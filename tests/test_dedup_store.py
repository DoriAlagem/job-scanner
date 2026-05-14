import pytest
from datetime import datetime, timedelta, timezone
import json
from src.dedup_store import DedupStore


def test_unknown_url_is_not_seen(tmp_path):
    store = DedupStore(tmp_path / "seen_jobs.json")
    assert store.is_seen("https://drushim.co.il/job/123") is False


def test_url_is_seen_after_mark(tmp_path):
    store = DedupStore(tmp_path / "seen_jobs.json")
    store.mark_seen("https://drushim.co.il/job/123")
    assert store.is_seen("https://drushim.co.il/job/123") is True


def test_save_and_reload_round_trips(tmp_path):
    path = tmp_path / "seen_jobs.json"
    store = DedupStore(path)
    store.mark_seen("https://drushim.co.il/job/123")
    store.save()

    reloaded = DedupStore(path)
    assert reloaded.is_seen("https://drushim.co.il/job/123") is True


def test_corrupted_file_starts_fresh(tmp_path):
    path = tmp_path / "seen_jobs.json"
    valid_ts = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps({
        "https://drushim.co.il/job/good": valid_ts,
        "https://drushim.co.il/job/bad": "not-a-timestamp",
    }))

    store = DedupStore(path)
    assert store.is_seen("https://drushim.co.il/job/good") is True
    assert store.is_seen("https://drushim.co.il/job/bad") is False


def test_invalid_json_file_starts_fresh(tmp_path):
    path = tmp_path / "seen_jobs.json"
    path.write_text("<<<< conflict marker garbage >>>>")

    store = DedupStore(path)
    assert store.is_seen("https://anything.com") is False


def test_urls_older_than_90_days_are_expired(tmp_path):
    path = tmp_path / "seen_jobs.json"
    old_ts = (datetime.now(timezone.utc) - timedelta(days=91)).isoformat()
    path.write_text(json.dumps({"https://drushim.co.il/job/old": old_ts}))

    store = DedupStore(path)
    assert store.is_seen("https://drushim.co.il/job/old") is False
