import logging
import time
from src.config_loader import load_config, load_cv_text
from src.dedup_store import DedupStore
from src.email_formatter import format_digest
from src.email_sender import send
from src.matcher import match_batch, QuotaExhausted, _BATCH_SIZE
from src.models import JobListing
from src.scrapers import alljobs, drushim, indeed, jobmaster, linkedin

_SCRAPER_BY_SOURCE = {
    "drushim": drushim,
    "jobmaster": jobmaster,
    "alljobs": alljobs,
    "linkedin": linkedin,
    "indeed": indeed,
}
_ENRICH_DELAY = 0.6

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_CONFIG_PATH = "config.yaml"
_CV_PATH = "Dor_Alagem_CV.pdf"
_SEEN_JOBS_PATH = "seen_jobs.json"


def _scrape_all(scrapers) -> list[JobListing]:
    """Run each scraper independently; log counts; swallow per-scraper failures."""
    all_listings: list[JobListing] = []
    for scraper in scrapers:
        name = scraper.__name__.split(".")[-1]
        try:
            listings = scraper.scrape()
            logger.info("%s: %d listings scraped", name, len(listings))
            all_listings.extend(listings)
        except Exception as e:
            logger.warning("%s: scraper failed: %s", name, e)
    return all_listings


def _enrich(listings: list[JobListing], scraper_by_source: dict, delay: float = _ENRICH_DELAY) -> int:
    """Fetch full job-page descriptions in-place; return count of listings enriched."""
    enriched = 0
    for listing in listings:
        scraper = scraper_by_source.get(listing.source)
        if scraper and hasattr(scraper, "fetch_full_description"):
            try:
                full = scraper.fetch_full_description(listing.url)
                if full and len(full) > len(listing.description):
                    listing.description = full
                    enriched += 1
            except Exception as e:
                logger.debug("enrich failed for %s: %s", listing.url, e)
            time.sleep(delay)
    return enriched


def run(
    config_path: str = _CONFIG_PATH,
    cv_path: str = _CV_PATH,
    seen_path: str = _SEEN_JOBS_PATH,
) -> None:
    logger.info("Job scanner run starting")

    config = load_config(config_path)
    cv_text = load_cv_text(cv_path)
    store = DedupStore(seen_path)

    all_listings = _scrape_all((drushim, jobmaster, alljobs, linkedin, indeed))
    logger.info("Total listings before dedup: %d", len(all_listings))

    new_listings = [l for l in all_listings if not store.is_seen(l.url)]
    logger.info("New listings after dedup: %d", len(new_listings))

    enriched_count = _enrich(new_listings, _SCRAPER_BY_SOURCE)
    logger.info("Enriched %d/%d listings with full descriptions", enriched_count, len(new_listings))

    results = []
    total_failed = 0
    quota_exhausted = False
    for i in range(0, len(new_listings), _BATCH_SIZE):
        batch = new_listings[i:i + _BATCH_SIZE]
        try:
            outcome = match_batch(batch, cv_text, config)
        except QuotaExhausted:
            logger.warning("Quota exhausted — stopping matching early, sending results found so far")
            quota_exhausted = True
            break

        for j, result in outcome.results.items():
            store.mark_seen(result.listing.url)
            if result.score >= config.match_threshold:
                results.append(result)

        total_failed += len(outcome.failed_listings)
        for failed in outcome.failed_listings:
            logger.warning("Failed to evaluate: %r (%s)", failed.title, failed.source)

    results.sort(key=lambda r: r.score, reverse=True)
    logger.info("Matching listings (score >= %d): %d, failed to evaluate: %d",
                config.match_threshold, len(results), total_failed)

    body = format_digest(results, failed_count=total_failed, quota_exhausted=quota_exhausted)
    subject = f"Job Scanner: {len(results)} new match(es) found"
    send(subject, body, config.email_to)
    logger.info("Digest email sent with %d listings", len(results))

    store.save()
    logger.info("seen_jobs.json updated")


if __name__ == "__main__":
    run()
