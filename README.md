# menu-mailer
## Overview

Menu Mailer is a background service that scans the same menu image folder and sends the current day’s menu image via email at a configured time every morning.

The menu image is embedded directly in the email body.

---

## Features

- Sends email once per day at a configured local time
- Sends ntfy notifications when a menu email is sent
- Inline image preview in email clients
- Automatically skips weekends (optional)
- Retries safely if image appears slightly late
- Stateless (no database)

---

## Folder Structure (Input)

```
/mnt/menu-images/
  2026-02-03_tue.png
  ...
```

---

## How It Works

1. Service starts and indexes menu images
2. Periodically checks current local time
3. At send time:
   - looks for today's menu image
   - if found, sends email
   - if not found, retries for a configured window

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/status` | GET | Last send status and last scan timestamp |
| `/send-now` | POST | Send today's menu email immediately |

---

## Configuration (Environment Variables)

### General

| Variable | Description | Default |
|--------|------------|---------|
| `MENU_IMAGE_DIR` | Menu image folder | `/mnt/menu-images` |
| `SEND_HOUR` | Hour to send (24h) | `7` |
| `SEND_MINUTE` | Minute to send | `0` |
| `TIMEZONE` | IANA timezone | `Europe/London` |
| `SKIP_WEEKENDS` | Skip Sat/Sun | `true` |
| `RETRY_WINDOW_MINUTES` | Retry window | `60` |
| `SCAN_INTERVAL_SECONDS` | Folder rescan | `300` |

### Email (SMTP)

| Variable | Description |
|--------|-------------|
| `SMTP_HOST` | SMTP server |
| `SMTP_PORT` | SMTP port |
| `SMTP_USERNAME` | SMTP username |
| `SMTP_PASSWORD` | SMTP password |
| `SMTP_USE_TLS` | true / false |
| `MAIL_FROM` | From address |
| `MAIL_TO` | Comma-separated recipients |
| `MENU_WEB_BASE_URL` | Base URL for menu-web viewer |
| `NTFY_BASE_URL` | Base URL for ntfy server |
| `NTFY_TOPIC` | Topic name for ntfy notifications |

---

## Email Format

- **Subject**:
  ```
  School menu – Tue 3 Feb
  ```
- **Body**:
  - Short text
  - Menu image embedded inline
  - Link to menu-web for the date
- **Fallback**:
  - Plain text for non-HTML clients

---

## Docker Example

```yaml
services:
  menu-mailer:
    image: menu-mailer:latest
    volumes:
      - /mnt/menu-images:/mnt/menu-images:ro
    environment:
      MENU_IMAGE_DIR: /mnt/menu-images
      SEND_HOUR: 7
      SEND_MINUTE: 0
      TIMEZONE: Europe/London
      SMTP_HOST: smtp.gmail.com
      SMTP_PORT: 587
      SMTP_USERNAME: example@gmail.com
      SMTP_PASSWORD: app-password
      MAIL_FROM: example@gmail.com
      MAIL_TO: you@gmail.com,partner@gmail.com
      MENU_WEB_BASE_URL: http://192.168.68.84:8080
      NTFY_BASE_URL: http://192.168.68.84:8090
      NTFY_TOPIC: menu-mailer
```

---

## Why Email?

- Works on every phone
- Inline image previews supported
- No apps required
- Easy to archive and forward
- Ideal for morning reminders

---

## Next Steps (Optional)

- Add school holiday exclusion
- Add “tomorrow’s menu” preview
- Add WhatsApp / Telegram bridge
- Add push notifications later
- Share logic between services

