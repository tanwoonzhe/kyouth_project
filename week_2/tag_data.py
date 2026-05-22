import asyncio
import json
import re
import sys
import time
from pathlib import Path

from fastmcp import Client as MCPClient

from mcp_server import mcp as _jobs_db_mcp
from prompt_model import prompt_model_full


# Primary model used for tagging; falls back to FALLBACK_MODEL if it fails
DEFAULT_MODEL = "gemini-3.1-flash-lite"
FALLBACK_MODEL = "gemini-2.5-flash-lite"
# How many times to retry a failed LLM call before giving up or switching model
MAX_RETRIES = 3
# Seconds to wait between retries to avoid hitting rate limits back-to-back
SLEEP_SECONDS = 3


def _parse_tool_result(result):
    # FastMCP 3.x returns a CallToolResult object; content is in result.content
    if not result:
        return None
    content_list = getattr(result, "content", None) or result
    if not content_list:
        return None
    text = getattr(content_list[0], "text", "")
    if not text:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return text


async def _tag_data_async(db_url: str) -> tuple[int, float]:
    """
    Async core of tag_data — all DB operations go through the in-process
    FastMCP server (mcp_server.py) instead of calling sqlite3 directly.
    """
    db_path = Path(db_url)

    if not db_path.exists():
        print(f"Database not found: {db_path}")
        return 0, 0.0

    # Open one persistent in-process MCP connection for the entire tagging session
    async with MCPClient(_jobs_db_mcp) as db:
        # Idempotent schema migration via MCP tool
        await db.call_tool("ensure_tech_stack_column", {"db_path": db_url})

        # Retrieve only untagged rows so the script is safe to re-run
        raw = await db.call_tool("get_untagged_jobs", {"db_path": db_url})
        rows = _parse_tool_result(raw) or []

        if not rows:
            print("No rows to tag.")
            return 0, 0.0

        # BONUS: Track total token usage across all LLM calls
        total_tokens = 0
        start_time = time.time()

        for index, row in enumerate(rows, start=1):
            source_id = row["source_id"]
            job_title = row["job_title"]
            description = row["description"]

            # Build a focused prompt using job title and description
            prompt = build_prompt(job_title, description)
            # Call the LLM with retry logic; returns cleaned skill string + token count
            skills, token_estimate = extract_skills_with_retry(prompt)

            total_tokens += token_estimate

            if not skills:
                print(
                    f"[Batch {index}] failed: source_id={source_id}, "
                    "no valid skills returned"
                )
                continue

            # Persist via MCP — no direct sqlite3 call in this file
            # Each row is committed immediately inside the MCP tool to preserve progress
            await db.call_tool(
                "update_tech_stack",
                {"db_path": db_url, "source_id": source_id, "skills": skills},
            )

            print(
                f"[Batch {index}] tokens={total_tokens} | source_id={source_id}, "
                f"job_title={job_title}, skills={skills}"
            )

        elapsed = time.time() - start_time
        # BONUS: Print token and time summary after all rows are processed
        print(f"Total tokens used (input + output): {total_tokens}")
        print(f"Total time used: {elapsed:.2f}s")
        return total_tokens, elapsed


def tag_data(db_url: str) -> tuple[int, float]:
    """
    Read job descriptions from a SQLite database (via MCP), extract technical
    skills using an LLM, and write the results back through MCP.

    Args:
        db_url: Path to the SQLite database.

    Returns:
        A tuple of (total_tokens, elapsed_seconds) where total_tokens is the
        combined input + output token count reported by the Gemini API.
    """
    # BONUS (MCP): All DB operations are routed through the FastMCP server in mcp_server.py
    return asyncio.run(_tag_data_async(db_url))


def build_prompt(job_title: str, description: str) -> str:
    # Most relevant skills are mentioned early in a job post
    description = description[:3000]

    return f"""
You are a skill extraction assistant.

Extract only technical skills, tools, programming languages, frameworks,
cloud platforms, databases, and software technologies from the job post.

Rules:
- Return comma-separated values only.
- Do not explain.
- Do not use bullet points.
- Do not include soft skills such as communication, leadership, teamwork, or management.
- Do not include generic words such as responsible, experience, candidate, requirement.
- Use short skill names.
- If no technical skills are found, return: None.

Job title:
{job_title}

Job description:
{description}

Answer:
""".strip()


