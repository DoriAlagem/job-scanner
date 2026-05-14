import logging
from src.config_loader import load_config, load_cv_text
from src.dedup_store import DedupStore
from src.email_formatter import format_digest
from src.email_sender import send
from src.matcher import match_batch, QuotaExhausted, _BATCH_SIZE
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

    # Match in batches
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

        # Mark successfully-evaluated listings as seen; collect matches above threshold
        for j, result in outcome.results.items():
            store.mark_seen(result.listing.url)
            if result.score >= config.match_threshold:
                results.append(result)

        # Listings that failed to evaluate are NOT marked seen — will be retried next run
        total_failed += len(outcome.failed_listings)
        for failed in outcome.failed_listings:
            logger.warning("Failed to evaluate: %r (%s)", failed.title, failed.source)

    results.sort(key=lambda r: r.score, reverse=True)
    logger.info("Matching listings (score >= %d): %d, failed to evaluate: %d",
                config.match_threshold, len(results), total_failed)

    # Send digest
    if results or total_failed > 0:
        body = format_digest(results, failed_count=total_failed, quota_exhausted=quota_exhausted)
        subject = f"Job Scanner: {len(results)} new match(es) found"
        send(subject, body, config.email_to)
        logger.info("Digest email sent with %d listings", len(results))
    else:
        logger.info("No matches above threshold and no failures — no email sent")

    # Persist seen jobs
    store.save()
    logger.info("seen_jobs.json updated")


if __name__ == "__main__":
    run()
