# SkillScope – API Contract

This document defines the HTTP endpoints the **backend** must expose for the **frontend** to work correctly.

> Base URL is configured via the `BACKEND_URL` environment variable (default: `http://localhost:8001`).

---

## Endpoints Required

### 1. `GET /stats`

Returns aggregate market data for the Stats page and the Analyze flow.

**Response:**
```json
{
  "top_skills": {
    "python": 45,
    "sql": 30,
    "aws": 28,
    "docker": 22
  },
  "location_distribution": {
    "ABC Company": 5,
    "XYZ Sdn Bhd": 3
  },
  "job_type_distribution": {
    "AI Engineer": 12,
    "Data Scientist": 8,
    "Software Engineer": 6
  },
  "jobs": [
    {
      "title": "AI Engineer",
      "company": "ABC Company",
      "location": "Kuala Lumpur",
      "salary": "MYR 5,000 - MYR 8,000",
      "actual_posted_date": "2026-05-30",
      "tech_stack": "Python, Docker, AWS"
    }
  ]
}
```

**Notes:**
- `top_skills` keys are skill names (lowercase), values are job count — used for the bar chart and skill matching.
- `jobs` array feeds the stats table. Each entry needs at minimum: `title`, `company`, `location`, `tech_stack`, `salary`, `actual_posted_date`.
- `location_distribution` is currently used as "Top Hiring Companies" (label mismatch from week3 backend — fix when migrating).

---

### 2. `POST /chat`

Accepts a structured AI prompt and returns a Gemini-generated response.

**Request body (JSON):**
```json
{
  "message": "<prompt string>",
  "pdf_text": ""
}
```

**Response:**
```json
{
  "reply": "{\"match_score\": 72, \"missing_skills\": [{\"skill\": \"Docker\", \"priority\": \"high\"}], \"ai_recommendation\": \"...\", \"limitations\": \"...\"}"
}
```

**Notes:**
- `reply` must be a string. The frontend parses it as JSON internally.
- The frontend sends a structured prompt asking for exactly this JSON shape inside `reply`:
  ```
  {"match_score": <0-100>, "missing_skills": [{"skill": "...", "priority": "high|medium|low"}], "ai_recommendation": "...", "limitations": "..."}
  ```
- Timeout is set to 120s on the frontend side.

---

### 3. `GET /roles`

Returns a list of distinct job titles for the Target Role dropdown.

**Response:**
```json
{
  "roles": [
    "AI Engineer",
    "Data Scientist",
    "Software Engineer",
    "Machine Learning Engineer"
  ]
}
```

**Notes:**
- Values should be human-readable (title case preferred).
- If this endpoint is unavailable, the frontend falls back to a preset list automatically — no error shown to user.

---

### 4. `GET /locations`

Returns a list of distinct locations for the Location dropdown.

**Response:**
```json
{
  "locations": [
    "Kuala Lumpur",
    "Selangor",
    "Cyberjaya, Selangor",
    "Penang",
    "Johor Bahru"
  ]
}
```

**Notes:**
- Same fallback behaviour as `/roles` — frontend uses preset list if this endpoint is unavailable.

---

## Future Endpoints (not yet implemented)

These are planned for when the richer database schema (`salary`, `actual_posted_date`) is ready:

### `GET /salary-stats`

**Planned response:**
```json
{
  "median": 7500,
  "min": 3000,
  "max": 20000,
  "distribution": {
    "MYR 3,000–5,000": 18,
    "MYR 5,000–8,000": 42,
    "MYR 8,000–12,000": 31,
    "MYR 12,000+": 9
  }
}
```

### `GET /trends`

**Planned response:**
```json
{
  "by_week": {
    "2026-05-05": 12,
    "2026-05-12": 18,
    "2026-05-19": 24,
    "2026-05-26": 31
  }
}
```

---

## Database Schema Reference

Fields available in `jobs_database.db` after the full pipeline runs:

| Column | Type | Example | Used by frontend? |
|---|---|---|---|
| `job_id` | TEXT | "26592036" | ❌ |
| `title` | TEXT | "Senior Engineer, Data Science" | ✅ via `/stats` jobs array |
| `company` | TEXT | "ABC Company" | ✅ via `/stats` location_distribution |
| `location` | TEXT | "Kuala Lumpur" | ✅ via `/roles`, `/stats` jobs |
| `salary` | TEXT | "MYR 5,000 - MYR 8,000" | ✅ via `/stats` jobs array |
| `posted_date` | TEXT | "2 days ago" | ❌ |
| `actual_posted_date` | TEXT | "2026-05-30" | ✅ via `/stats` jobs array |
| `description` | TEXT | "Full job description..." | ❌ (used internally by pipeline) |
| `tech_stack` | TEXT | "Python, Docker, AWS" | ✅ via `/stats` top_skills + jobs |
