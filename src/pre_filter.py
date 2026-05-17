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
    re.compile(r"(\d+)\s*years?\s+(?:of\s+)?(?:\w+\s+){0,3}(?:experience|exp\.?|professional)", re.IGNORECASE),
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
    return not config.filters.title_is_blocked(listing.title)


def passes_experience(listing: JobListing, config: Config) -> bool:
    return _passes_experience(listing, config)


def experience_prompt_block(config: Config) -> str:
    """Return the LLM prompt fragment that enforces experience limits.

    Centralises experience-filter knowledge so matcher.py doesn't need to
    duplicate the rule logic that already lives here.
    """
    max_yrs = config.filters.max_years_experience
    exp_rule = (
        f"Score EXACTLY 0 if the listing requires more than {max_yrs} year(s) of experience, "
        f"or mentions: senior, lead, principal, head of, בכיר, ראש צוות, or any similar seniority signal. "
        f"This includes ranges like '4-6 years' or '3-5 שנות'. This is the most important rule — no exceptions."
    )
    override_lines = "\n".join(
        f"- {role.title()} roles: score EXACTLY 0 if more than {yrs} year(s) of experience required."
        for role, yrs in config.filters.role_max_years_overrides.items()
    )
    role_overrides = (
        f"\nROLE-SPECIFIC OVERRIDES (apply before the general rule):\n{override_lines}"
        if override_lines else ""
    )
    return f"{exp_rule}{role_overrides}"


def _passes_experience(listing: JobListing, config: Config) -> bool:
    """False if the description explicitly requires more experience than allowed."""
    max_years = config.filters.max_years_for(listing.title)
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
