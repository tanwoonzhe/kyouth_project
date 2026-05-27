import asyncio
import io
import os
import pathlib
from typing import Annotated

import httpx
import pypdf
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Request, UploadFile
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
    return templates.TemplateResponse("chat_page.html", {"request": request})


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


def _extract_pdf_text(contents: bytes) -> str:
    reader = pypdf.PdfReader(io.BytesIO(contents))
    return "\n".join(page.extract_text() or "" for page in reader.pages)
