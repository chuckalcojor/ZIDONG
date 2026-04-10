from dataclasses import dataclass
import os

from dotenv import load_dotenv


load_dotenv()


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


@dataclass
class Settings:
    app_env: str
    app_timezone: str
    cutoff_time: str
    telegram_bot_token: str
    telegram_webhook_secret: str
    supabase_url: str
    supabase_service_role_key: str
    flask_secret_key: str
    dashboard_admin_user: str
    dashboard_admin_password: str
    dashboard_data_mode: str
    liveconnect_webhook_secret: str
    anarvet_webhook_secret: str
    new_client_form_webhook_secret: str
    whatsapp_webhook_verify_token: str
    whatsapp_access_token: str
    whatsapp_phone_number_id: str
    openai_api_key: str
    openai_model: str
    openai_fallback_model: str
    openai_enable_fallback: bool


settings = Settings(
    app_env=os.getenv("APP_ENV", "development"),
    app_timezone=os.getenv("APP_TIMEZONE", "America/Bogota"),
    cutoff_time=os.getenv("CUTOFF_TIME", "17:30"),
    telegram_bot_token=required_env("TELEGRAM_BOT_TOKEN"),
    telegram_webhook_secret=required_env("TELEGRAM_WEBHOOK_SECRET"),
    supabase_url=required_env("SUPABASE_URL"),
    supabase_service_role_key=required_env("SUPABASE_SERVICE_ROLE_KEY"),
    flask_secret_key=os.getenv("FLASK_SECRET_KEY", "dev-only-change-me"),
    dashboard_admin_user=os.getenv("DASHBOARD_ADMIN_USER", "admin"),
    dashboard_admin_password=os.getenv("DASHBOARD_ADMIN_PASSWORD", "admin123"),
    dashboard_data_mode=os.getenv("DASHBOARD_DATA_MODE", "mock").strip().lower(),
    liveconnect_webhook_secret=os.getenv("LIVECONNECT_WEBHOOK_SECRET", ""),
    anarvet_webhook_secret=os.getenv("ANARVET_WEBHOOK_SECRET", ""),
    new_client_form_webhook_secret=os.getenv("NEW_CLIENT_FORM_WEBHOOK_SECRET", ""),
    whatsapp_webhook_verify_token=os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", ""),
    whatsapp_access_token=os.getenv("WHATSAPP_ACCESS_TOKEN", ""),
    whatsapp_phone_number_id=os.getenv("WHATSAPP_PHONE_NUMBER_ID", ""),
    openai_api_key=os.getenv("OPENAI_API_KEY", ""),
    openai_model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
    openai_fallback_model=os.getenv("OPENAI_FALLBACK_MODEL", "gpt-5-mini"),
    openai_enable_fallback=os.getenv("OPENAI_ENABLE_FALLBACK", "true").strip().lower()
    in {"1", "true", "yes", "on"},
)
