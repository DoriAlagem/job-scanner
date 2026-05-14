import pytest
from unittest.mock import MagicMock, patch
from src.matcher import match, match_batch, MatchResult
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


def _mock_groq_batch_response(*entries: tuple[int, str]):
    """entries is a sequence of (score, reasoning) tuples — one per listing in the batch."""
    import json
    body = json.dumps({
        "results": [{"score": s, "reasoning": r} for s, r in entries]
    })
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = body
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    return mock_client


def test_returns_match_result_with_correct_score_and_reasoning(listing, cv_text, config):
    mock_client = _mock_groq_batch_response((85, "Strong Python skills match the role."))
    with patch("src.matcher.Groq", return_value=mock_client):
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
    # Pre-filter rejection still returns a MatchResult with score 0 from match_batch,
    # but since match() now wraps batch and returns the result, we expect score 0 here.
    mock_client = MagicMock()
    with patch("src.matcher.Groq", return_value=mock_client):
        result = match(listing, cv_text, config)

    # Pre-filtered listings get score 0 with "Pre-filtered" reasoning, no LLM call
    assert result is not None
    assert result.score == 0
    assert "Pre-filtered" in result.reasoning
    mock_client.chat.completions.create.assert_not_called()


def test_keeps_listing_with_unknown_location(cv_text, config):
    listing = JobListing(
        title="Python Developer",
        company="Acme",
        location="Israel",  # generic — should not be filtered
        url="https://drushim.co.il/job/789",
        description="",
        source="drushim",
    )
    mock_client = _mock_groq_batch_response((80, "Good fit."))
    with patch("src.matcher.Groq", return_value=mock_client):
        result = match(listing, cv_text, config)

    assert result is not None
    assert result.score == 80


def test_senior_title_rejected_without_llm_call(cv_text, config):
    listing = JobListing(
        title="Senior Software Engineer",
        company="Acme",
        location="Tel Aviv",
        url="https://drushim.co.il/job/senior-1",
        description="",
        source="drushim",
    )
    mock_client = MagicMock()
    with patch("src.matcher.Groq", return_value=mock_client):
        result = match(listing, cv_text, config)

    # Pre-filtered: score 0, no LLM call
    assert result is not None
    assert result.score == 0
    mock_client.chat.completions.create.assert_not_called()


def test_hebrew_senior_title_rejected(cv_text, config):
    listing = JobListing(
        title="מפתח/ת בכיר/ה Python",
        company="Acme",
        location="Tel Aviv",
        url="https://drushim.co.il/job/senior-heb",
        description="",
        source="drushim",
    )
    mock_client = MagicMock()
    with patch("src.matcher.Groq", return_value=mock_client):
        result = match(listing, cv_text, config)

    assert result is not None
    assert result.score == 0
    mock_client.chat.completions.create.assert_not_called()


def test_years_of_experience_in_description_rejected(cv_text, config):
    """Listings whose description explicitly requires 3+ years of experience get pre-filtered."""
    descriptions = [
        "Looking for a developer with 3+ years of experience.",
        "Requirements: 5 years of professional experience in Python.",
        "Minimum 4 years experience required.",
        "We need someone with at least 3 years of backend experience.",
        "3-5 years experience.",
        "דרישות: 5 שנות ניסיון בפיתוח Python.",
        "מינימום 3 שנים ניסיון",
    ]
    mock_client = MagicMock()
    for desc in descriptions:
        listing = JobListing(
            title="Python Developer",  # neutral title that would otherwise pass
            company="Acme",
            location="Tel Aviv",
            url=f"https://x.com/{hash(desc)}",
            description=desc,
            source="drushim",
        )
        with patch("src.matcher.Groq", return_value=mock_client):
            result = match(listing, cv_text, config)
        assert result is not None, f"description should yield pre-filter result: {desc!r}"
        assert result.score == 0, f"description {desc!r} should be rejected but got {result.score}"
    mock_client.chat.completions.create.assert_not_called()


def test_two_years_experience_still_passes(cv_text, config):
    """Listings asking for 0-2 years should NOT be rejected."""
    listing = JobListing(
        title="Python Developer",
        company="Acme",
        location="Tel Aviv",
        url="https://x.com/two-yrs",
        description="Looking for a developer with 0-2 years of experience.",
        source="drushim",
    )
    mock_client = _mock_groq_batch_response((80, "Good fit."))
    with patch("src.matcher.Groq", return_value=mock_client):
        result = match(listing, cv_text, config)

    assert result is not None
    assert result.score == 80


def test_unwanted_title_keywords_rejected(cv_text, config):
    """Full Stack, UI/UX, Economist, Freelance, מתאם פגישות should all be pre-filtered."""
    unwanted_titles = [
        "Full Stack Developer",
        "Fullstack Engineer",
        "UI/UX Designer",
        "UX Researcher",
        "Senior Economist",  # also has senior, both should fire
        "Freelance Python Developer",
        "מתאם פגישות לחברת הייטק",
    ]
    mock_client = MagicMock()
    for title in unwanted_titles:
        listing = JobListing(
            title=title,
            company="Acme",
            location="Tel Aviv",
            url=f"https://x.com/{title}",
            description="",
            source="drushim",
        )
        with patch("src.matcher.Groq", return_value=mock_client):
            result = match(listing, cv_text, config)
        assert result is not None, f"{title} should return a pre-filter result"
        assert result.score == 0, f"{title} should be score 0 but got {result.score}"
    mock_client.chat.completions.create.assert_not_called()


def test_manager_title_passes_filter(cv_text, config):
    listing = JobListing(
        title="Project Manager",
        company="Acme",
        location="Tel Aviv",
        url="https://drushim.co.il/job/pm",
        description="",
        source="drushim",
    )
    mock_client = _mock_groq_batch_response((75, "Skills align with role requirements."))
    with patch("src.matcher.Groq", return_value=mock_client):
        result = match(listing, cv_text, config)

    assert result is not None
    assert result.score == 75


def test_batch_returns_results_for_multiple_listings(cv_text, config):
    listings = [
        JobListing(title="Python Dev", company="A", location="Tel Aviv", url="https://x.com/1", description="", source="drushim"),
        JobListing(title="Backend Dev", company="B", location="Herzliya", url="https://x.com/2", description="", source="drushim"),
    ]
    mock_client = _mock_groq_batch_response((85, "Great fit."), (60, "Decent fit."))
    with patch("src.matcher.Groq", return_value=mock_client):
        outcome = match_batch(listings, cv_text, config)

    assert len(outcome.results) == 2
    assert outcome.results[0].score == 85
    assert outcome.results[1].score == 60
    assert outcome.failed_listings == []


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
    # No results for this listing
    assert 0 not in outcome.results
