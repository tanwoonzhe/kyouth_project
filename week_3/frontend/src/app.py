import asyncio
import io
import json
import os
import pathlib
import re
from typing import Annotated

import httpx
import pypdf
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

load_dotenv()

app = FastAPI()

BASE_DIR = pathlib.Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8001")
MAX_PDF_BYTES = 10 * 1024 * 1024  # 10 MB


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/static/services/api.js")
async def serve_api_js():
    """Serve the API service module without requiring aiofiles."""
    path = BASE_DIR / "static" / "services" / "api.js"
    content = path.read_text(encoding="utf-8")
    return Response(content=content, media_type="application/javascript")


@app.get("/stats", response_class=HTMLResponse)
async def stats_page(request: Request):
    return templates.TemplateResponse("stats.html", {"request": request})


@app.post("/chat")
async def chat(
    message: Annotated[str, Form()] = "",
    pdf: Annotated[UploadFile | None, File()] = None,
):
    pdf_text = ""
    if pdf and pdf.filename:
        contents = await pdf.read()
        if len(contents) > MAX_PDF_BYTES:
            return JSONResponse({"reply": "PDF too large (max 10 MB)."}, status_code=413)
        try:
            pdf_text = _extract_pdf_text(contents)
        except Exception as exc:
            return JSONResponse(
                {"reply": f"Could not read the PDF ({type(exc).__name__}). "
                           "Please ensure it is a valid, non-corrupted PDF file."},
                status_code=400,
            )

    if not message.strip() and not pdf_text.strip():
        return JSONResponse(
            {"reply": "Please type a message or upload a PDF resume."},
            status_code=400,
        )

    payload = {"message": message, "pdf_text": pdf_text}
    try:
        def _post():
            return httpx.post(f"{BACKEND_URL}/chat", json=payload, timeout=120.0)
        resp = await asyncio.to_thread(_post)
        try:
            return JSONResponse(content=resp.json(), status_code=resp.status_code)
        except Exception:
            return JSONResponse(
                {"reply": "Backend returned an unexpected response. Please try again."},
                status_code=502,
            )
    except Exception as exc:
        return JSONResponse({"reply": f"Backend is not available. ({type(exc).__name__}: {exc})"}, status_code=503)


@app.get("/api/stats")
async def api_stats():
    try:
        def _get():
            return httpx.get(f"{BACKEND_URL}/stats", timeout=10.0)
        resp = await asyncio.to_thread(_get)
        try:
            return JSONResponse(content=resp.json(), status_code=resp.status_code)
        except Exception:
            return JSONResponse(
                {"error": "Backend returned an unexpected response."},
                status_code=502,
            )
    except Exception as exc:
        return JSONResponse({"error": f"Backend is not available. ({type(exc).__name__}: {exc})"}, status_code=503)


@app.get("/api/roles")
async def api_roles():
    """Return distinct job roles. Tries backend /roles first; falls back to preset list."""
    try:
        def _get():
            return httpx.get(f"{BACKEND_URL}/roles", timeout=5.0)
        resp = await asyncio.to_thread(_get)
        if resp.status_code == 200:
            return JSONResponse(content=resp.json(), status_code=200)
    except Exception:
        pass
    return JSONResponse({"roles": _MOCK_ROLES, "_fallback": True})


@app.get("/api/locations")
async def api_locations():
    """Return distinct locations. Tries backend /locations first; falls back to preset list."""
    try:
        def _get():
            return httpx.get(f"{BACKEND_URL}/locations", timeout=5.0)
        resp = await asyncio.to_thread(_get)
        if resp.status_code == 200:
            return JSONResponse(content=resp.json(), status_code=200)
    except Exception:
        pass
    return JSONResponse({"locations": _MOCK_LOCATIONS, "_fallback": True})


def _extract_pdf_text(contents: bytes) -> str:
    reader = pypdf.PdfReader(io.BytesIO(contents))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


# ── Analyze endpoint ─────────────────────────────────────────────────────────

_MOCK_TOP_SKILLS: list[dict] = [
    {"skill": "Python", "count": 120},
    {"skill": "SQL", "count": 95},
    {"skill": "Docker", "count": 88},
    {"skill": "Machine Learning", "count": 82},
    {"skill": "Git", "count": 110},
    {"skill": "TensorFlow", "count": 65},
    {"skill": "FastAPI", "count": 60},
    {"skill": "Kubernetes", "count": 55},
    {"skill": "REST API", "count": 70},
    {"skill": "LLM / GenAI", "count": 45},
]

_MOCK_ROLES: list[str] = [
    "AI Engineer",
    "Applied AI Engineer",
    "AI Chatbot Developer",
    "AI Software Engineer",
    "Machine Learning Engineer",
    "Computer Vision Engineer",
    "Data Scientist",
    "Data Engineer",
    "Backend Developer",
    "Full Stack Developer",
    "Software Engineer",
    "DevOps / Cloud Engineer",
    "Algorithm Engineer",
]

_MOCK_LOCATIONS: list[str] = [
    "Kuala Lumpur",
    "Selangor",
    "Cyberjaya, Selangor",
    "Petaling Jaya, Selangor",
    "Penang",
    "Johor Bahru",
    "Melaka",
    "Remote / Malaysia",
]



