import os


class Settings:
    database_url: str = os.getenv("DATABASE_URL", "postgresql+psycopg://ebfi:ebfi@db:5432/ebfi")
    secret_key: str = os.getenv("SECRET_KEY", "dev-secret-change-me")
    # Fernet key (urlsafe base64, 32 bytes) used to encrypt inspector bank details
    encryption_key: str = os.getenv("ENCRYPTION_KEY", "")
    session_hours: int = int(os.getenv("SESSION_HOURS", "12"))
    cookie_secure: bool = os.getenv("COOKIE_SECURE", "true").lower() == "true"
    upload_dir: str = os.getenv("UPLOAD_DIR", "/data/uploads")
    max_failed_logins: int = 5
    lockout_minutes: int = 15


settings = Settings()
