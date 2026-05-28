import asyncio
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

from fastmcp import Client as MCPClient
from fastmcp.exceptions import ToolError
from pydantic import BaseModel

try:
    from .mcp_server import mcp as _jobs_db_mcp
    from .prompt_model import prompt_model_full
except ImportError:
    from mcp_server import mcp as _jobs_db_mcp
    from prompt_model import prompt_model_full


# Primary model for resume skill extraction; uses a capable but fast model
DEFAULT_MODEL = "gemini-2.5-flash-lite"
FALLBACK_MODEL = "gemini-2.5-flash"
MAX_RETRIES = 3
# Rate limits file path (relative to this file)
RATE_LIMITS_FILE = Path(__file__).parent / "rate_limits.txt"


def load_rate_limits() -> dict[str, int]:
    """Parse rate_limits.txt into {model_name: requests_per_minute}."""
    limits: dict[str, int] = {}
    try:
        with open(RATE_LIMITS_FILE) as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 2:
                    model, rpm_str = parts[0], parts[1]
                    try:
                        limits[model] = int(rpm_str)
                    except ValueError:
                        pass
    except FileNotFoundError:
        pass
    return limits


def get_sleep_seconds(model: str) -> int:
    """Return seconds to wait between calls = 60 / RPM from rate_limits.txt."""
    limits = load_rate_limits()
    rpm = limits.get(model, 5)  # default to 5 RPM if model not in file
    return max(1, 60 // rpm)

# BONUS: Regex patterns to detect prompt injection attacks in user-supplied resume text
# A malicious user could try to overwrite the LLM's instructions via the resume file
_INJECTION_PATTERNS = [
    r"ignore\s+(?:(?:previous|above|all|your)\s+)+instructions",
    r"you\s+are\s+now\b",
    r"new\s+(role|persona|instructions)",
    r"disregard\s+(?:your|the)\s+(?:previous|above)",
    r"act\s+as\s+(?:if|a)\b",
]


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


# Pydantic model to enforce a typed, validated return value from find_skill_gaps
class SkillGapResult(BaseModel):
    gaps: list[str]          # Sorted list of skills the candidate is missing
    tokens: int = 0          # BONUS: Total LLM tokens consumed
    time: float = 0.0        # BONUS: Wall-clock seconds for the full run
    stats: dict[str, int] = {}  # BONUS: Demand count per gap skill, sorted by frequency


def find_skill_gaps(input_file_path: str, db_url: str) -> SkillGapResult:
    """
    Read a resume text file and a tagged jobs database, then identify
    technical skills that appear in job requirements but are missing
    from the resume.

    Args:
        input_file_path: Path to the resume text file.
        db_url: Path to the SQLite database.

    Returns:
        SkillGapResult containing sorted missing skills.
    """
    resume_path = Path(input_file_path)
    db_path = Path(db_url)

    if not resume_path.exists():
        raise FileNotFoundError(f"Resume file not found: {resume_path}")

    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    start_time = time.time()

    resume_text = resume_path.read_text(encoding="utf-8", errors="ignore")

    # BONUS: Jailbreak prevention — scan resume for injection attempts before sending to LLM
    if _is_injection(resume_text):
        print("Warning: Potential prompt injection detected. Sanitizing resume.")
        resume_text = _sanitize(resume_text)

    # Step 1: Use LLM to extract skills the candidate already has
    resume_skills, tokens = extract_resume_skills(resume_text)
    # Step 2: Read all skills demanded by the job market from the database
    market_skills = read_market_skills(db_path)

    # Step 3: Compute the difference (market skills not in the resume)
    gaps = calculate_gaps(resume_skills, market_skills)
    # BONUS: Compute demand statistics so the user can prioritise which gaps to close
    stats = calculate_stats(resume_skills, market_skills)

    elapsed = round(time.time() - start_time, 2)
    return SkillGapResult(gaps=gaps, tokens=tokens, time=elapsed, stats=stats)


def _is_injection(text: str) -> bool:
    # Check the entire text in lowercase so case variations are not missed
    lower = text.lower()
    return any(re.search(p, lower) for p in _INJECTION_PATTERNS)


def _sanitize(text: str) -> str:
    # Remove only the lines that contain injection patterns; keep the rest of the resume
    return "\n".join(
        line for line in text.splitlines()
        if not any(re.search(p, line.lower()) for p in _INJECTION_PATTERNS)
    )


def extract_resume_skills(resume_text: str) -> tuple[set[str], int]:
    prompt = build_resume_prompt(resume_text)
    skills_text, tokens = call_model_with_retry(prompt)

    # Split the comma-separated response and normalise each skill
    skills = split_skills(skills_text)
    # Return a set so membership checks are O(1) during gap calculation
    return {normalise_skill(s) for s in skills if normalise_skill(s)}, tokens


def build_resume_prompt(resume_text: str) -> str:
    resume_text = resume_text[:4000]
    return (
        "Extract technical skills (languages, frameworks, tools, cloud platforms, databases, "
        "testing methodologies, analytical techniques) "
        "from this resume. Return comma-separated lowercase values only. "
        "No explanations, no soft skills, no certifications. Return None if none found.\n\n"
        f"Resume:\n{resume_text}\n\nAnswer:"
    )


def read_market_skills(db_path: Path) -> list[str]:
    # BONUS (MCP): Route DB access through the FastMCP server instead of direct sqlite3
    async def _get_via_mcp() -> list[str]:
        async with MCPClient(_jobs_db_mcp) as db:
            result = await db.call_tool("get_market_skills", {"db_path": str(db_path)})
            return _parse_tool_result(result) or []

    tech_stacks = asyncio.run(_get_via_mcp())

    skills = []

    # Each row's tech_stack is a comma-separated string; flatten all into one list
    for tech_stack in tech_stacks:
        skills.extend(split_skills(tech_stack))

    # Normalise every skill so aliases map to the same canonical name
    return [normalise_skill(skill) for skill in skills if normalise_skill(skill)]


def calculate_gaps(resume_skills: set[str], market_skills: list[str]) -> list[str]:
    # Counter gives unique market skills; sorted ensures deterministic output
    return sorted(skill for skill in Counter(market_skills) if skill not in resume_skills)


def calculate_stats(resume_skills: set[str], market_skills: list[str]) -> dict[str, int]:
    """Return demand count for each gap skill, sorted by demand descending."""
    counter = Counter(market_skills)
    # most_common() is already sorted by count descending
    return {
        skill: count
        for skill, count in counter.most_common()
        if skill not in resume_skills
    }


def call_model_with_retry(prompt: str) -> tuple[str, int]:
    total_tokens = 0

    for attempt in range(1, MAX_RETRIES + 1):
        # temperature=0.0 ensures deterministic output across repeated runs
        result = prompt_model_full(DEFAULT_MODEL, prompt, temperature=0.0)
        total_tokens += result.tokens

        if is_rate_limit_error(result.text):
            delay = get_retry_delay(result.text)
            print(
                f"{DEFAULT_MODEL} rate limit. "
                f"Waiting {delay}s (attempt {attempt}/{MAX_RETRIES})..."
            )
            time.sleep(delay)
            continue

        cleaned = clean_response(result.text)
        if cleaned:
            return cleaned, total_tokens

        print(f"Attempt {attempt} failed. Retrying...")
        time.sleep(get_sleep_seconds(DEFAULT_MODEL))

    # Switch to a stronger model as a last resort
    print(f"{DEFAULT_MODEL} failed. Falling back to {FALLBACK_MODEL}...")
    result = prompt_model_full(FALLBACK_MODEL, prompt, temperature=0.0)
    total_tokens += result.tokens
    return clean_response(result.text), total_tokens


def clean_response(response: str) -> str:
    if not response:
        return ""

    text = response.strip()

    if is_rate_limit_error(text):
        return ""

    # Treat explicit "no result" responses as empty
    if text.lower() in {"none", "n/a", "no technical skills found"}:
        return ""

    # Remove markdown code fences and prompt echo
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"^[Aa]nswer:\s*", "", text)
    # Normalise newline-separated lists to comma-separated
    text = text.replace("\n", ",")

    return text.strip()


