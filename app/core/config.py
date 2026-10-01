from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/dbname"
    INVENTORY_BASE_URL: str = "http://127.0.0.1:8000"
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()