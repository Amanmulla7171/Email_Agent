import os
from functools import lru_cache
from typing import Optional, List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables and .env file."""

    PROJECT_NAME: str = "Email Agent API"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"

    # Server configuration
    HOST: str = "0.0.0.0"
    PORT: int = int(os.environ.get("PORT", 8000))

    # Security: Optional API secret key for endpoint protection in production
    API_SECRET_KEY: Optional[str] = None

    # LLM Settings
    GROQ_API_KEY: Optional[str] = None
    groq_api_key: Optional[str] = None

    # Email / SMTP Settings
    SMTP_SERVER: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_EMAIL: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SENDER_EMAIL: Optional[str] = None
    EMAIL_PASSWORD: Optional[str] = None

    # CORS settings
    CORS_ORIGINS: List[str] = ["*"]

    # File Attachment Security Settings
    UPLOAD_DIR: str = os.environ.get("UPLOAD_DIR", "storage/uploads")
    MAX_ATTACHMENT_SIZE_MB: int = int(os.environ.get("MAX_ATTACHMENT_SIZE_MB", 10))
    ALLOWED_ATTACHMENT_EXTENSIONS: List[str] = [".pdf", ".docx", ".doc", ".txt"]
    ALLOWED_ATTACHMENT_MIME_TYPES: List[str] = [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
        "text/plain",
        "application/octet-stream",
    ]

    # Default Resume / Document Attachment Settings
    DEFAULT_ATTACHMENT_PATH: str = os.environ.get("DEFAULT_ATTACHMENT_PATH", "storage/default_attachments/Aman_Mulla_Resume.pdf")
    ATTACH_DEFAULT_BY_DEFAULT: bool = os.environ.get("ATTACH_DEFAULT_BY_DEFAULT", "true").lower() in ("true", "1", "yes")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


@lru_cache()
def get_settings() -> Settings:
    """Returns cached settings instance."""
    return Settings()