def extract_skills_with_retry(prompt: str) -> tuple[str, int]:
    # Accumulate real token counts returned by the Gemini API (input + output).
    # estimate_tokens() is only used as a fallback when the API returns 0 (error path).
    total_tokens = 0

    for attempt in range(1, MAX_RETRIES + 1):
        result = prompt_model_full(DEFAULT_MODEL, prompt)
        # Use actual token count from API; fall back to character estimate if unavailable
        total_tokens += (
            result.tokens
            if result.tokens
            else estimate_tokens(prompt) + estimate_tokens(result.text)
        )

        # If the API returns a rate-limit error, wait and retry
        if is_rate_limit_error(result.text):
            delay = get_retry_delay(result.text)
            print(
                f"{DEFAULT_MODEL} rate limit reached. "
                f"Waiting {delay}s before retry {attempt}/{MAX_RETRIES}..."
            )
            time.sleep(delay)
            continue

        # Clean and validate the response; empty string means the LLM gave bad output
        skills = clean_skills(result.text)

        if skills:
            return skills, total_tokens

        print(f"Attempt {attempt} failed with {DEFAULT_MODEL}. Retrying...")
        time.sleep(SLEEP_SECONDS)

    # After all retries, switch to the fallback model for one final attempt
    print(f"{DEFAULT_MODEL} failed. Falling back to {FALLBACK_MODEL}...")

    result = prompt_model_full(FALLBACK_MODEL, prompt)
    total_tokens += (
        result.tokens
        if result.tokens
        else estimate_tokens(prompt) + estimate_tokens(result.text)
    )

    skills = clean_skills(result.text)

    return skills, total_tokens


def clean_skills(response: str) -> str:
    if not response:
        return ""

    text = response.strip()

    # If the response is still a rate-limit error message, treat it as a failure
    if is_rate_limit_error(text):
        return ""

    # LLM said no skills found; treat as empty result
    if text.lower() in {"none", "no technical skills found", "n/a"}:
        return ""

    # Remove any markdown code fences the LLM may have added
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    # Normalize all separator styles to commas
    text = text.replace("\n", ",")
    text = text.replace(";", ",")
    text = text.replace("|", ",")
    # Strip "Answer:" prefix if the LLM echoed the prompt template
    text = re.sub(r"^[Aa]nswer:\s*", "", text)

    raw_skills = [item.strip() for item in text.split(",")]

    cleaned_skills = []
    seen = set()  # Track lowercase keys to deduplicate

    # Soft skills and generic filler words to filter out
    banned_words = {
        "communication",
        "teamwork",
        "leadership",
        "management",
        "problem solving",
        "responsible",
        "experience",
        "candidate",
        "requirement",
        "requirements",
    }

    for skill in raw_skills:
        # Remove leading list markers like "- ", "* ", "1. ", "a) "
        skill = re.sub(r"^[\-\*\d\.\)\s]+", "", skill).strip()
        # Collapse multiple spaces into one
        skill = re.sub(r"\s+", " ", skill)

        if not skill:
            continue

        # Discard suspiciously long strings (likely a sentence, not a skill name)
        if len(skill) > 40:
            continue

        if skill.lower() in banned_words:
            continue

        key = skill.lower()

        # Only add if we haven't seen this skill before (case-insensitive dedup)
        if key not in seen:
            cleaned_skills.append(skill)
            seen.add(key)

    return ", ".join(cleaned_skills)


def estimate_tokens(text: str) -> int:

    if not text:
        return 0

    return max(1, len(text) // 4)


def get_retry_delay(response: str) -> int:
    # Try to parse the retryDelay seconds from the API error message
    match = re.search(r"'retryDelay': '(\d+)s'", response)

    if match:
        return int(match.group(1))

    match = re.search(r"retryDelay.*?(\d+)s", response)

    if match:
        return int(match.group(1))

    # Default to 60 seconds if we cannot parse the suggested delay
    return 60


def is_rate_limit_error(response: str) -> bool:
    if not response:
        return False

    # These keywords appear in Google API rate-limit and availability error messages
    error_keywords = [
        "RESOURCE_EXHAUSTED",
        "quotaValue",
        "quotaDimensions",
        "retryDelay",
        "429",
        "UNAVAILABLE",
    ]

    return any(keyword in response for keyword in error_keywords)


def main() -> None:
    # Default database path; can be overridden by passing a path as the first argument
    db_url = "data/jobs.db"

    if len(sys.argv) > 1:
        db_url = sys.argv[1]

    tag_data(db_url)


if __name__ == "__main__":
    main()
