"""Mail delivery logic for menu-mailer."""

from __future__ import annotations

import logging
import smtplib
import urllib.request
from datetime import date, datetime, time as dt_time, timedelta, timezone
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode, urlparse, urlunparse
from zoneinfo import ZoneInfo

from src.config import Settings
from src.menu_index import MenuIndex


CHECK_INTERVAL_SECONDS = 30
SEND_RETRY_INTERVAL_SECONDS = 120
MISSING_LOG_INTERVAL_SECONDS = 300


class MenuMailer:
    """Scheduler and sender for daily menu emails."""

    def __init__(self, settings: Settings, index: MenuIndex) -> None:
        self._settings = settings
        self._index = index
        self._logger = logging.getLogger("menu-mailer")
        self._timezone = self._load_timezone(settings.timezone)

        self._last_sent_date: Optional[date] = None
        self._last_sent_at: Optional[datetime] = None
        self._last_attempt_at: Optional[datetime] = None
        self._last_result: str = "idle"
        self._last_error: str = ""
        self._last_handled_date: Optional[date] = None
        self._last_missing_log_at: Optional[datetime] = None

    def _load_timezone(self, tz_name: str) -> timezone:
        try:
            return ZoneInfo(tz_name)
        except Exception:
            self._logger.warning("Invalid timezone '%s', falling back to UTC", tz_name)
            return timezone.utc

    def tick(self) -> None:
        """Perform a single scheduler tick."""

        now = datetime.now(self._timezone)
        today = now.date()

        if self._settings.skip_weekends and today.weekday() >= 5:
            if self._last_handled_date != today:
                self._logger.info("Skipping weekend send for %s", today.isoformat())
                self._last_result = "skipped_weekend"
                self._last_handled_date = today
            return

        send_time = dt_time(hour=self._settings.send_hour, minute=self._settings.send_minute)
        send_start = datetime.combine(today, send_time, tzinfo=self._timezone)
        send_deadline = send_start + timedelta(minutes=self._settings.retry_window_minutes)

        if now < send_start:
            return

        if self._last_sent_date == today:
            return

        if now > send_deadline:
            if self._last_handled_date != today:
                self._logger.warning(
                    "Send window missed for %s (deadline %s)",
                    today.isoformat(),
                    send_deadline.isoformat(),
                )
                self._last_result = "missed"
                self._last_handled_date = today
            return

        if self._last_attempt_at:
            elapsed = (now - self._last_attempt_at).total_seconds()
            if elapsed < SEND_RETRY_INTERVAL_SECONDS:
                return

        image_path = self._index.get_image_path(today.isoformat())
        if image_path is None or not image_path.exists():
            self._log_missing_image(now, today)
            self._last_result = "waiting_image"
            return

        if not self._smtp_ready():
            self._last_result = "config_error"
            return

        self._last_attempt_at = now
        try:
            self._send_email(today, image_path)
        except Exception as exc:
            self._last_error = str(exc)
            self._last_result = "error"
            self._logger.exception("Failed to send menu email")
            return

        self._last_sent_date = today
        self._last_sent_at = now
        self._last_result = "sent"
        self._last_error = ""
        self._last_handled_date = today
        self._logger.info("Menu email sent for %s", today.isoformat())
        self._notify_sent(today)

    def send_now(self) -> dict:
        """Send the menu email immediately for today's date."""

        now = datetime.now(self._timezone)
        today = now.date()

        try:
            self._index.scan()
        except Exception:
            self._logger.exception("Failed to refresh menu image index")

        image_path = self._index.get_image_path(today.isoformat())
        if image_path is None or not image_path.exists():
            detail = f"Menu image not found for {today.isoformat()}"
            self._last_result = "missing_image"
            self._last_error = detail
            return {"status": "missing_image", "date": today.isoformat(), "detail": detail}

        if not self._smtp_ready():
            self._last_result = "config_error"
            return {"status": "config_error", "detail": self._last_error}

        self._last_attempt_at = now
        try:
            self._send_email(today, image_path)
        except Exception as exc:
            self._last_error = str(exc)
            self._last_result = "error"
            self._logger.exception("Failed to send menu email")
            return {"status": "error", "detail": self._last_error}

        self._last_sent_date = today
        self._last_sent_at = now
        self._last_result = "sent"
        self._last_error = ""
        self._last_handled_date = today

        self._notify_sent(today)

        return {
            "status": "sent",
            "date": today.isoformat(),
            "sent_at": now.isoformat(),
        }

    def _log_missing_image(self, now: datetime, today: date) -> None:
        if self._last_missing_log_at:
            elapsed = (now - self._last_missing_log_at).total_seconds()
            if elapsed < MISSING_LOG_INTERVAL_SECONDS:
                return
        self._logger.info("Menu image not found for %s, will retry", today.isoformat())
        self._last_missing_log_at = now

    def _smtp_ready(self) -> bool:
        missing = []
        if not self._settings.smtp_host:
            missing.append("SMTP_HOST")
        if not self._settings.mail_from:
            missing.append("MAIL_FROM")
        if not self._settings.recipient_list():
            missing.append("MAIL_TO")

        if missing:
            self._last_error = "Missing settings: " + ", ".join(missing)
            if self._last_result != "config_error":
                self._logger.error(self._last_error)
            return False

        if self._settings.smtp_username and not self._settings.smtp_password:
            self._logger.warning("SMTP_USERNAME is set but SMTP_PASSWORD is empty")

        return True

    def _send_email(self, menu_date: date, image_path: Path) -> None:
        recipients = self._settings.recipient_list()
        message = self._build_message(menu_date, image_path, recipients)
        smtp = None

        try:
            if self._settings.smtp_use_tls and self._settings.smtp_port == 465:
                smtp = smtplib.SMTP_SSL(
                    self._settings.smtp_host,
                    self._settings.smtp_port,
                    timeout=10,
                )
            else:
                smtp = smtplib.SMTP(
                    self._settings.smtp_host,
                    self._settings.smtp_port,
                    timeout=10,
                )
                smtp.ehlo()
                if self._settings.smtp_use_tls:
                    smtp.starttls()
                    smtp.ehlo()

            if self._settings.smtp_username:
                smtp.login(self._settings.smtp_username, self._settings.smtp_password)

            smtp.send_message(message, from_addr=self._settings.mail_from, to_addrs=recipients)
        finally:
            if smtp is not None:
                try:
                    smtp.quit()
                except Exception:
                    self._logger.warning("SMTP session did not close cleanly")

    def _build_message(
        self, menu_date: date, image_path: Path, recipients: list[str]
    ) -> MIMEMultipart:
        menu_link = self._build_menu_link(menu_date)
        subject = self._format_subject(menu_date)
        message = MIMEMultipart("related")
        message["Subject"] = subject
        message["From"] = self._settings.mail_from
        message["To"] = ", ".join(recipients)

        alternative = MIMEMultipart("alternative")
        text_body = (
            f"School menu for {menu_date.isoformat()} is attached.\n"
            f"View in browser: {menu_link}"
        )
        html_body = (
            "<html><body>"
            '<img src="cid:menu-image" alt="School menu">'
            f"<p>School menu for {self._format_display_date(menu_date)}.</p>"
            f'<p><a href="{menu_link}">Open calendar view</a></p>'
            "</body></html>"
        )

        alternative.attach(MIMEText(text_body, "plain"))
        alternative.attach(MIMEText(html_body, "html"))
        message.attach(alternative)

        with image_path.open("rb") as handle:
            image = MIMEImage(handle.read(), _subtype="png")
        image.add_header("Content-ID", "<menu-image>")
        image.add_header("Content-Disposition", "inline", filename=image_path.name)
        message.attach(image)

        return message

    def _build_menu_link(self, menu_date: date) -> str:
        base_url = self._settings.menu_web_base_url.rstrip("/")
        parsed = urlparse(base_url)
        query = urlencode({"date": menu_date.isoformat()})
        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path or "/",
                parsed.params,
                query,
                parsed.fragment,
            )
        )

    def _build_menu_image_url(self, menu_date: date) -> str:
        base_url = self._settings.menu_web_base_url.rstrip("/")
        return f"{base_url}/api/image/{menu_date.isoformat()}"

    def _notify_sent(self, menu_date: date) -> None:
        try:
            self._send_ntfy(menu_date)
        except Exception:
            self._logger.exception("Failed to send ntfy notification")

    def _send_ntfy(self, menu_date: date) -> None:
        base_url = self._settings.ntfy_base_url.strip()
        topic = self._settings.ntfy_topic.strip()
        if not base_url or not topic:
            return

        topic = topic.lstrip("/")
        url = f"{base_url.rstrip('/')}/{topic}"
        menu_link = self._build_menu_link(menu_date)
        menu_image_url = self._build_menu_image_url(menu_date)
        display_date = self._format_display_date(menu_date)
        message = f""

        request = urllib.request.Request(
            url,
            data=message.encode("utf-8"),
            method="POST",
        )
        request.add_header("Content-Type", "text/plain; charset=utf-8")
        request.add_header("Title", f"School menu - {display_date}")
        request.add_header("Click", menu_link)
        request.add_header("Attach", menu_image_url)
        request.add_header("Filename", f"menu-{menu_date.isoformat()}.png")

        with urllib.request.urlopen(request, timeout=10) as response:
            response.read()

    def _format_subject(self, menu_date: date) -> str:
        return f"School menu - {self._format_display_date(menu_date)}"

    def _format_display_date(self, menu_date: date) -> str:
        return f"{menu_date.strftime('%a')} {menu_date.day} {menu_date.strftime('%b')}"

    def status(self) -> dict:
        """Return a status payload."""

        return {
            "last_sent_date": self._last_sent_date.isoformat()
            if self._last_sent_date
            else None,
            "last_sent_at": self._last_sent_at.isoformat() if self._last_sent_at else None,
            "last_attempt_at": self._last_attempt_at.isoformat()
            if self._last_attempt_at
            else None,
            "last_result": self._last_result,
            "last_error": self._last_error,
            "timezone": getattr(self._timezone, "key", "UTC"),
        }
