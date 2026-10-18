from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    jwt_secret: str = "dev-secret-change-me"
    jwt_expire_minutes: int = 60
    database_url: str = "sqlite:///./reviewpilot.db"
    cors_origins: str = "*"
    rate_limit_per_minute: int = 10
    max_review_chars: int = 2000
    max_policy_bytes: int = 100_000

    admin_email: str = "admin@reviewpilot.com"
    admin_password: str = "Admin@12345"
    demo_owner_email: str = "owner@reviewpilot.com"
    demo_owner_password: str = "Owner@12345"


settings = Settings()
