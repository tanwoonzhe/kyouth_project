FROM python:3.14.4-bookworm

WORKDIR /app

COPY week_3/backend/pyproject.toml week_3/backend/uv.lock week_3/backend/.python-version ./

RUN pip install uv && uv sync --frozen --no-dev

COPY week_3/backend/src/ ./src/
# Use week_2 source files directly — no duplicate copies needed
COPY week_2/find_skill_gaps.py week_2/mcp_server.py week_2/prompt_model.py week_2/rate_limits.txt ./src/week_2/

EXPOSE 8001

ENTRYPOINT ["uv", "run", "uvicorn"]
CMD ["src.app:app", "--host", "0.0.0.0", "--port", "8001"]
