from google.genai import types
from google.genai.errors import APIError
from src.config import Config
from src.gemini_client import get_gemini_client

REVIEW_SYSTEM_INSTRUCTION = """You are an expert software engineer and code reviewer.
Perform a strict, high-quality code review of the provided git diff.

Instructions:
1. Review only the supplied diff changes.
2. Identify concrete issues in four areas:
   - Potential bugs and correctness risks
   - Security concerns or vulnerabilities
   - Code quality and structural flaws
   - Maintainability and readability concerns
3. Clearly separate critical risks (bugs, security flaws) from minor style or refactoring suggestions.
4. For every issue, explain WHY it is a problem and provide a realistic code fix where appropriate.
5. Do not invent non-existent files, surrounding architecture, or execution outputs.
6. If the diff lacks sufficient context to confirm an issue, state the ambiguity explicitly instead of making unverified assumptions.
7. Keep the tone concise, professional, and practical."""


def review_code_diff(
    diff: str,
    context: str | None = None,
    model_name: str = Config.GEMINI_MODEL,
) -> str:
    if not diff or not diff.strip():
        raise ValueError("Code diff cannot be empty or contain only whitespace.")

    client = get_gemini_client()

    prompt_parts = []
    if context and context.strip():
        prompt_parts.append(f"Context:\n{context.strip()}")
    prompt_parts.append(f"Diff:\n```diff\n{diff.strip()}\n```")

    full_prompt = "\n\n".join(prompt_parts)

    try:
        config = types.GenerateContentConfig(
            system_instruction=REVIEW_SYSTEM_INSTRUCTION,
            temperature=0.2,
        )
        response = client.models.generate_content(
            model=model_name,
            contents=full_prompt,
            config=config,
        )
    except APIError as err:
        raise RuntimeError(f"Gemini API error during code review: {err.message}") from err
    except Exception as err:
        raise RuntimeError(f"Unexpected error calling Gemini API: {err}") from err

    if not response.text or not response.text.strip():
        raise RuntimeError("Gemini API returned an empty response.")

    return response.text
