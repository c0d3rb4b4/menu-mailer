"""Application configuration."""

import logging
import sys
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    menu_image_dir: str = "/mnt/menu-images"
    scan_interval_seconds: int = 300

    send_hour: int = 7
    send_minute: int = 0
    timezone: str = "Europe/London"
    skip_weekends: bool = True
    retry_window_minutes: int = 60

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    mail_from: str = ""
    mail_to: str = ""

    bind_host: str = "0.0.0.0"
    bind_port: int = 8082

    log_level: str = "INFO"

    class Config:
        """Pydantic settings configuration."""

        env_file = "/app/config/app.env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    def recipient_list(self) -> list[str]:
        """Return parsed recipient list."""

        return [addr.strip() for addr in self.mail_to.split(",") if addr.strip()]


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""

    return Settings()


def setup_logging() -> None:
    """Configure logging for the application."""

    settings = get_settings()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    log_format = (
        '{"timestamp":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s",'
        '"message":"%(message)s"}'
    )

    logging.basicConfig(
        level=log_level,
        format=log_format,
        datefmt="%Y-%m-%dT%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    logging.getLogger("uvicorn").setLevel(log_level)
    logging.getLogger("uvicorn.access").setLevel(log_level)
    logging.getLogger("uvicorn.error").setLevel(log_level)
