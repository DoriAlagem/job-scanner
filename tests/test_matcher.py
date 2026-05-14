import pytest
from unittest.mock import MagicMock, patch
from src.matcher import match, MatchResult
from src.models import JobListing
from src.config_loader import Config


@pytest.fixture
def config():
    return Config(
        roles=["Python Developer", "Backend Developer"],
        experience_levels=["entry level", "junior"],
        location="Israel",
        regions=["תל אביב", "Tel Aviv", "הרצליה", "Herzliya", "מרכז", "Center"],
        match_threshold=70,
        email_language="English",
        email_to="dor3382@gmail.com",
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
    return "Computer Science student with Python, REST APIs, and AWS experience. GPA 95."


def _mock_gemini_response(score: int, reasoning: str):
    mock_response = MagicMock()
    mock_response.text = f'{{"score": {score}, "reasoning": "{reasoning}"}}'
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response
    return mock_client


def test_returns_match_result_with_correct_score_and_reasoning(listing, cv_text, config):
    mock_client = _mock_gemini_response(85, "Strong Python skills match the role.")
    with patch("src.matcher.genai.Client", return_value=mock_client):
        result = match(listing, cv_text, config)

    assert isinstance(result, MatchResult)
    assert result.score == 85
    assert result.reasoning == "Strong Python skills match the role."
    assert result.listing is listing


def test_returns_none_when_location_not_in_regions(cv_text, config):
    listing = JobListing(
        title="Python Developer",
        company="Acme",
        location="באר שבע",  # Beer Sheva — not in center district
        url="https://drushim.co.il/job/456",
        description="",
        source="drushim",
    )
    result = match(listing, cv_text, config)
    assert result is None


def test_keeps_listing_with_unknown_location(cv_text, config):
    listing = JobListing(
        title="Python Developer",
        company="Acme",
        location="Israel",  # generic — should not be filtered
        url="https://drushim.co.il/job/789",
        description="",
        source="drushim",
    )
    mock_client = _mock_gemini_response(80, "Good fit.")
    with patch("src.matcher.genai.Client", return_value=mock_client):
        result = match(listing, cv_text, config)

    assert result is not None
    assert result.score == 80


def test_returns_none_on_malformed_gemini_response(listing, cv_text, config):
    mock_response = MagicMock()
    mock_response.text = "not valid json at all"
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("src.matcher.genai.Client", return_value=mock_client):
        result = match(listing, cv_text, config)

    assert result is None