def split_skills(text: str) -> list[str]:
    if not text:
        return []

    # Normalise all separator styles to commas before splitting
    text = text.replace(";", ",")
    text = text.replace("|", ",")

    raw_skills = text.split(",")

    cleaned = []

    for skill in raw_skills:
        skill = skill.strip()
        # Remove leading bullet/number markers (e.g., "- Python" -> "Python")
        skill = re.sub(r"^[\-\*\d\.\)\s]+", "", skill)
        skill = re.sub(r"\s+", " ", skill)

        if not skill:
            continue

        # Discard entries that are too long to be a valid skill name
        if len(skill) > 50:
            continue

        cleaned.append(skill)

    return cleaned


def normalise_skill(skill: str) -> str:
    # Lowercase and collapse whitespace so comparisons are case/space insensitive
    skill = skill.strip().lower()
    skill = re.sub(r"\s+", " ", skill)

    # Alias table maps common variants to a single canonical name
    # This prevents "js" and "javascript" from being counted as separate skills
    aliases = {
        "javascript": "javascript",
        "js": "javascript",
        "typescript": "typescript",
        "ts": "typescript",
        "nodejs": "node.js",
        "node.js": "node.js",
        "reactjs": "react",
        "react.js": "react",
        "react": "react",
        "postgres": "postgresql",
        "postgresql": "postgresql",
        "mysql": "mysql",
        "mongo db": "mongodb",
        "mongodb": "mongodb",
        "amazon web services": "aws",
        "aws": "aws",
        "google cloud platform": "gcp",
        "gcp": "gcp",
        "microsoft azure": "azure",
        "azure": "azure",
        "large language models": "llm",
        "llms": "llm",
        "llm": "llm",
        "retrieval-augmented generation": "rag",
        "rag": "rag",
        "ci/cd": "ci/cd",
        "cicd": "ci/cd",
        "rest api": "rest api",
        "restful api": "rest api",
        "restful apis": "rest api",
        # C/C++ normalization — assignment requires these to match exactly
        "c++": "c++",
        "c/c++": "c++",
        "cplusplus": "c++",
        "c plus plus": "c++",
        # Additional common aliases
        "golang": "go",
        "go lang": "go",
        "k8s": "kubernetes",
        "kubernetes": "kubernetes",
        "python3": "python",
        "python": "python",
        "scikit learn": "scikit-learn",
        "scikit-learn": "scikit-learn",
        "sklearn": "scikit-learn",
        "apis": "api",
        "api": "api",
    }

    # Return the canonical name if known, otherwise return the skill as-is
    return aliases.get(skill, skill)


