from __future__ import annotations

from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


def load_dotenv_file() -> Optional[Path]:
    """
    Load environment variables from the repository-level .env file once at startup.

    Existing environment variables take precedence; .env provides defaults.
    """
    repo_root = Path(__file__).resolve().parents[1]
    dotenv_path = repo_root / ".env"
    if not dotenv_path.exists():
        return None
    load_dotenv(dotenv_path, override=False)
    return dotenv_path
