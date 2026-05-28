FROM python:3.14.4-bookworm

WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./

RUN pip install uv && uv sync --frozen --no-dev

COPY src/ ./src/

EXPOSE 8001

ENTRYPOINT ["uv", "run", "uvicorn"]
CMD ["src.app:app", "--host", "0.0.0.0", "--port", "8001"]
