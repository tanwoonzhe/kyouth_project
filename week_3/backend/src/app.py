import asyncio
import os
import sqlite3
import sys
import tempfile
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Bonus 2: load GOOGLE_API_KEY from Docker secret file if present
# read_bytes + decode handles UTF-8, UTF-16 LE/BE (with or without BOM)
# so the file works regardless of how it was created (PowerShell, bash, etc.)
_secret_key_path = Path("/run/secrets/google_api_key")
if _secret_key_path.exists():
    _raw = _secret_key_path.read_bytes()
    _key = _raw.decode("utf-16" if _raw[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8").strip()
    os.environ.setdefault("GOOGLE_API_KEY", _key)

# Ensure the week_2 package is importable when uvicorn is run from backend/
sys.path.insert(0, str(Path(__file__).parent))

from week_2.find_skill_gaps import find_skill_gaps  # noqa: E402
from week_2.prompt_model import prompt_model  # noqa: E402

load_dotenv()

app = FastAPI()

DB_PATH = Path(os.getenv("DB_PATH", "/app/data/jobs.db"))


@app.on_event("startup")
async def startup_checks():
    if not DB_PATH.exists():
        print(
            f"WARNING: Database not found at {DB_PATH}. "
            "/stats and PDF skill-gap analysis will not work until the DB is mounted.",
            file=sys.stderr,
        )
    if not os.getenv("GOOGLE_API_KEY"):
        print(
            "WARNING: GOOGLE_API_KEY is not set. Chat and skill-gap analysis will fail.",
            file=sys.stderr,
        )
CHAT_MODEL = os.getenv("CHAT_MODEL", "gemini-2.5-flash-lite")
CHAT_FALLBACK_MODEL = os.getenv("CHAT_FALLBACK_MODEL", "gemini-2.5-flash")
SYSTEM_PROMPT = (
    "You are a helpful career assistant specialising in tech jobs in Malaysia. "
    "Answer questions about skills, job market trends, and career advice concisely."
)

_SKILL_GAP_KEYWORDS = {
    "skill gap", "skills gap", "skill gaps", "skills gaps",
    "missing skill", "missing skills", "find gap", "find gaps",
    "lacking skill", "lacking skills", "what skill", "what skills",
    "gap analysis",
}


def _is_skill_gap_request(message: str) -> bool:
    """Return True if the message is asking for skill-gap analysis."""
    lower = message.lower()
    return any(kw in lower for kw in _SKILL_GAP_KEYWORDS)


def _is_retryable_error(reply: str) -> bool:
    """Return True if prompt_model returned a 503/429 error string."""
    return reply.startswith("Error:") and (
        "503" in reply or "UNAVAILABLE" in reply
        or "429" in reply or "quota" in reply.lower()
    )


async def _chat(prompt: str) -> str:
    """Call prompt_model with CHAT_MODEL, falling back to CHAT_FALLBACK_MODEL on 503/429."""
    reply = await asyncio.to_thread(prompt_model, CHAT_MODEL, prompt)
    if _is_retryable_error(reply):
        reply = await asyncio.to_thread(prompt_model, CHAT_FALLBACK_MODEL, prompt)
    return reply


class ChatRequest(BaseModel):
    message: str = ""
    pdf_text: str = ""


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/chat")
async def chat(req: ChatRequest):
    try:
        if req.pdf_text.strip():
            if _is_skill_gap_request(req.message):
                # Skill-gap analysis — write resume to temp file and run pipeline
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".txt", delete=False, encoding="utf-8"
                ) as tmp:
                    tmp.write(req.pdf_text)
                    tmp_path = tmp.name

                try:
                    result = await asyncio.to_thread(
                        find_skill_gaps, tmp_path, str(DB_PATH)
                    )
                finally:
                    Path(tmp_path).unlink(missing_ok=True)

                if result.gaps:
                    reply = (
                        "Skills gap identified:\n\n"
                        + " - ".join([""] + result.gaps)
                    )
                else:
                    reply = "No significant skill gaps were found in your resume."

            else:
                # Free-form Q&A with the resume as context (summarise, review, etc.)
                user_q = req.message.strip() or "Please summarise this resume."
                full_prompt = (
                    f"{SYSTEM_PROMPT}\n\n"
                    f"Resume content:\n{req.pdf_text}\n\n"
                    f"User: {user_q}\n\nAssistant:"
                )
                reply = await _chat(full_prompt)

        else:
            # General chat — no resume
            full_prompt = f"{SYSTEM_PROMPT}\n\nUser: {req.message}\n\nAssistant:"
            reply = await _chat(full_prompt)

        return JSONResponse({"reply": reply})

    except FileNotFoundError as exc:
        msg = (
            f"The jobs database was not found ({DB_PATH}). "
            "Please contact the administrator."
            if "jobs.db" in str(exc) or str(DB_PATH) in str(exc)
            else f"A required file was missing: {exc}"
        )
        return JSONResponse({"reply": msg}, status_code=503)
    except Exception as exc:
        return JSONResponse(
            {"reply": f"Error processing request: {exc}"}, status_code=500
        )


@app.get("/stats")
async def stats():
    try:
        if not DB_PATH.exists():
            return JSONResponse(
                {"error": f"Database not found at {DB_PATH}"}, status_code=503
            )

        conn = sqlite3.connect(str(DB_PATH))
        try:
            loc_rows = conn.execute(
                "SELECT company, COUNT(*) FROM jobs "
                "WHERE company IS NOT NULL AND TRIM(company) != '' "
                "GROUP BY company ORDER BY COUNT(*) DESC LIMIT 15"
            ).fetchall()
            location_dist = {r[0]: r[1] for r in loc_rows}

            type_rows = conn.execute(
                "SELECT job_title, COUNT(*) FROM jobs "
                "WHERE job_title IS NOT NULL "
                "GROUP BY job_title ORDER BY COUNT(*) DESC LIMIT 15"
            ).fetchall()
            job_type_dist = {r[0]: r[1] for r in type_rows}

            skill_rows = conn.execute(
                "SELECT tech_stack FROM jobs "
                "WHERE tech_stack IS NOT NULL AND TRIM(tech_stack) != '' "
                "AND tech_stack NOT LIKE '%RESOURCE_EXHAUSTED%'"
            ).fetchall()
            skill_counter: Counter = Counter()
            for (tech_stack,) in skill_rows:
                for s in tech_stack.split(","):
                    s = s.strip().lower()
                    if s:
                        skill_counter[s] += 1
            top_skills = dict(skill_counter.most_common(20))

            job_rows = conn.execute(
                "SELECT job_title, company, tech_stack FROM jobs LIMIT 100"
            ).fetchall()
            jobs = [
                {
                    "title": r[0],
                    "company": r[1],
                    "location": "",
                    "skills": [s.strip() for s in (r[2] or "").split(",") if s.strip()],
                }
                for r in job_rows
            ]
        finally:
            conn.close()

        return JSONResponse(
            {
                "location_distribution": location_dist,
                "top_skills": top_skills,
                "job_type_distribution": job_type_dist,
                "jobs": jobs,
            }
        )
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)

