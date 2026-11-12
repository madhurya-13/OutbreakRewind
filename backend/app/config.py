from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = "sqlite:///./orion.db"
    frontend_origin: str = "http://localhost:5173"
    storage_dir: str = "./evidence_storage"
    max_upload_bytes: int = 15 * 1024 * 1024
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def storage_dir_path(self) -> Path:
        return Path(self.storage_dir).resolve()

settings = Settings()
