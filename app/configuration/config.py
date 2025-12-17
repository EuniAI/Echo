from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", env_prefix="PROMETHEUS_"
    )

    # Logging
    LOGGING_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

    WORKING_DIRECTORY: str

    # LLM models
    ADVANCED_MODEL: str
    BASE_MODEL: str

    # API Keys
    ANTHROPIC_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    OPENAI_FORMAT_BASE_URL: Optional[str] = None
    OPENAI_FORMAT_API_KEY: Optional[str] = None

    # Model parameters
    ADVANCED_MODEL_TEMPERATURE: Optional[float] = None

    BASE_MODEL_TEMPERATURE: Optional[float] = None

    # CRA URL
    CRA_BASE_URL: str


settings = Settings()
