import json
import yaml
import pytest
from unittest.mock import MagicMock, patch
from src.orchestrator import _scrape_all, _enrich, _pre_filter_experience, run
from src.matcher import MatchResult, BatchOutcome, QuotaExhausted
from src.models import JobListing


def _listing(url="https://example.com/1", source="drushim", description=""):
    return JobListing(title="Dev", company="Co", location="Tel Aviv",
                      url=url, description=description, source=source)


# --- _scrape_all ---

def test_scrape_all_combines_listings_from_all_scrapers():
    a = MagicMock()
    a.scrape.return_value = [_listing("https://a.com/1")]

    b = MagicMock()
    b.scrape.return_value = [_listing("https://b.com/1"), _listing("https://b.com/2")]

    result = _scrape_all({"a": a, "b": b}, ["python"])
    assert len(result) == 3
    a.scrape.assert_called_once_with(["python"])
    b.scrape.assert_called_once_with(["python"])


def test_scrape_all_continues_when_one_scraper_raises():
    ok = MagicMock()
    ok.scrape.return_value = [_listing("https://ok.com/1")]

    bad = MagicMock()
    bad.scrape.side_effect = RuntimeError("network down")

    result = _scrape_all({"ok": ok, "bad": bad}, ["python"])
    assert len(result) == 1
    assert result[0].url == "https://ok.com/1"


# --- _enrich ---

def test_enrich_updates_description_when_full_text_is_longer():
    listing = _listing(description="short")
    scraper = MagicMock()
    scraper.fetch_full_description.return_value = "much longer full description text"

    count = _enrich([listing], {"drushim": scraper}, delay=0)

    assert count == 1
    assert listing.description == "much longer full description text"


def test_enrich_skips_when_fetch_returns_none():
    listing = _listing(description="original")
    scraper = MagicMock()
    scraper.fetch_full_description.return_value = None

    count = _enrich([listing], {"drushim": scraper}, delay=0)

    assert count == 0
    assert listing.description == "original"


def test_enrich_skips_when_full_text_is_shorter():
    listing = _listing(description="already a long description that won't be replaced")
    scraper = MagicMock()
    scraper.fetch_full_description.return_value = "short"

    count = _enrich([listing], {"drushim": scraper}, delay=0)

    assert count == 0
    assert "already a long" in listing.description


def test_enrich_skips_listing_with_no_matching_scraper():
    listing = _listing(source="unknown_source", description="original")
    count = _enrich([listing], {}, delay=0)
    assert count == 0
    assert listing.description == "original"


# --- _pre_filter_experience ---

def test_pre_filter_experience_drops_listing_with_experience_in_enriched_description(tmp_path):
    """A listing that passed the initial pre-filter (short description had no years)
    should be dropped post-enrich if the full description reveals 5 years required."""
    import yaml
    from src.config_loader import load_config
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump({
        "regions": ["Tel Aviv"], "match_threshold": 60, "email_to": "x@x.com",
        "search_terms": [],
        "filters": {
            "seniority_keywords": [], "unwanted_keywords": [], "max_years_experience": 3,
        },
    }))
    config = load_config(str(p))
    listing = _listing(description="Requires 5 years of Python experience.")
    kept = _pre_filter_experience([listing], config)
    assert kept == []


def test_pre_filter_experience_keeps_listing_within_limit(tmp_path):
    import yaml
    from src.config_loader import load_config
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump({
        "regions": ["Tel Aviv"], "match_threshold": 60, "email_to": "x@x.com",
        "search_terms": [],
        "filters": {
            "seniority_keywords": [], "unwanted_keywords": [], "max_years_experience": 3,
        },
    }))
    config = load_config(str(p))
    listing = _listing(description="Looking for a developer with 2 years of experience.")
    kept = _pre_filter_experience([listing], config)
    assert len(kept) == 1


# --- run() end-to-end pipeline ---

_MINIMAL_CONFIG = {
    "regions": ["תל אביב", "Tel Aviv"],
    "match_threshold": 70,
    "email_to": "test@example.com",
    "search_terms": ["python"],
    "filters": {
        "seniority_keywords": [" senior", "senior "],
        "unwanted_keywords": ["full stack"],
        "max_years_experience": 2,
    },
}


