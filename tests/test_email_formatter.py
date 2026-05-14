import pytest
from src.email_formatter import format_digest
from src.matcher import MatchResult
from src.models import JobListing


def _make_result(title: str, company: str, score: int, reasoning: str, url: str = "https://example.com/job/1") -> MatchResult:
    return MatchResult(
        listing=JobListing(title=title, company=company, location="Tel Aviv", url=url, description="", source="drushim"),
        score=score,
        reasoning=reasoning,
    )


def test_single_result_contains_required_fields():
    result = _make_result("Python Developer", "Acme Corp", 85, "Strong Python background matches role.")
    body = format_digest([result])

    assert "Python Developer" in body
    assert "Acme Corp" in body
    assert "85" in body
    assert "Strong Python background matches role." in body
    assert "https://example.com/job/1" in body


def test_multiple_results_all_appear_in_body():
    results = [
        _make_result("Backend Developer", "TechCorp", 90, "Excellent backend skills.", "https://example.com/job/1"),
        _make_result("DevOps Engineer", "CloudInc", 75, "AWS experience is a plus.", "https://example.com/job/2"),
    ]
    body = format_digest(results)

    assert "Backend Developer" in body
    assert "TechCorp" in body
    assert "DevOps Engineer" in body
    assert "CloudInc" in body
    assert "https://example.com/job/1" in body
    assert "https://example.com/job/2" in body


def test_empty_list_returns_no_matches_message():
    body = format_digest([])
    assert "No matching" in body
