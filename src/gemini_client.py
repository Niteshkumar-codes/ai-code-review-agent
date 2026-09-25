from google import genai
from src.config import Config


def get_gemini_client() -> genai.Client:
    if not Config.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is missing or empty in configuration.")
    return genai.Client(api_key=Config.GEMINI_API_KEY)


def generate_test_response(
    prompt: str = "Respond with: 'Gemini API connection verified successfully!'",
    model_name: str = "gemini-3.5-flash",
) -> str:
    client = get_gemini_client()
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
    )
    return response.text
