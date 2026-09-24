import importlib.metadata
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import Config


def verify_installed_packages() -> bool:
    required_packages = [
        "python-dotenv",
        "google-genai",
        "PyGithub",
        "pydantic",
        "tenacity",
    ]
    print("--- 1. Package Installation Verification ---")
    all_installed = True
    for pkg in required_packages:
        try:
            version = importlib.metadata.version(pkg)
            print(f"  [OK] {pkg:15s} Version: {version}")
        except importlib.metadata.PackageNotFoundError:
            print(f"  [MISSING] {pkg:15s} Not found!")
            all_installed = False
    return all_installed


def verify_environment_variables() -> dict[str, bool]:
    print("\n--- 2. Environment Variables Verification ---")
    status = Config.validate()
    for key, is_present in status.items():
        state_str = "CONFIGURED" if is_present else "NOT SET"
        symbol = "[OK]" if is_present else "[WARN]"
        print(f"  {symbol} {key:15s} -> {state_str}")
    return status


def main() -> None:
    print("==================================================")
    print(" PHASE 1: ENVIRONMENT & CONFIGURATION CHECK")
    print("==================================================")
    print(f"Python Executable: {sys.executable}")
    print(f"Python Version   : {sys.version.split()[0]}\n")

    pkgs_ok = verify_installed_packages()
    env_status = verify_environment_variables()

    print("\n--------------------------------------------------")
    if pkgs_ok:
        print("[SUCCESS] Environment Verification Passed!")
        if not env_status["GEMINI_API_KEY"]:
            print("\n[NOTE]: Ensure GEMINI_API_KEY is configured in .env for Phase 2.")
    else:
        print("[FAIL] Required packages are missing from the environment.")
    print("==================================================")


if __name__ == "__main__":
    main()
