from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    # Anchor local defaults to the backend directory so the API, Alembic, and
    # pytest behave the same whether they are started from the repository root
    # or from backend/.
    database_url: str = f"sqlite:///{(BACKEND_DIR / 'orion.db').as_posix()}"
    frontend_origin: str = "http://localhost:5173"
    storage_dir: str = str(BACKEND_DIR / "evidence_storage")
    max_upload_bytes: int = 15 * 1024 * 1024
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def storage_dir_path(self) -> Path:
        return Path(self.storage_dir).resolve()

settings = Settings()