def is_rate_limit_error(response: str) -> bool:
    if not response:
        return False

    # Keywords that appear in Google API rate-limit and quota error messages
    error_keywords = [
        "RESOURCE_EXHAUSTED",
        "quotaValue",
        "quotaDimensions",
        "retryDelay",
        "429",
        "UNAVAILABLE",
    ]

    return any(keyword in response for keyword in error_keywords)


def get_retry_delay(response: str) -> int:
    # Try to extract the exact suggested delay from the API error body
    match = re.search(r"'retryDelay': '(\d+)s'", response)

    if match:
        return int(match.group(1))

    match = re.search(r"retryDelay.*?(\d+)s", response)

    if match:
        return int(match.group(1))

    # Safe default when the delay cannot be parsed
    return 60


def main() -> None:
    # Default paths work for evaluation; override by passing two arguments:
    # uv run find_skill_gaps.py <resume.txt> <jobs.db>
    input_file_path = "resources_eval/resume_d3_eval.txt"
    db_url = "resources_eval/jobs_d3_eval.db"

    if len(sys.argv) >= 3:
        input_file_path = sys.argv[1]
        db_url = sys.argv[2]

    try:
        result = find_skill_gaps(input_file_path, db_url)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ToolError as e:
        print(f"Database error: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result.model_dump(), indent=2))


if __name__ == "__main__":
    main()