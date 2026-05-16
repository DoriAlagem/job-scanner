"""Tests for matcher — LLM scoring, batch handling, prompt construction.

Pre-filter tests live in test_pre_filter.py. These tests assume input has
already been pre-filtered."""

import json
import pytest
from unittest.mock import MagicMock, patch
from src.matcher import match, match_batch, MatchResult, _build_batch_prompt
from src.models import JobListing
from src.config_loader import Config, FilterConfig


@pytest.fixture
def config():
    return Config(
        regions=["Tel Aviv"],
        match_threshold=60,
        email_to="x@x.com",
        search_terms=[],
        filters=FilterConfig(
            seniority_keywords=(),
            unwanted_keywords=(),
            max_years_experience=2,
        ),
    )


@pytest.fixture
def listing():
    return JobListing(
        title="Python Developer",
        company="Acme Corp",
        location="Tel Aviv",
        url="https://drushim.co.il/job/123",
        description="We need a Python developer with REST API experience.",
        source="drushim",
    )


@pytest.fixture
def cv_text():
    return "Computer Science student with Python, REST APIs, and AWS experience."


def _mock_groq_batch_response(*entries: tuple[int, str]):
    body = json.dumps({"results": [{"score": s, "reasoning": r} for s, r in entries]})
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = body
    client = MagicMock()
    client.chat.completions.create.return_value = response
    return client


def test_returns_match_result_with_correct_score_and_reasoning(listing, cv_text, config):
    mock_client = _mock_groq_batch_response((85, "Strong Python skills match the role."))
    with patch("src.matcher.Groq", return_value=mock_client):
        result = match(listing, cv_text, config)

    assert isinstance(result, MatchResult)
    assert result.score == 85
    assert result.reasoning == "Strong Python skills match the role."
    assert result.listing is listing


def test_batch_returns_results_for_multiple_listings(cv_text, config):
    listings = [
        JobListing(title="Python Dev", company="A", location="Tel Aviv",
                   url="https://x.com/1", description="", source="drushim"),
        JobListing(title="Backend Dev", company="B", location="Tel Aviv",
                   url="https://x.com/2", description="", source="drushim"),
    ]
    mock_client = _mock_groq_batch_response((85, "Great fit."), (60, "Decent fit."))
    with patch("src.matcher.Groq", return_value=mock_client):
        outcome = match_batch(listings, cv_text, config)

    assert len(outcome.results) == 2
    assert outcome.results["https://x.com/1"].score == 85
    assert outcome.results["https://x.com/2"].score == 60
    assert outcome.failed_listings == []


def test_prompt_reflects_config_thresholds(cv_text):
    cfg = Config(
        regions=["Tel Aviv"],
        match_threshold=70, email_to="x@x.com",
        search_terms=[],
        filters=FilterConfig(
            seniority_keywords=(),
            unwanted_keywords=(),
            max_years_experience=3,
            role_max_years_overrides={"data scientist": 1},
        ),
    )
    listings = [JobListing(title="Dev", company="X", location="Tel Aviv",
                           url="http://x.com/1", description="", source="drushim")]
    prompt = _build_batch_prompt(listings, cv_text, cfg)

    assert "more than 3 year(s)" in prompt
    assert "Data Scientist" in prompt
    assert "more than 1 year(s)" in prompt


def test_batch_handles_malformed_response(listing, cv_text, config):
    listings = [listing]
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "not valid json"
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    with patch("src.matcher.Groq", return_value=mock_client):
        outcome = match_batch(listings, cv_text, config)

    assert len(outcome.failed_listings) == 1
    assert outcome.failed_listings[0] is listing
    assert listing.url not in outcome.results


def test_empty_input_returns_empty_outcome(cv_text, config):
    """match_batch with no listings should not call Groq."""
    mock_client = MagicMock()
    with patch("src.matcher.Groq", return_value=mock_client):
        outcome = match_batch([], cv_text, config)

    assert outcome.results == {}
    assert outcome.failed_listings == []
    mock_client.chat.completions.create.assert_not_called()
