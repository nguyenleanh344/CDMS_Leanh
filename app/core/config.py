from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/dbname"
    INVENTORY_BASE_URL: str = "http://127.0.0.1:8000"
    POLLING_ENABLED: bool = False
    POLLING_INTERVAL_SECONDS: float = Field(default=30, gt=0)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()