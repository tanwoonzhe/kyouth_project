# Week 3 – Full-Stack AI Career Advisor

## Project Overview

This project is a containerised full-stack chat application that helps users identify skill gaps in their tech careers. Users upload a resume (PDF) and send a message; the backend analyses the resume against real job-market data scraped from Jobstreet Malaysia and returns a personalised skill-gap report powered by Google Gemini.

The system is built across three weeks:

| Week | Component | Role |
|------|-----------|------|
| Week 1 | ETL pipeline | Scrapes and cleans job listings into a SQLite database |
| Week 2 | AI pipeline | Tags jobs with skills; identifies resume skill gaps via FastMCP + Gemini |
| Week 3 | Web application | FastAPI frontend + backend served as Docker containers |

---

## Setup Instructions

### Prerequisites

| Tool | Purpose |
|------|---------|
| [Docker Desktop](https://docs.docker.com/get-started/get-docker/) | Run all services as containers |
| Google Gemini API key | Required for the AI model — get one free at [aistudio.google.com](https://aistudio.google.com) |
| Week 1 jobs database | `week_1/data/3_gold/jobs.db` must exist (run the Week 1 pipeline first) |

### 1 — Clone the repository

```bash
git clone <your-repo-url>
cd kyouth_project/week_3
```

### 2 — Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and set the values:

```
BACKEND_URL=http://backend:8001   # use this for Docker Compose
DB_PATH=/app/data/jobs.db         # leave as-is for Docker Compose
CHAT_MODEL=gemini-2.5-flash
```

Do **not** put your API key in `.env` — use Docker secrets instead (see step 3).

### 3 — Add your Google API key as a Docker secret

The `secrets/` folder already exists in the repo. Create the key file using one of the commands below depending on your OS.

**macOS / Linux / Git Bash:**
```bash
echo -n "YOUR_GOOGLE_API_KEY" > secrets/google_api_key.txt
```

**Windows PowerShell** (⚠️ do **not** use `echo` — it writes UTF-16):
```powershell
[System.IO.File]::WriteAllText("secrets\google_api_key.txt", "YOUR_GOOGLE_API_KEY")
```

**Windows Command Prompt:**
```cmd
<nul set /p="YOUR_GOOGLE_API_KEY" > secrets\google_api_key.txt
```

The key is never stored in `.env` or committed to git (the `secrets/` folder is in `.gitignore`).

### 4 — Run with Docker Compose

```bash
docker compose up --build
```

### 5 — Access the application

| URL | Service |
|-----|---------|
| http://localhost:8000 | Chat UI + Stats dashboard |
| http://localhost:8001/docs | Backend API documentation (Swagger UI) |

---

## Usage

### Running the application

```bash
# Build and start all services
docker compose up --build

# Run in the background
docker compose up --build -d

# Stop all services
docker compose down
```

### Using the chat interface

1. Open http://localhost:8000 in your browser
2. **General chat** — type a message such as *"What Python skills are in demand in Malaysia?"* and press **Send**
3. **Resume analysis** — click the 📎 icon, select your CV as a PDF (max 10 MB), then send a message like *"What skills am I missing for AI engineering roles?"*
4. The AI will return a list of skills found in job listings that are missing from your resume
5. Click **📊 Stats** (top-right) to see job market visualisations: top hiring companies, in-demand skills, and job type distribution

### Expected inputs and outputs

| Input | Format | Notes |
|-------|--------|-------|
| User message | Plain text | Any career-related question |
| Resume | PDF file | Max 10 MB; text is extracted server-side |

| Output | Format |
|--------|--------|
| Skill gap report | Text list of missing skills |
| General chat reply | Free-form text from Gemini |

---

## API / Function Reference

### Backend endpoints (`http://localhost:8001`)

#### `POST /chat`

Accepts a JSON payload and returns an AI-generated response.

**Request body:**
```json
{
  "message": "What skills am I missing?",
  "pdf_text": "John Doe, Python developer with 2 years experience..."
}
```

**Response:**
```json
{
  "reply": "Based on your resume and the current job market, the following skills are most in demand but missing from your profile: docker, kubernetes, aws, ..."
}
```

**Logic:**
- If `pdf_text` is non-empty → runs `find_skill_gaps()` from Week 2 to compare resume skills against the jobs database, then optionally answers the user's message in context
- If `pdf_text` is empty → sends `message` directly to the Gemini model for general career advice

#### `GET /stats`

Returns aggregated job market data from the SQLite database.

**Response:**
```json
{
  "location_distribution": {"Company A": 4, "Company B": 2},
  "top_skills": {"python": 45, "docker": 32},
  "job_type_distribution": {"Data Engineer": 6, "Software Engineer": 4},
  "jobs": [{"title": "...", "company": "...", "location": "", "skills": []}]
}
```

#### `GET /health`

Returns `{"status": "ok"}` — used to verify the backend is running.

---

### Frontend endpoints (`http://localhost:8000`)

#### `GET /`
Serves the main chat page (`chat_page.html`).

#### `GET /stats`
Serves the statistics dashboard (`stats.html`).

#### `POST /chat`
Receives `multipart/form-data` from the browser (message text + optional PDF file), extracts PDF text using `pypdf`, then proxies the request to the backend `/chat` endpoint.

#### `GET /api/stats`
Proxies the backend `/stats` endpoint and returns the JSON response to the browser.

---

### Key JavaScript functions (`chat_page.html`)

| Function | Purpose |
|----------|---------|
| `sendMessage()` | Reads the text input and optional PDF file, builds a `FormData` object, sends a `POST /chat` request, and renders the reply in the chat history |
| `addMessage(text, role)` | Creates a chat bubble DOM element and appends it to the chat history area |
| `pdfInput` change listener | Updates the filename badge when a PDF is selected |
| `msgInput` keydown listener | Submits the form when Enter is pressed |

---

### Frontend ↔ Backend communication

Both services are on the same Docker bridge network (`app_network`). The frontend resolves the backend by its Docker Compose service name:

```
Browser → POST http://localhost:8000/chat (frontend)
             ↓
         Frontend extracts PDF text, builds JSON payload
             ↓
         POST http://backend:8001/chat  (internal Docker network)
             ↓
         Backend calls Gemini API / Week 2 skill-gap pipeline
             ↓
         JSON response {"reply": "..."} returned to browser
```

The backend URL is configured via the `BACKEND_URL` environment variable — never hardcoded.

---

## Data / Assumptions

### Data sources

| Data | Location | Format |
|------|----------|--------|
| Job listings | `week_1/data/3_gold/jobs.db` | SQLite — columns: `source_id`, `job_title`, `company`, `description`, `tech_stack` |
| Resume | Uploaded by user at runtime | PDF, converted to plain text via `pypdf` |

### Message format between frontend and backend

```
Frontend → Backend (JSON):
  { "message": str, "pdf_text": str }

Backend → Frontend (JSON):
  { "reply": str }        # success
  { "reply": "Error: ..." }  # handled error
```

### Assumptions

- **PDF format** — the resume must be a text-based PDF (not a scanned image). Image-only PDFs will return empty text and no skill gaps will be detected.
- **`tech_stack` column** — skill gap analysis only works if jobs have been tagged by the Week 2 `tag_data.py` script. If `tech_stack` is empty for all rows, the system will report no gaps.
- **PDF size** — capped at 10 MB on the frontend. Larger files are rejected with HTTP 413.
- **Resume text length** — only the first 4 000 characters of the extracted resume text are sent to the LLM to stay within token limits.
- **Gemini free tier** — the default model (`gemini-2.5-flash`) has a daily request quota. If the quota is exhausted, the API returns a 429 error which propagates to the user as an error message.

---

## Testing

### Backend — using curl

```bash
# Health check
curl http://localhost:8001/health

# General chat
curl -X POST http://localhost:8001/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What Python skills are in demand?", "pdf_text": ""}'

# Resume skill gap (replace the pdf_text value with actual resume text)
curl -X POST http://localhost:8001/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "", "pdf_text": "John Doe. Skills: Python, SQL."}'

# Stats endpoint
curl http://localhost:8001/stats
```

### Frontend — manual test cases

| Test | Steps | Expected result |
|------|-------|----------------|
| Send a message | Type in chat box, press Send | Bot reply appears in chat history |
| Enter key | Type message, press Enter | Same as clicking Send |
| Upload PDF | Click 📎, select a `.pdf` file | Filename badge appears below input |
| PDF + message | Upload PDF and type a question, press Send | Skill gap report returned |
| Stats page | Click 📊 Stats link | Charts render with job market data |
| Empty message | Click Send with empty input and no PDF | Nothing happens (guarded in JS) |
| Large PDF | Upload a PDF > 10 MB | Error message: "PDF too large (max 10 MB)" |

### Docker network communication test

```bash
# Confirm frontend can reach backend through Docker network
docker exec week_3-frontend-1 curl -s http://backend:8001/health
# Expected: {"status":"ok"}
```

### How Docker connectivity was verified

The `BACKEND_URL=http://backend:8001` environment variable routes all frontend-to-backend calls through Docker's internal `app_network` bridge. This was verified by checking that `/api/stats` in the browser returns live data from the backend database.

---

## Limitations

| Limitation | Detail |
|------------|--------|
| **No chat history persistence** | Conversation history lives only in the browser's DOM. Refreshing the page clears all messages. |
| **Skill gap accuracy depends on tagging** | If the `tech_stack` column in the database has not been populated by `tag_data.py`, the skill gap analysis returns no results. |
| **Gemini free-tier quota** | `gemini-2.5-flash` allows ~250 requests/day on the free tier. Heavy usage will hit the quota and return a 429 error. |
| **No GPU acceleration** | The Gemini API is used for inference. There is no local GPU acceleration in this configuration. |
| **Single-turn AI context** | Each chat request is stateless — the AI has no memory of previous messages in the conversation. |

---

## Architecture Reflection

### Design Choices

For this project, I separated the system into frontend and backend services instead of putting everything in one file or one application. The frontend mainly handles the web page, PDF upload, text extraction, and sending requests to the backend. The backend handles the AI logic, Gemini API, MCP access, and SQLite queries. I chose this structure because each part has its own responsibility, so it is easier to understand, debug, and modify. I also used Docker containers for each service, so the project can run more consistently on different computers without many setup problems.

One trade-off I made was choosing simplicity and easier deployment instead of building a very advanced system. For example, I used Docker Compose because it is easy to run with one command, but it is not as powerful as Kubernetes for scaling. I also used plain HTML and JavaScript for the frontend because it does not need a complicated setup, but it has fewer features compared to React or Vue. The chat is also stateless, which makes the backend simpler, but it means the AI cannot remember previous messages. Besides that, using Gemini API is easier because I do not need to run a local AI model, but it depends on internet connection and external API usage.

If I had more time, I would improve the system by adding conversation memory so the AI can understand follow-up questions better. I would also rebuild the frontend using React or Vue to make the interface cleaner and easier to manage. Another improvement is deploying the system to the cloud so it can be accessed online with HTTPS and proper secret management. I would also consider storing resume analysis results in a database for future tracking, adding streaming responses to make the chatbot feel faster, and improving PDF parsing so the system can handle scanned or complex resume formats better.
