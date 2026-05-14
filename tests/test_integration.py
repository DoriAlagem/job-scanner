"""End-to-end integration test: real filters, real dedup, real prompt building,
real email formatting. Only the Groq HTTP call and SMTP send are stubbed."""

import json
import yaml
import pytest
from unittest.mock import MagicMock, patch

from src.orchestrator import run
from src.models import JobListing


_CONFIG = {
    "regions": ["Tel Aviv", "תל אביב", "מרכז"],
    "match_threshold": 70,
    "email_to": "test@example.com",
    "filters": {
        "seniority_keywords": [" senior", "senior "],
        "unwanted_keywords": ["full stack", "מתאם"],
        "max_years_experience": 2,
        "role_max_years_overrides": {"data engineer": 1},
    },
}


@pytest.fixture
def tmp_config(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(_CONFIG))
    return str(p)


@pytest.fixture
def tmp_seen(tmp_path):
    p = tmp_path / "seen.json"
    p.write_text("{}")
    return str(p)


@pytest.fixture
def tmp_cv(tmp_path):
    p = tmp_path / "cv.txt"
    p.write_text("Python developer with REST API, AWS, SQL experience.")
    return str(p)


def _mixed_listings():
    """A mix designed to exercise every filter path."""
    return [
        # Should reach LLM: junior backend in Tel Aviv
        JobListing(title="Backend Developer", company="A", location="Tel Aviv",
                   url="https://drushim.co.il/job/keep1",
                   description="Python REST APIs.", source="drushim"),
        # Should be pre-filtered: senior title
        JobListing(title="Senior Engineer", company="B", location="Tel Aviv",
                   url="https://drushim.co.il/job/senior",
                   description="", source="drushim"),
        # Should be pre-filtered: outside region
        JobListing(title="Backend Developer", company="C", location="Haifa",
                   url="https://drushim.co.il/job/haifa",
                   description="", source="drushim"),
        # Should be pre-filtered: 5 years experience required
        JobListing(title="Backend Developer", company="D", location="Tel Aviv",
                   url="https://drushim.co.il/job/5yrs",
                   description="Requires 5+ years of experience.", source="drushim"),
        # Should be pre-filtered: full stack
        JobListing(title="Full Stack Developer", company="E", location="Tel Aviv",
                   url="https://drushim.co.il/job/fullstack",
                   description="", source="drushim"),
        # Should be pre-filtered: data engineer needing 2 years (override is 1)
        JobListing(title="Data Engineer", company="F", location="Tel Aviv",
                   url="https://drushim.co.il/job/de",
                   description="Requires 2 years of experience.", source="drushim"),
    ]


def _mock_groq_with_score(score: int):
    body = json.dumps({"results": [{"score": score, "reasoning": "Strong match."}]})
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = body
    client = MagicMock()
    client.chat.completions.create.return_value = response
    return client


def test_full_pipeline_filters_and_scores_correctly(tmp_config, tmp_seen, tmp_cv):
    """Real filter logic + real dedup + stubbed LLM/email. Only 1 of 6 listings
    should reach the LLM (the rest pre-filtered), and that one scores 85."""
    mock_groq = _mock_groq_with_score(85)

    with patch("src.orchestrator._scrape_all", return_value=_mixed_listings()), \
         patch("src.orchestrator._enrich", return_value=0), \
         patch("src.orchestrator.load_cv_text", return_value="cv text"), \
         patch("src.matcher.Groq", return_value=mock_groq), \
         patch("src.orchestrator.send") as mock_send:
        run(config_path=tmp_config, cv_path=tmp_cv, seen_path=tmp_seen)

    # Groq should be called exactly once for the 1 listing that survived pre-filtering
    assert mock_groq.chat.completions.create.call_count == 1

    # Email sent with the surviving match
    assert mock_send.called
    subject, body, to = mock_send.call_args.args
    assert "1 new match" in subject
    assert "drushim.co.il/job/keep1" in body
    assert to == "test@example.com"

    # All scored listings (the 5 pre-filtered + the 1 LLM-scored) marked seen
    seen = json.loads(open(tmp_seen).read())
    assert "https://drushim.co.il/job/keep1" in seen
    assert "https://drushim.co.il/job/senior" in seen
    assert "https://drushim.co.il/job/fullstack" in seen


def test_full_pipeline_skips_already_seen(tmp_config, tmp_seen, tmp_cv):
    """A listing already in seen_jobs.json should not reach the LLM."""
    import json as _json
    from datetime import datetime, timezone
    open(tmp_seen, "w").write(_json.dumps({
        "https://drushim.co.il/job/keep1": datetime.now(timezone.utc).isoformat()
    }))

    mock_groq = _mock_groq_with_score(85)
    with patch("src.orchestrator._scrape_all", return_value=_mixed_listings()), \
         patch("src.orchestrator._enrich", return_value=0), \
         patch("src.orchestrator.load_cv_text", return_value="cv text"), \
         patch("src.matcher.Groq", return_value=mock_groq), \
         patch("src.orchestrator.send") as mock_send:
        run(config_path=tmp_config, cv_path=tmp_cv, seen_path=tmp_seen)

    # The already-seen listing was filtered out by dedup, so 0 listings reached LLM
    assert mock_groq.chat.completions.create.call_count == 0
    # No matches → "no match" quip email still sent
    assert mock_send.called
    subject, _, _ = mock_send.call_args.args
    assert "0 new match" in subject
