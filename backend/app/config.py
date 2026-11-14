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
    def allowed_origins(self) -> list[str]:
        """Return configured origins, accepting both localhost and 127.0.0.1."""
        origins = [origin.strip() for origin in self.frontend_origin.split(",") if origin.strip()]
        for origin in list(origins):
            if "localhost" in origin:
                origins.append(origin.replace("localhost", "127.0.0.1"))
            elif "127.0.0.1" in origin:
                origins.append(origin.replace("127.0.0.1", "localhost"))
        return list(dict.fromkeys(origins))

    @property
    def storage_dir_path(self) -> Path:
        return Path(self.storage_dir).resolve()

settings = Settings()
