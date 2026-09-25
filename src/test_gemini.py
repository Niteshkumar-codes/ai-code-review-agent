from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google.genai.errors import APIError
from src.config import Config
from src.gemini_client import generate_test_response


def main() -> None:
    print("==================================================")
    print(" PHASE 2: GEMINI API INTEGRATION TEST")
    print("==================================================")

    env_status = Config.validate()
    if not env_status.get("GEMINI_API_KEY"):
        print("[FAIL] GEMINI_API_KEY is missing or empty in .env file.")
        sys.exit(1)

    print("  [OK] GEMINI_API_KEY detected in configuration.")
    print("  Sending test prompt to Gemini API...")

    try:
        response_text = generate_test_response()
        print("\n--------------------------------------------------")
        print("[SUCCESS] Gemini API Connection Verified!")
        print("Model Response:")
        print(response_text.strip())
        print("--------------------------------------------------")
        print("==================================================")
        sys.exit(0)
    except ValueError as err:
        print(f"\n[FAIL] Configuration Error: {err}")
        sys.exit(1)
    except APIError as err:
        print(f"\n[FAIL] Gemini API Error (Status Code {err.code}): {err.message}")
        sys.exit(1)
    except Exception as err:
        print(f"\n[FAIL] Unexpected Error: {type(err).__name__} - {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
