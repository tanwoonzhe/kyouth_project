import argparse
import os
import subprocess
from typing import NamedTuple

from dotenv import load_dotenv
from google import genai
from google.genai import types


# Load environment variables from .env file (e.g., GOOGLE_API_KEY)
load_dotenv()


# These model names are routed to the Google Gemini API.
# Any other model name (e.g., llama3.1, phi3) is sent to the local Ollama server.
GEMINI_MODELS = {
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3-flash",
}


# BONUS: NamedTuple to return both the response text and total token count.
# This lets callers track token usage for benchmarking and rate-limit management.
class ModelResponse(NamedTuple):
    text: str
    tokens: int


def prompt_model_full(
    model: str, prompt: str, temperature: float | None = None
) -> ModelResponse:
    """Call a model and return both text and token count."""
    # Guard against empty inputs to avoid wasting API calls
    if not model.strip():
        return ModelResponse(text="Error: model name is empty.", tokens=0)

    if not prompt.strip():
        return ModelResponse(text="Error: prompt is empty.", tokens=0)

    try:
        # Route to the correct backend based on model name
        if model in GEMINI_MODELS:
            return _prompt_gemini_full(model, prompt, temperature)

        # Fallback: call Ollama for local models
        text = _prompt_ollama(model, prompt)
        # Ollama does not return token counts, so we estimate from word count
        estimated = len(prompt.split()) + len(text.split())
        return ModelResponse(text=text, tokens=estimated)

    except Exception as error:
        return ModelResponse(text=f"Error: {error}", tokens=0)


# Public interface: returns only the text string (not token count)
def prompt_model(model: str, prompt: str, temperature: float | None = None) -> str:
    return prompt_model_full(model, prompt, temperature).text


def _prompt_gemini_full(
    model: str, prompt: str, temperature: float | None
) -> ModelResponse:
    # Read API key from environment — never hardcode secrets in source code
    api_key = os.getenv("GOOGLE_API_KEY")

    if not api_key:
        return ModelResponse(text="Error: GOOGLE_API_KEY is not set.", tokens=0)

    client = genai.Client(api_key=api_key)
    # Only set temperature config if explicitly provided; None uses model default
    config = (
        types.GenerateContentConfig(temperature=temperature)
        if temperature is not None
        else None
    )
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=config,
    )

    text = response.text.strip() if response.text else ""
    # BONUS: Read actual token count from the API response metadata
    tokens = 0
    if response.usage_metadata:
        tokens = response.usage_metadata.total_token_count or 0

    return ModelResponse(text=text, tokens=tokens)


def _prompt_ollama(model: str, prompt: str) -> str:
    # Call the local Ollama CLI as a subprocess; capture stdout and stderr
    result = subprocess.run(
        ["ollama", "run", model, prompt],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        check=False,  # Do not raise on non-zero exit; we handle it manually
    )

    if result.returncode != 0:
        return f"Error: {result.stderr.strip()}"

    return result.stdout.strip()


def main() -> None:
    # BONUS: Accept model and prompt as CLI arguments for flexible testing
    # Usage: uv run prompt_model.py llama3.1 "tell me a joke"
    parser = argparse.ArgumentParser()
    parser.add_argument("model", help="Model name, for example llama3.1")
    parser.add_argument("prompt", help="Prompt to send to the model")
    args = parser.parse_args()

    response = prompt_model(args.model, args.prompt)

    print("--- RESPONSE ---")
    print(response)


if __name__ == "__main__":
    main()
