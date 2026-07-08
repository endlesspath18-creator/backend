import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    PROJECT_NAME: str = "EndlessPath Services API"
    PORT: int = 5000
    ENVIRONMENT: str = "development"

    # JWT
    JWT_SECRET: str = "6f9c2e8b4a1d7c5e9f3b8a2d6c1e7f4b9d3a6c8e1f5b7a2d9c4e6f1b3a8d5c7"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # Database
    DATABASE_URL: str = Field(default="postgresql+asyncpg://postgres:postgres@localhost:5432/postgres")

    # Razorpay
    RAZORPAY_KEY_ID: str = "rzp_test_xxxxxxxxx"
    RAZORPAY_KEY_SECRET: str = "xxxxxxxxxxxxxxxxxxxxxxxxxxx"
    RAZORPAY_WEBHOOK_SECRET: str = ""

    # Firebase (Optional)
    FIREBASE_CREDENTIALS_JSON: str = ""

    # Pydantic Configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
