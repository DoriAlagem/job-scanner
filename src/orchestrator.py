import logging
import sys
from pathlib import Path

from src.config_loader import load_config, load_cv_text
from src.dedup_store import DedupStore
from src.email_formatter import format_digest
from src.email_sender import send
from src.matcher import match, QuotaExhausted
from src.scrapers import alljobs, drushim, jobmaster, linkedin

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_CONFIG_PATH = "config.yaml"
_CV_PATH = "Dor_Alagem_CV.pdf"
_SEEN_JOBS_PATH = "seen_jobs.json"


def run() -> None:
    logger.info("Job scanner run starting")

    config = load_config(_CONFIG_PATH)
    cv_text = load_cv_text(_CV_PATH)
    store = DedupStore(_SEEN_JOBS_PATH)

    # Scrape all sources independently
    all_listings = []
    for scraper in (drushim, jobmaster, alljobs, linkedin):
        name = scraper.__name__.split(".")[-1]
        try:
            listings = scraper.scrape()
            logger.info("%s: %d listings scraped", name, len(listings))
            all_listings.extend(listings)
        except Exception as e:
            logger.warning("%s: scraper failed: %s", name, e)

    logger.info("Total listings before dedup: %d", len(all_listings))

    # Deduplicate
    new_listings = [l for l in all_listings if not store.is_seen(l.url)]
    logger.info("New listings after dedup: %d", len(new_listings))

    # Match
    results = []
    for listing in new_listings:
        try:
            result = match(listing, cv_text, config)
        except QuotaExhausted:
            logger.warning("Quota exhausted — stopping matching early, sending results found so far")
            break
        if result is not None and result.score >= config.match_threshold:
            results.append(result)
            store.mark_seen(listing.url)
        elif result is None:
            # Region-filtered — mark as seen; quota failures bubble up as QuotaExhausted
            store.mark_seen(listing.url)

    results.sort(key=lambda r: r.score, reverse=True)
    logger.info("Matching listings (score >= %d): %d", config.match_threshold, len(results))

    # Send digest
    if results:
        body = format_digest(results)
        subject = f"Job Scanner: {len(results)} new match(es) found"
        send(subject, body, config.email_to)
        logger.info("Digest email sent with %d listings", len(results))
    else:
        logger.info("No matches above threshold — no email sent")

    # Persist seen jobs
    store.save()
    logger.info("seen_jobs.json updated")


if __name__ == "__main__":
    run()
