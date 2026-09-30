from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/callback"
    database_url: str = "sqlite:///./data/app.db"
    session_secret: str = "change-me-local-only"
    host: str = "127.0.0.1"
    port: int = 8000
    root_folder_id: str = ""
    frontend_url: str = "http://localhost:8000"
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

settings = Settings()
DATA_DIR = BASE_DIR / "data"
TOKEN_DIR = BASE_DIR / "tokens"
FRONTEND_DIR = BASE_DIR / "frontend"
DATA_DIR.mkdir(exist_ok=True)
TOKEN_DIR.mkdir(exist_ok=True)
