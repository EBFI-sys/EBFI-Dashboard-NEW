import os


class Settings:
    database_url: str = os.getenv("DATABASE_URL", "postgresql+psycopg://ebfi:ebfi@db:5432/ebfi")
    secret_key: str = os.getenv("SECRET_KEY", "dev-secret-change-me")
    # Fernet key (urlsafe base64, 32 bytes) used to encrypt inspector bank details
    encryption_key: str = os.getenv("ENCRYPTION_KEY", "")
    session_hours: int = int(os.getenv("SESSION_HOURS", "12"))
    cookie_secure: bool = os.getenv("COOKIE_SECURE", "true").lower() == "true"
    upload_dir: str = os.getenv("UPLOAD_DIR", "/data/uploads")
    # Microsoft 365 (Entra app «EBFI ERP» with Sites.Selected on the admin's OneDrive); empty = files feature off
    ms_tenant_id: str = os.getenv("MS_TENANT_ID", "")
    ms_client_id: str = os.getenv("MS_CLIENT_ID", "")
    ms_client_secret: str = os.getenv("MS_CLIENT_SECRET", "")
    ms_site_id: str = os.getenv("MS_SITE_ID", "")
    ms_root: str = os.getenv("MS_ROOT", "EBFI")  # top folder in that OneDrive
    # Telegram bot for the morning digest (@BotFather); empty = digest off
    telegram_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    digest_time: str = os.getenv("DIGEST_TIME", "09:00")  # India time
    fx_source: str = os.getenv("FX_SOURCE", "https://www.msei.in/markets/currency/historical-data/rbireferenceratearchives")
    max_failed_logins: int = 5
    lockout_minutes: int = 15


settings = Settings()
