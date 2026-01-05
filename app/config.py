from typing import Optional
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str

    # Redis (for Celery)
    redis_url: str = "redis://localhost:6379/0"

    # Google AI (GenAI SDK)
    google_api_key: str  # Get from https://aistudio.google.com/app/apikey

    # Google Vertex AI (legacy - keeping for backward compatibility)
    google_cloud_project: Optional[str] = None
    google_cloud_location: str = "us-central1"
    google_application_credentials_json: Optional[str] = None

    # JWT Authentication
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440  # 24 hours

    # App Settings
    debug: bool = False
    cors_origins: str = "http://localhost:3000"

    # Follow-up Settings (in hours)
    followup_check_interval_hours: int = 4  # How often to check if follow-up needed
    followup_inactivity_hours: int = 24  # Send follow-up if no message in X hours
    followup_plan_checkin_hours: int = 48  # Check on plan progress every X hours

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
