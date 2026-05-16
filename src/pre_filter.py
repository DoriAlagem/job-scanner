"""Rule-based pre-filtering of job listings before LLM scoring.

Filters by region, title keywords (seniority + unwanted), and explicit
experience requirements in the description. Listings that fail are dropped
and NOT marked seen, so they re-appear in future runs if filter rules change.
"""

import logging
import re

from src.config_loader import Config
from src.models import JobListing

logger = logging.getLogger(__name__)


# Experience year patterns — syntax rules, not user preferences
_YEARS_PATTERNS = [
    re.compile(r"(\d+)\s*\+\s*years?", re.IGNORECASE),
    re.compile(r"(\d+)\s*[-–]\s*\d+\s*years?", re.IGNORECASE),
    re.compile(r"(?:minimum|at least|min\.?|over)\s+(\d+)\s*years?", re.IGNORECASE),
    re.compile(r"(\d+)\s*years?\s+(?:of\s+)?(?:experience|exp\.?|professional)", re.IGNORECASE),
    re.compile(r"(\d+)\s*שנ(?:ות|ים|ה)"),
    re.compile(r"(\d+)\s*[-–]\s*\d+\s*שנ(?:ות|ים|ה)"),
]


def apply(listings: list[JobListing], config: Config) -> list[JobListing]:
    """Return only listings that pass all pre-filters."""
    kept = []
    for listing in listings:
        reason = _drop_reason(listing, config)
        if reason is None:
            kept.append(listing)
        else:
            logger.debug("pre-filter dropped %r (%s): %s", listing.title, listing.source, reason)
    return kept


def _drop_reason(listing: JobListing, config: Config) -> str | None:
    if not _passes_region(listing, config):
        return f"region '{listing.location}' not in configured regions"
    if not _passes_title(listing, config):
        return f"title '{listing.title}' matches seniority/unwanted keyword"
    if not _passes_experience(listing, config):
        return "experience requirement in title/description exceeds limit"
    return None


def _passes_region(listing: JobListing, config: Config) -> bool:
    loc = listing.location.strip().lower()
    if not loc or loc in ("israel", "unknown", ""):
        return True
    return any(region.lower() in loc or loc in region.lower() for region in config.regions)


def _passes_title(listing: JobListing, config: Config) -> bool:
    title = f" {listing.title.lower()} "
    if any(kw in title for kw in config.filters.seniority_keywords):
        return False
    if any(kw in title for kw in config.filters.unwanted_keywords):
        return False
    return True


def _passes_experience(listing: JobListing, config: Config) -> bool:
    """False if the description explicitly requires more experience than allowed."""
    title_lower = listing.title.lower()
    max_years = config.filters.max_years_experience
    for role, override in config.filters.role_max_years_overrides.items():
        if role in title_lower:
            max_years = override
            break

    text = f"{listing.title} {listing.description}"
    for pattern in _YEARS_PATTERNS:
        for match in pattern.finditer(text):
            try:
                years = int(match.group(1))
                if years > max_years:
                    return False
            except (ValueError, IndexError):
                continue
    return True
