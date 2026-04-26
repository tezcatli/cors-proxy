import os

class Config:
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"

    ALLOWED_ORIGINS: list[str] = [
        o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()
    ]

    REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "10"))
    MAX_CONTENT_LENGTH: int = int(os.getenv("MAX_CONTENT_LENGTH", str(10 * 1024 * 1024)))

    # Admin
    ADMIN_KEY: str = os.getenv("ADMIN_KEY", "")

    # IGDB
    IGDB_CLIENT_ID:     str = os.getenv("IGDB_CLIENT_ID", "")
    IGDB_CLIENT_SECRET: str = os.getenv("IGDB_CLIENT_SECRET", "")

    # RSS
    RSS_TTL_MINUTES: int = int(os.getenv("RSS_TTL_MINUTES", "60"))

    # Auth
    JWT_SECRET: str      = os.getenv("JWT_SECRET", "dev-insecure-change-me")
    JWT_TTL_SECONDS: int = int(os.getenv("JWT_TTL_SECONDS", str(7 * 24 * 3600)))  # 7 days
    RESET_TTL_SECONDS: int = 3600  # 1 hour, not configurable

    # Password reset e-mail
    RESET_BASE_URL: str = os.getenv("RESET_BASE_URL", "http://localhost:5000")
    SMTP_HOST: str      = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int      = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str      = os.getenv("SMTP_USER", "")
    SMTP_PASS: str      = os.getenv("SMTP_PASS", "")
    SMTP_FROM: str      = os.getenv("SMTP_FROM", "noreply@example.com")
