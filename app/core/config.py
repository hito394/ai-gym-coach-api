from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_env: str = "development"
    api_prefix: str = "/v1"
    database_url: str = "sqlite:///./app.db"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"


@lru_cache
def get_settings() -> Settings:
    return Settings()