@pytest.fixture
def tmp_config(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(_MINIMAL_CONFIG))
    return str(p)


@pytest.fixture
def tmp_seen(tmp_path):
    p = tmp_path / "seen.json"
    p.write_text("{}")
    return str(p)


def test_run_sends_email_with_no_matches_message_when_below_threshold(tmp_config, tmp_seen, tmp_path):
    cv = tmp_path / "cv.txt"
    cv.write_text("Python developer CV")

    listing = _listing("https://drushim.co.il/1")
    outcome = BatchOutcome(
        results={"https://drushim.co.il/1": MatchResult(listing=listing, score=40, reasoning="Poor fit.")},
        failed_listings=[],
    )

    with patch("src.orchestrator._scrape_all", return_value=[listing]), \
         patch("src.orchestrator._enrich", return_value=0), \
         patch("src.orchestrator.match_batch", return_value=outcome), \
         patch("src.orchestrator.load_cv_text", return_value="cv text"), \
         patch("src.orchestrator.send") as mock_send:
        run(config_path=tmp_config, cv_path=str(cv), seen_path=tmp_seen)

    mock_send.assert_called_once()
    subject, body, _ = mock_send.call_args.args
    assert "0" in subject
    assert "0 matching" not in body  # no-match quip is shown instead


def test_run_sends_email_when_matches_found(tmp_config, tmp_seen, tmp_path):
    cv = tmp_path / "cv.txt"
    cv.write_text("Python developer CV")

    listing = _listing("https://drushim.co.il/1")
    outcome = BatchOutcome(
        results={"https://drushim.co.il/1": MatchResult(listing=listing, score=85, reasoning="Great fit.")},
        failed_listings=[],
    )

    with patch("src.orchestrator._scrape_all", return_value=[listing]), \
         patch("src.orchestrator._enrich", return_value=0), \
         patch("src.orchestrator.match_batch", return_value=outcome), \
         patch("src.orchestrator.load_cv_text", return_value="cv text"), \
         patch("src.orchestrator.send") as mock_send:
        run(config_path=tmp_config, cv_path=str(cv), seen_path=tmp_seen)

    mock_send.assert_called_once()
    subject, body, to = mock_send.call_args.args
    assert "1" in subject
    assert "drushim.co.il" in body
    assert to == "test@example.com"


def test_run_marks_listings_seen_after_scoring(tmp_config, tmp_seen, tmp_path):
    cv = tmp_path / "cv.txt"
    cv.write_text("Python developer CV")

    listing = _listing("https://drushim.co.il/job/42")
    outcome = BatchOutcome(
        results={"https://drushim.co.il/job/42": MatchResult(listing=listing, score=80, reasoning="Good fit.")},
        failed_listings=[],
    )

    with patch("src.orchestrator._scrape_all", return_value=[listing]), \
         patch("src.orchestrator._enrich", return_value=0), \
         patch("src.orchestrator.match_batch", return_value=outcome), \
         patch("src.orchestrator.load_cv_text", return_value="cv text"), \
         patch("src.orchestrator.send"):
        run(config_path=tmp_config, cv_path=str(cv), seen_path=tmp_seen)

    seen = json.loads(open(tmp_seen).read())
    assert "https://drushim.co.il/job/42" in seen


def test_run_does_not_mark_pre_filtered_listings_seen(tmp_config, tmp_seen, tmp_path):
    """A listing dropped by pre-filter must NOT be marked seen — so if filter rules
    change later, the same URL can re-appear and re-pass the filter."""
    cv = tmp_path / "cv.txt"
    cv.write_text("Python developer CV")

    # Senior title gets dropped by pre-filter (seniority_keywords include " senior")
    rejected = _listing("https://drushim.co.il/job/senior-1")
    rejected.title = "Senior Software Engineer"

    with patch("src.orchestrator._scrape_all", return_value=[rejected]), \
         patch("src.orchestrator._enrich", return_value=0), \
         patch("src.orchestrator.match_batch") as mock_match, \
         patch("src.orchestrator.load_cv_text", return_value="cv text"), \
         patch("src.orchestrator.send"):
        run(config_path=tmp_config, cv_path=str(cv), seen_path=tmp_seen)

    # match_batch must not even be called — pre-filter drops it first
    mock_match.assert_not_called()
    seen = json.loads(open(tmp_seen).read())
    assert "https://drushim.co.il/job/senior-1" not in seen


