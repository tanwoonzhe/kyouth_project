"""Prompt model router — Gemini API or Ollama."""

import os
import subprocess
from typing import NamedTuple

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

GEMINI_MODELS = {
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3-flash",
}


class ModelResponse(NamedTuple):
    text: str
    tokens: int


def prompt_model_full(
    model: str, prompt: str, temperature: float | None = None
) -> ModelResponse:
    if not model.strip():
        return ModelResponse(text="Error: model name is empty.", tokens=0)
    if not prompt.strip():
        return ModelResponse(text="Error: prompt is empty.", tokens=0)

    try:
        if model in GEMINI_MODELS:
            return _prompt_gemini_full(model, prompt, temperature)

        text = _prompt_ollama(model, prompt)
        estimated = len(prompt.split()) + len(text.split())
        return ModelResponse(text=text, tokens=estimated)

    except Exception as error:
        return ModelResponse(text=f"Error: {error}", tokens=0)


def prompt_model(model: str, prompt: str, temperature: float | None = None) -> str:
    return prompt_model_full(model, prompt, temperature).text


def _prompt_gemini_full(
    model: str, prompt: str, temperature: float | None
) -> ModelResponse:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return ModelResponse(text="Error: GOOGLE_API_KEY is not set.", tokens=0)

    client = genai.Client(api_key=api_key)
    config = (
        types.GenerateContentConfig(temperature=temperature)
        if temperature is not None
        else None
    )
    response = client.models.generate_content(
        model=model, contents=prompt, config=config
    )
    text = response.text.strip() if response.text else ""
    tokens = 0
    if response.usage_metadata:
        tokens = response.usage_metadata.total_token_count or 0
    return ModelResponse(text=text, tokens=tokens)


def _prompt_ollama(model: str, prompt: str) -> str:
    result = subprocess.run(
        ["ollama", "run", model, prompt],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        check=False,
    )
    if result.returncode != 0:
        return f"Error: {result.stderr.strip()}"
    return result.stdout.strip()
