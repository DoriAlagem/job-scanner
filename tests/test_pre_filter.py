"""Tests for pre-filter rules (region, title keywords, experience years).

Pre-filter is rule-based, deterministic, and runs before any LLM call —
no Groq mocking needed."""

import logging
import pytest

from src import pre_filter
from src.config_loader import Config, FilterConfig
from src.models import JobListing


@pytest.fixture
def config():
    return Config(
        regions=["תל אביב", "Tel Aviv", "הרצליה", "Herzliya", "מרכז", "Center"],
        match_threshold=60,
        email_to="x@x.com",
        search_terms=[],
        filters=FilterConfig(
            seniority_keywords=(
                " senior", "senior ", "sr.", " sr ", " lead ", "team lead", "tech lead",
                "principal", "head of", " chief", "vp ", " director",
                "בכיר", "ראש צוות", " ראש ",
            ),
            unwanted_keywords=(
                "full stack", "fullstack", "full-stack",
                "ui/ux", "ux/ui", "ui ux", " ux ", " ui ", "ui designer", "ux designer",
                "economist", "economics", "כלכלן", "כלכלנית", "חשב", "רואה חשבון",
                "freelance", "פרילנס", "פרילנסר",
                "מתאם פגישות", "מתאמת פגישות", "מתאם/ת פגישות",
                "appointment setter", "scheduling coordinator",
            ),
            max_years_experience=2,
            role_max_years_overrides={"data engineer": 1},
        ),
    )


def _listing(title="Python Developer", location="Tel Aviv", description="", url=None):
    return JobListing(
        title=title,
        company="Acme",
        location=location,
        url=url or f"https://x.com/{hash((title, location, description))}",
        description=description,
        source="drushim",
    )


def test_drops_listing_outside_regions(config):
    kept = pre_filter.apply([_listing(location="באר שבע")], config)
    assert kept == []


def test_keeps_listing_with_unknown_location(config):
    kept = pre_filter.apply([_listing(location="Israel")], config)
    assert len(kept) == 1


def test_drops_senior_titles(config):
    kept = pre_filter.apply([_listing(title="Senior Software Engineer")], config)
    assert kept == []


def test_drops_hebrew_senior_titles(config):
    kept = pre_filter.apply([_listing(title="מפתח/ת בכיר/ה Python")], config)
    assert kept == []


def test_drops_listings_with_too_many_years(config):
    descriptions = [
        "Looking for a developer with 3+ years of experience.",
        "Requirements: 5 years of professional experience in Python.",
        "Minimum 4 years experience required.",
        "We need someone with at least 3 years of backend experience.",
        "3-5 years experience.",
        "דרישות: 5 שנות ניסיון בפיתוח Python.",
        "מינימום 3 שנים ניסיון",
    ]
    for desc in descriptions:
        kept = pre_filter.apply([_listing(description=desc)], config)
        assert kept == [], f"should drop listing with description: {desc!r}"


def test_keeps_listings_within_max_years(config):
    kept = pre_filter.apply(
        [_listing(description="Looking for a developer with 0-2 years of experience.")],
        config,
    )
    assert len(kept) == 1


def test_drops_unwanted_titles(config):
    unwanted = [
        "Full Stack Developer",
        "Fullstack Engineer",
        "UI/UX Designer",
        "UX Researcher",
        "Senior Economist",
        "Freelance Python Developer",
        "מתאם פגישות לחברת הייטק",
    ]
    for title in unwanted:
        kept = pre_filter.apply([_listing(title=title)], config)
        assert kept == [], f"should drop unwanted title: {title!r}"


def test_keeps_neutral_titles(config):
    kept = pre_filter.apply([_listing(title="Project Manager")], config)
    assert len(kept) == 1


def test_role_override_applies_stricter_limit(config):
    """Data engineer override is 1 year; a 2-year requirement should be dropped."""
    kept = pre_filter.apply(
        [_listing(title="Data Engineer", description="Requires 2 years of experience.")],
        config,
    )
    assert kept == []


def test_apply_returns_only_passing_listings(config):
    listings = [
        _listing(title="Python Dev", location="Tel Aviv"),  # passes
        _listing(title="Senior Engineer", location="Tel Aviv"),  # dropped
        _listing(title="Backend Dev", location="באר שבע"),  # dropped
    ]
    kept = pre_filter.apply(listings, config)
    assert len(kept) == 1
    assert kept[0].title == "Python Dev"


def test_apply_logs_drop_reason_at_debug(config, caplog):
    with caplog.at_level(logging.DEBUG, logger="src.pre_filter"):
        pre_filter.apply([_listing(title="Senior Engineer", location="Tel Aviv")], config)
    assert any("pre-filter dropped" in r.message for r in caplog.records)
    assert any("seniority" in r.message or "unwanted" in r.message for r in caplog.records)