def test_run_does_not_mark_failed_listings_seen(tmp_config, tmp_seen, tmp_path):
    cv = tmp_path / "cv.txt"
    cv.write_text("Python developer CV")

    listing = _listing("https://drushim.co.il/job/99")
    outcome = BatchOutcome(
        results={},
        failed_listings=[listing],
    )

    with patch("src.orchestrator._scrape_all", return_value=[listing]), \
         patch("src.orchestrator._enrich", return_value=0), \
         patch("src.orchestrator.match_batch", return_value=outcome), \
         patch("src.orchestrator.load_cv_text", return_value="cv text"), \
         patch("src.orchestrator.send"):
        run(config_path=tmp_config, cv_path=str(cv), seen_path=tmp_seen)

    seen = json.loads(open(tmp_seen).read())
    assert "https://drushim.co.il/job/99" not in seen


def test_run_sends_partial_results_when_quota_exhausted(tmp_config, tmp_seen, tmp_path):
    cv = tmp_path / "cv.txt"
    cv.write_text("Python developer CV")

    good = _listing("https://drushim.co.il/1")
    exhausted = _listing("https://drushim.co.il/2")

    first_outcome = BatchOutcome(
        results={"https://drushim.co.il/1": MatchResult(listing=good, score=85, reasoning="Good fit.")},
        failed_listings=[],
    )

    def mock_match_batch(batch, *args, **kwargs):
        if exhausted in batch:
            raise QuotaExhausted("quota gone")
        return first_outcome

    with patch("src.orchestrator._scrape_all", return_value=[good, exhausted]), \
         patch("src.orchestrator._enrich", return_value=0), \
         patch("src.orchestrator.match_batch", side_effect=mock_match_batch), \
         patch("src.orchestrator.load_cv_text", return_value="cv text"), \
         patch("src.orchestrator._BATCH_SIZE", 1), \
         patch("src.orchestrator.send") as mock_send:
        run(config_path=tmp_config, cv_path=str(cv), seen_path=tmp_seen)

    # Email still sent with the 1 result found before quota ran out
    mock_send.assert_called_once()
    _, body, _ = mock_send.call_args.args
    assert "quota" in body.lower() or "1" in mock_send.call_args.args[0]


def test_run_retries_failed_listings_individually(tmp_config, tmp_seen, tmp_path):
    """A listing that fails batch scoring should be retried as a single-item call."""
    cv = tmp_path / "cv.txt"
    cv.write_text("Python developer CV")

    listing = _listing("https://drushim.co.il/job/retry-me")
    call_count = 0

    def mock_match_batch(batch, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if len(batch) > 1 or call_count == 1:
            # First call (batch) fails entirely
            return BatchOutcome(results={}, failed_listings=list(batch))
        # Retry (single item) succeeds
        return BatchOutcome(
            results={listing.url: MatchResult(listing=listing, score=85, reasoning="Good fit.")},
            failed_listings=[],
        )

    with patch("src.orchestrator._scrape_all", return_value=[listing]), \
         patch("src.orchestrator._enrich", return_value=0), \
         patch("src.orchestrator.match_batch", side_effect=mock_match_batch), \
         patch("src.orchestrator.load_cv_text", return_value="cv text"), \
         patch("src.orchestrator.send") as mock_send:
        run(config_path=tmp_config, cv_path=str(cv), seen_path=tmp_seen)

    # match_batch called twice: once for batch, once for retry
    assert call_count == 2
    # Recovered listing appears in the email
    _, body, _ = mock_send.call_args.args
    assert "drushim.co.il/job/retry-me" in body
