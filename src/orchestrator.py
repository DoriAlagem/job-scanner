import logging
import time
from dataclasses import dataclass

from src.config_loader import Config, load_config, load_cv_text
from src.dedup_store import DedupStore
from src.email_formatter import format_digest
from src.email_sender import send
from src.matcher import make_client, match_batch, MatchResult, QuotaExhausted, _BATCH_SIZE
from src.models import JobListing
from src import pre_filter
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


def _scrape_all(scrapers: dict, terms: list[str]) -> list[JobListing]:
    """Run each scraper; log counts; swallow per-scraper failures."""
    all_listings: list[JobListing] = []
    for name, scraper in scrapers.items():
        try:
            listings = scraper.scrape(terms)
            if listings:
                logger.info("%s: %d listings scraped", name, len(listings))
            else:
                logger.warning("%s: scraper returned 0 listings — possible block or site change", name)
            all_listings.extend(listings)
        except Exception as e:
            logger.warning("%s: scraper failed: %s", name, e)
    return all_listings


def _dedup(listings: list[JobListing], store: DedupStore) -> list[JobListing]:
    """Drop listings whose URL is already in the dedup store."""
    new = [l for l in listings if not store.is_seen(l.url)]
    logger.info("New listings after dedup: %d (of %d total)", len(new), len(listings))
    return new


def _pre_filter(listings: list[JobListing], config: Config) -> list[JobListing]:
    """Drop listings that fail region/title/experience filters. Dropped listings
    are NOT marked seen, so they re-appear in future runs if filter rules change."""
    kept = pre_filter.apply(listings, config)
    logger.info("Pre-filter kept %d of %d listings", len(kept), len(listings))
    return kept


def _pre_filter_experience(listings: list[JobListing], config: Config) -> list[JobListing]:
    """Re-run experience check on enriched descriptions. Experience requirements are
    often only visible in the full job page, not the short scraped snippet."""
    kept = [l for l in listings if pre_filter.passes_experience(l, config)]
    dropped = len(listings) - len(kept)
    if dropped:
        logger.info("Post-enrich experience filter dropped %d listing(s)", dropped)
    return kept


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


def _log_per_source_stats(listings: list[JobListing], matches: list[MatchResult], threshold: int) -> None:
    from collections import Counter
    scored_by_source: Counter = Counter(l.source for l in listings)
    matched_by_source: Counter = Counter(r.listing.source for r in matches)
    for source in sorted(scored_by_source):
        logger.info("  %s: %d scored, %d matched (>= %d)",
                    source, scored_by_source[source], matched_by_source[source], threshold)


def _accept(result: MatchResult, config: Config, store: DedupStore, matches: list[MatchResult]) -> None:
    """Mark a scored listing seen and append it to matches if above threshold."""
    store.mark_seen(result.listing.url)
    if result.score >= config.match_threshold:
        matches.append(result)


def _retry_failed(
    failed: list[JobListing],
    cv_text: str,
    config: Config,
    client,
    store: DedupStore,
    matches: list[MatchResult],
) -> tuple[int, bool]:
    """Retry each failed listing individually; return (recovered_count, quota_exhausted)."""
    recovered = 0
    for listing in failed:
        logger.warning("Retrying failed listing: %r (%s)", listing.title, listing.source)
        try:
            retry = match_batch([listing], cv_text, config, client=client)
        except QuotaExhausted:
            return recovered, True
        if retry.failed_listings:
            logger.warning("Retry also failed for: %r (%s)", listing.title, listing.source)
        else:
            recovered += 1
            for result in retry.results.values():
                _accept(result, config, store, matches)
    return recovered, False


def _score(listings: list[JobListing], cv_text: str, config: Config, store: DedupStore) -> ScoringSummary:
    """Score listings in batches; mark scored ones seen; return summary."""
    client = make_client()
    matches: list[MatchResult] = []
    all_failed: list[JobListing] = []
    quota_exhausted = False

    for i in range(0, len(listings), _BATCH_SIZE):
        batch = listings[i:i + _BATCH_SIZE]
        try:
            outcome = match_batch(batch, cv_text, config, client=client)
        except QuotaExhausted:
            logger.warning("Quota exhausted — stopping early, sending results so far")
            quota_exhausted = True
            break

        for result in outcome.results.values():
            _accept(result, config, store, matches)
        all_failed.extend(outcome.failed_listings)

    if not quota_exhausted:
        recovered, quota_exhausted = _retry_failed(
            all_failed, cv_text, config, client, store, matches
        )
    else:
        recovered = 0

    matches.sort(key=lambda r: r.score, reverse=True)
    logger.info("Matching listings (score >= %d): %d, failed: %d, retried: %d recovered",
                config.match_threshold, len(matches), len(all_failed), recovered)
    _log_per_source_stats(listings, matches, config.match_threshold)
    return ScoringSummary(matches=matches, failed_count=len(all_failed) - recovered, quota_exhausted=quota_exhausted)


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

    all_listings = _scrape_all(_SCRAPERS, config.search_terms)
    new_listings = _dedup(all_listings, store)
    filtered = _pre_filter(new_listings, config)
    _enrich(filtered, _SCRAPERS)
    # Re-run experience filter on enriched descriptions — requirements are often
    # only visible in the full job page, not the short scraped snippet.
    filtered = _pre_filter_experience(filtered, config)
    summary = _score(filtered, cv_text, config, store)
    _notify(summary, config.email_to)

    store.save()
    logger.info("seen_jobs.json updated")


if __name__ == "__main__":
    run()
