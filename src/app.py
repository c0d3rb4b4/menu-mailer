"""FastAPI application for menu-mailer."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from src.config import get_settings, setup_logging
from src.mailer import CHECK_INTERVAL_SECONDS, MenuMailer
from src.menu_index import MenuIndex


setup_logging()
logger = logging.getLogger("menu-mailer")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    index = MenuIndex(settings.menu_image_dir)
    index.scan()

    mailer = MenuMailer(settings, index)

    app.state.index = index
    app.state.mailer = mailer
    app.state.settings = settings

    scan_task = None
    mailer_task = None

    if settings.scan_interval_seconds > 0:

        async def scan_loop() -> None:
            while True:
                await asyncio.sleep(settings.scan_interval_seconds)
                try:
                    index.scan()
                except Exception:
                    logger.exception("Failed to scan menu image directory")

        scan_task = asyncio.create_task(scan_loop())

    async def mailer_loop() -> None:
        while True:
            try:
                mailer.tick()
            except Exception:
                logger.exception("Mailer loop error")
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)

    mailer_task = asyncio.create_task(mailer_loop())

    yield

    for task in (scan_task, mailer_task):
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


app = FastAPI(title="menu-mailer", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/status")
async def status():
    index = app.state.index
    mailer = app.state.mailer
    payload = mailer.status()
    payload["last_scan"] = index.last_scan_iso()
    return payload


@app.post("/send-now")
async def send_now():
    mailer = app.state.mailer
    return mailer.send_now()


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "src.app:app",
        host=settings.bind_host,
        port=settings.bind_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
