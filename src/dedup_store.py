import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class DedupStore:
    def __init__(self, store_path: str | Path = "seen_jobs.json"):
        self._path = Path(store_path)
        self._seen: dict[str, str] = {}
        if self._path.exists():
            self._load()

    def is_seen(self, url: str) -> bool:
        return url in self._seen

    def mark_seen(self, url: str) -> None:
        self._seen[url] = datetime.now(timezone.utc).isoformat()

    def save(self) -> None:
        self._path.write_text(json.dumps(self._seen, indent=2))

    def _load(self) -> None:
        try:
            data = json.loads(self._path.read_text())
        except Exception as e:
            logger.warning("dedup_store: could not read %s, starting fresh: %s", self._path, e)
            return

        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        for url, ts in data.items():
            try:
                if datetime.fromisoformat(ts) > cutoff:
                    self._seen[url] = ts
            except Exception:
                logger.warning("dedup_store: skipping malformed entry for %s", url)
