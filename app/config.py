import os

class Config:
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"

    ALLOWED_ORIGINS: list[str] = [
        o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()
    ]


    PROXY_SECRET="ubjcYpnoFHTqr4hPaO0k88S3JqzI2kLRzcevTcA2ZNE"

    REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "10"))
    
    MAX_CONTENT_LENGTH: int = int(os.getenv("MAX_CONTENT_LENGTH", str(10 * 1024 * 1024)))  # 10 MB