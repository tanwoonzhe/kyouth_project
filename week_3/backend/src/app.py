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
_secret_key_path = Path("/run/secrets/google_api_key")
if _secret_key_path.exists():
    os.environ.setdefault("GOOGLE_API_KEY", _secret_key_path.read_text().strip())

# Ensure the week_2 package is importable when uvicorn is run from backend/
sys.path.insert(0, str(Path(__file__).parent))

from week_2.find_skill_gaps import find_skill_gaps  # noqa: E402
from week_2.prompt_model import prompt_model  # noqa: E402

load_dotenv()

app = FastAPI()

DB_PATH = Path(os.getenv("DB_PATH", "/app/data/jobs.db"))
CHAT_MODEL = os.getenv("CHAT_MODEL", "gemini-2.5-flash-lite")
SYSTEM_PROMPT = (
    "You are a helpful career assistant specialising in tech jobs in Malaysia. "
    "Answer questions about skills, job market trends, and career advice concisely."
)


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
            # Resume uploaded — write to temp file, then run skill-gap analysis in a
            # thread so that find_skill_gaps can safely call asyncio.run() internally.
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
                top_gaps = result.gaps[:20]
                gap_list = ", ".join(top_gaps)
                reply = (
                    "Based on your resume and the current job market, "
                    "the following skills are most in demand but missing from your profile:\n\n"
                    f"{gap_list}"
                )
                if req.message.strip():
                    followup = await asyncio.to_thread(
                        prompt_model,
                        CHAT_MODEL,
                        f"{SYSTEM_PROMPT}\n\nUser question: {req.message}\n"
                        f"Identified skill gaps: {gap_list}\n\nAnswer concisely:",
                    )
                    reply = f"{reply}\n\n{followup}"
            else:
                reply = "No significant skill gaps were found in your resume."

        else:
            # General chat — no resume
            full_prompt = f"{SYSTEM_PROMPT}\n\nUser: {req.message}\n\nAssistant:"
            reply = await asyncio.to_thread(prompt_model, CHAT_MODEL, full_prompt)

        return JSONResponse({"reply": reply})

    except FileNotFoundError as exc:
        return JSONResponse({"reply": f"Configuration error: {exc}"}, status_code=500)
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

