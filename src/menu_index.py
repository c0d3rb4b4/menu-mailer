"""Menu image indexer."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Dict, Optional


DATE_PATTERN = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})(?:_.+)?\.png$", re.IGNORECASE)


class MenuIndex:
    """Scan a directory and index menu images by date."""

    def __init__(self, menu_image_dir: str) -> None:
        self._menu_image_dir = Path(menu_image_dir)
        self._lock = Lock()
        self._date_to_path: Dict[str, Path] = {}
        self._last_scan: Optional[datetime] = None
        self._logger = logging.getLogger("menu-mailer.index")

    def scan(self) -> None:
        """Scan the menu directory and rebuild the index."""

        scan_time = datetime.now(timezone.utc)
        new_map: Dict[str, Path] = {}

        if not self._menu_image_dir.exists():
            self._logger.warning(
                "Menu image directory does not exist: %s", self._menu_image_dir
            )
            self._update_index(new_map, scan_time)
            return

        try:
            for entry in self._menu_image_dir.iterdir():
                if not entry.is_file():
                    continue
                if entry.suffix.lower() != ".png":
                    continue

                match = DATE_PATTERN.match(entry.name)
                if not match:
                    continue

                date_str = match.group("date")
                try:
                    date.fromisoformat(date_str)
                except ValueError:
                    continue

                existing = new_map.get(date_str)
                if existing is None or entry.name < existing.name:
                    new_map[date_str] = entry
        except OSError:
            self._logger.exception("Failed to scan menu image directory")

        self._update_index(new_map, scan_time)

    def _update_index(self, new_map: Dict[str, Path], scan_time: datetime) -> None:
        with self._lock:
            self._date_to_path = new_map
            self._last_scan = scan_time

    def get_image_path(self, date_str: str) -> Optional[Path]:
        """Return the image path for a given date string."""

        with self._lock:
            return self._date_to_path.get(date_str)

    def last_scan_iso(self) -> Optional[str]:
        """Return the last scan timestamp as an ISO string."""

        with self._lock:
            if self._last_scan is None:
                return None
            return self._last_scan.isoformat()
