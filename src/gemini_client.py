from google import genai
from google.genai import types
from src.config import Config

# Timeout for the test connectivity request.
# NOTE: google-genai SDK HttpOptions.timeout unit is MILLISECONDS (divided by
# 1000 internally before being passed to httpx). 30 * 1000 = 30 000 ms = 30 s.
_TEST_TIMEOUT_MS: int = 30 * 1000


def get_gemini_client() -> genai.Client:
    if not Config.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is missing or empty in configuration.")
    return genai.Client(api_key=Config.GEMINI_API_KEY)


def generate_test_response(
    prompt: str = "Respond with: 'Gemini API connection verified successfully!'",
    model_name: str = Config.GEMINI_MODEL,
) -> str:
    client = get_gemini_client()
    config = types.GenerateContentConfig(
        # Suppress the AFC advisory warning: models.generate_content does not
        # use automatic function calling, so disable it explicitly.
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        # Hard timeout so the test fails fast on network/routing problems
        # rather than hanging indefinitely.
        http_options=types.HttpOptions(timeout=_TEST_TIMEOUT_MS),
        temperature=0.0,
    )
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=config,
    )
    if not response.text or not response.text.strip():
        raise RuntimeError("Gemini API returned an empty response.")
    return response.text