def _build_analyze_prompt(
    target_role: str,
    location: str,
    user_skills: list[str],
    top_market_skills: list[dict],
    pdf_text: str = "",
    expected_salary: str = "",
) -> str:
    market_str = ", ".join(s["skill"] for s in top_market_skills[:10])
    skills_str = ", ".join(user_skills) if user_skills else "not specified"
    resume_part = f"\n\nResume excerpt:\n{pdf_text[:800]}" if pdf_text else ""
    salary_part = f"\nExpected Salary: {expected_salary}" if expected_salary else ""
    return (
        "You are a career analyst for tech jobs in Malaysia. "
        "Analyze the profile below and return ONLY valid JSON with NO markdown.\n\n"
        f"Target Role: {target_role}\n"
        f"Location: {location}\n"
        f"User Skills: {skills_str}{resume_part}{salary_part}\n"
        f"Top Market Skills: {market_str}\n\n"
        "Return exactly this JSON (nothing else):\n"
        '{"match_score": <0-100>, '
        '"missing_skills": [{"skill": "<name>", "priority": "high|medium|low"}], '
        '"ai_recommendation": "<2-3 sentences>", '
        '"limitations": "<1-2 sentences>"}'
    )


def _parse_ai_json(reply: str) -> dict:
    clean = re.sub(r"```(?:json)?", "", reply).strip().strip("`")
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return {}


def _compute_missing_skills(
    user_skills: list[str], top_market_skills: list[dict]
) -> list[dict]:
    user_lower = {s.lower() for s in user_skills}
    result = []
    for i, s in enumerate(top_market_skills):
        if s["skill"].lower() not in user_lower:
            priority = "high" if i < 3 else ("medium" if i < 6 else "low")
            result.append({"skill": s["skill"], "priority": priority})
    return result[:5]


@app.post("/analyze")
async def analyze(
    target_role: Annotated[str, Form()],
    location: Annotated[str, Form()],
    current_skills: Annotated[str, Form()] = "",
    expected_salary: Annotated[str, Form()] = "",
    pdf: Annotated[UploadFile | None, File()] = None,
):
    # 1. Extract PDF text
    pdf_text = ""
    if pdf and pdf.filename:
        contents = await pdf.read()
        if len(contents) > MAX_PDF_BYTES:
            return JSONResponse({"error": "PDF too large (max 10 MB)."}, status_code=413)
        try:
            pdf_text = _extract_pdf_text(contents)
        except Exception as exc:
            return JSONResponse(
                {"error": f"Could not read PDF ({type(exc).__name__}). "
                           "Please ensure it is a valid PDF file."},
                status_code=400,
            )

    # 2. Parse user skills (fall back to PDF text if no skills typed)
    user_skills = [s.strip() for s in current_skills.split(",") if s.strip()]

    # 3. Fetch market stats from backend
    stats_data: dict | None = None
    try:
        def _get_stats():
            return httpx.get(f"{BACKEND_URL}/stats", timeout=10.0)

        stats_resp = await asyncio.to_thread(_get_stats)
        if stats_resp.status_code == 200:
            body = stats_resp.json()
            if not body.get("error"):
                stats_data = body
    except Exception:
        pass

    # 4. Build top market skills and total jobs count
    if stats_data:
        top_skills_raw: dict = stats_data.get("top_skills", {})
        top_market_skills = [
            {"skill": k, "count": v} for k, v in list(top_skills_raw.items())[:10]
        ]
        total_jobs = max(top_skills_raw.values(), default=0) if top_skills_raw else 0
    else:
        top_market_skills = _MOCK_TOP_SKILLS
        total_jobs = 148

    # 5. Compute matched skills and a simple fallback score
    market_names_lower = {s["skill"].lower() for s in top_market_skills}
    matched_skills = [s for s in user_skills if s.lower() in market_names_lower]
    if user_skills:
        simple_score = min(100, round(len(matched_skills) / len(user_skills) * 100))
    else:
        simple_score = 0

    # 6. Get AI analysis (only when backend is reachable)
    ai_result: dict = {}
    if stats_data:
        prompt = _build_analyze_prompt(
            target_role, location, user_skills, top_market_skills, pdf_text, expected_salary
        )
        try:
            def _post_chat():
                return httpx.post(
                    f"{BACKEND_URL}/chat",
                    json={"message": prompt, "pdf_text": ""},
                    timeout=120.0,
                )

            chat_resp = await asyncio.to_thread(_post_chat)
            if chat_resp.status_code == 200:
                ai_result = _parse_ai_json(chat_resp.json().get("reply", ""))
        except Exception:
            pass

    # 7. Assemble final response
    match_score = int(ai_result.get("match_score") or simple_score)
    missing_skills = ai_result.get("missing_skills") or _compute_missing_skills(
        user_skills, top_market_skills
    )
    ai_recommendation = ai_result.get("ai_recommendation", "")
    limitations = ai_result.get(
        "limitations",
        "Analysis based on available Jobstreet Malaysia job listings.",
    )

    if not ai_recommendation:
        ai_recommendation = (
            "AI recommendation unavailable — the backend may still be loading. "
            "Please retry in a moment."
        )
        limitations += " AI analysis was not available for this request."

    return JSONResponse({
        "match_score": match_score,
        "total_jobs": total_jobs,
        "top_market_skills": top_market_skills,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "ai_recommendation": ai_recommendation,
        "limitations": limitations,
        "expected_salary": expected_salary or None,
        "_mock": not bool(stats_data),
    })
