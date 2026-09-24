import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")


class Config:
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()
    GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "").strip()
    MONGODB_URI: str = os.getenv("MONGODB_URI", "").strip()

    @classmethod
    def validate(cls) -> dict[str, bool]:
        return {
            "GEMINI_API_KEY": bool(cls.GEMINI_API_KEY),
            "GITHUB_TOKEN": bool(cls.GITHUB_TOKEN),
            "MONGODB_URI": bool(cls.MONGODB_URI),
        }
