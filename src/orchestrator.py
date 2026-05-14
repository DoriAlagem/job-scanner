import logging
import time
from dataclasses import dataclass

from src.config_loader import Config, load_config, load_cv_text
from src.dedup_store import DedupStore
from src.email_formatter import format_digest
from src.email_sender import send
from src.matcher import match_batch, MatchResult, QuotaExhausted, _BATCH_SIZE
from src.models import JobListing
from src.scrapers import alljobs, drushim, jobmaster, linkedin

# Single source of truth: source name → scraper module.
# Every scraper must expose: scrape() -> list[JobListing], fetch_full_description(url) -> str | None
_SCRAPERS = {
    "drushim": drushim,
    "jobmaster": jobmaster,
    "alljobs": alljobs,
    "linkedin": linkedin,
}
_ENRICH_DELAY = 0.6

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_CONFIG_PATH = "config.yaml"
_CV_PATH = "Dor_Alagem_CV.pdf"
_SEEN_JOBS_PATH = "seen_jobs.json"


@dataclass
class ScoringSummary:
    matches: list[MatchResult]
    failed_count: int
    quota_exhausted: bool


def _scrape_all(scrapers: dict) -> list[JobListing]:
    """Run each scraper; log counts; swallow per-scraper failures."""
    all_listings: list[JobListing] = []
    for name, scraper in scrapers.items():
        try:
            listings = scraper.scrape()
            logger.info("%s: %d listings scraped", name, len(listings))
            all_listings.extend(listings)
        except Exception as e:
            logger.warning("%s: scraper failed: %s", name, e)
    return all_listings


def _dedup(listings: list[JobListing], store: DedupStore) -> list[JobListing]:
    """Drop listings whose URL is already in the dedup store."""
    new = [l for l in listings if not store.is_seen(l.url)]
    logger.info("New listings after dedup: %d (of %d total)", len(new), len(listings))
    return new


def _enrich(listings: list[JobListing], scrapers: dict, delay: float = _ENRICH_DELAY) -> int:
    """Fetch full job-page descriptions in-place; return count enriched."""
    enriched = 0
    for listing in listings:
        scraper = scrapers.get(listing.source)
        if scraper is None:
            continue
        try:
            full = scraper.fetch_full_description(listing.url)
            if full and len(full) > len(listing.description):
                listing.description = full
                enriched += 1
        except Exception as e:
            logger.debug("enrich failed for %s: %s", listing.url, e)
        time.sleep(delay)
    logger.info("Enriched %d/%d listings with full descriptions", enriched, len(listings))
    return enriched


def _score(listings: list[JobListing], cv_text: str, config: Config, store: DedupStore) -> ScoringSummary:
    """Score listings in batches; mark scored ones seen; return summary."""
    matches: list[MatchResult] = []
    total_failed = 0
    quota_exhausted = False

    for i in range(0, len(listings), _BATCH_SIZE):
        batch = listings[i:i + _BATCH_SIZE]
        try:
            outcome = match_batch(batch, cv_text, config)
        except QuotaExhausted:
            logger.warning("Quota exhausted — stopping early, sending results so far")
            quota_exhausted = True
            break

        for result in outcome.results.values():
            store.mark_seen(result.listing.url)
            if result.score >= config.match_threshold:
                matches.append(result)

        total_failed += len(outcome.failed_listings)
        for failed in outcome.failed_listings:
            logger.warning("Failed to evaluate: %r (%s)", failed.title, failed.source)

    matches.sort(key=lambda r: r.score, reverse=True)
    logger.info("Matching listings (score >= %d): %d, failed: %d",
                config.match_threshold, len(matches), total_failed)
    return ScoringSummary(matches=matches, failed_count=total_failed, quota_exhausted=quota_exhausted)


def _notify(summary: ScoringSummary, email_to: str) -> None:
    """Format and send the digest email."""
    body = format_digest(summary.matches,
                         failed_count=summary.failed_count,
                         quota_exhausted=summary.quota_exhausted)
    subject = f"Job Scanner: {len(summary.matches)} new match(es) found"
    send(subject, body, email_to)
    logger.info("Digest email sent with %d listings", len(summary.matches))


def run(
    config_path: str = _CONFIG_PATH,
    cv_path: str = _CV_PATH,
    seen_path: str = _SEEN_JOBS_PATH,
) -> None:
    logger.info("Job scanner run starting")

    config = load_config(config_path)
    cv_text = load_cv_text(cv_path)
    store = DedupStore(seen_path)

    all_listings = _scrape_all(_SCRAPERS)
    new_listings = _dedup(all_listings, store)
    _enrich(new_listings, _SCRAPERS)
    summary = _score(new_listings, cv_text, config, store)
    _notify(summary, config.email_to)

    store.save()
    logger.info("seen_jobs.json updated")


if __name__ == "__main__":
    run()
