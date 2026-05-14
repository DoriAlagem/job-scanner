import json
import logging
import os
import re
import time
from dataclasses import dataclass

from groq import Groq

from src.config_loader import Config
from src.models import JobListing

logger = logging.getLogger(__name__)

# Llama 3.1 8B on Groq free tier: 30 RPM, 14400 RPD, 6000 TPM
_MODEL_NAME = "llama-3.1-8b-instant"
_REQUEST_DELAY = 2.0
_MAX_RETRIES = 3
_RETRY_DELAY = 60
_BATCH_SIZE = 10


class QuotaExhausted(Exception):
    """Raised when daily quota is exhausted — caller should stop and send results so far."""


@dataclass
class MatchResult:
    listing: JobListing
    score: int
    reasoning: str


@dataclass
class BatchOutcome:
    """Result of scoring a batch. `results` holds successful matches keyed by listing index;
    missing indices mean that listing failed to evaluate and should NOT be marked as seen."""
    results: dict[int, MatchResult]
    failed_listings: list[JobListing]


# Experience year patterns — these are fixed syntax rules, not user preferences
_YEARS_PATTERNS = [
    re.compile(r"(\d+)\s*\+\s*years?", re.IGNORECASE),
    re.compile(r"(\d+)\s*[-–]\s*\d+\s*years?", re.IGNORECASE),
    re.compile(r"(?:minimum|at least|min\.?|over)\s+(\d+)\s*years?", re.IGNORECASE),
    re.compile(r"(\d+)\s*years?\s+(?:of\s+)?(?:experience|exp\.?|professional)", re.IGNORECASE),
    re.compile(r"(\d+)\s*שנ(?:ות|ים|ה)"),
    re.compile(r"(\d+)\s*[-–]\s*\d+\s*שנ(?:ות|ים|ה)"),  # Hebrew range: "4-6 שנות"
]


def _passes_title_filter(listing: JobListing, config: Config) -> bool:
    title = f" {listing.title.lower()} "
    if any(kw in title for kw in config.filters.seniority_keywords):
        return False
    if any(kw in title for kw in config.filters.unwanted_keywords):
        return False
    return True


def _passes_experience_filter(listing: JobListing, config: Config) -> bool:
    """Return False if the description explicitly requires more experience than the candidate has."""
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


def _passes_region_filter(listing: JobListing, config: Config) -> bool:
    loc = listing.location.strip().lower()
    if not loc or loc in ("israel", "unknown", ""):
        return True
    return any(region.lower() in loc or loc in region.lower() for region in config.regions)


def _prefilter(listing: JobListing, config: Config) -> bool:
    """Returns True if listing should be sent to the LLM, False to skip."""
    if not _passes_region_filter(listing, config):
        return False
    if not _passes_title_filter(listing, config):
        return False
    if not _passes_experience_filter(listing, config):
        return False
    return True


def match_batch(listings: list[JobListing], cv_text: str, config: Config) -> BatchOutcome:
    """Score a batch of listings in one Groq call. Returns BatchOutcome with successful results
    keyed by listing index and a list of listings that failed to evaluate."""
    # Apply pre-filters first — filtered listings are treated as "scored 0", marked seen
    filtered_results: dict[int, MatchResult] = {}
    to_evaluate: list[tuple[int, JobListing]] = []
    for i, listing in enumerate(listings):
        if _prefilter(listing, config):
            to_evaluate.append((i, listing))
        else:
            # Pre-filter rejection — still "evaluated" with score 0, mark as seen
            filtered_results[i] = MatchResult(listing=listing, score=0, reasoning="Pre-filtered (region/seniority)")

    if not to_evaluate:
        return BatchOutcome(results=filtered_results, failed_listings=[])

    api_key = os.environ.get("GROQ_API_KEY", "")
    client = Groq(api_key=api_key)
    prompt = _build_batch_prompt([l for _, l in to_evaluate], cv_text, config)

    for attempt in range(_MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=_MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            text = response.choices[0].message.content
            time.sleep(_REQUEST_DELAY)
            parsed = _parse_batch_response(text, [l for _, l in to_evaluate])
            if parsed is None:
                # Parse failed entirely — all listings in batch are failures
                return BatchOutcome(results=filtered_results, failed_listings=[l for _, l in to_evaluate])
            # Merge LLM results into final dict
            for (original_idx, _listing), result in zip(to_evaluate, parsed):
                if result is not None:
                    filtered_results[original_idx] = result
            # Identify per-listing failures (some entries in `parsed` may be None)
            failed = [l for (_, l), r in zip(to_evaluate, parsed) if r is None]
            return BatchOutcome(results=filtered_results, failed_listings=failed)
        except Exception as e:
            err = str(e)
            if "429" in err or "rate_limit" in err.lower():
                if attempt < _MAX_RETRIES - 1:
                    logger.warning("matcher: rate limited on batch — waiting %ds (attempt %d/%d)",
                                   _RETRY_DELAY, attempt + 1, _MAX_RETRIES)
                    time.sleep(_RETRY_DELAY)
                else:
                    logger.error("matcher: quota exhausted after %d attempts — stopping run", _MAX_RETRIES)
                    raise QuotaExhausted("Groq daily quota exhausted")
            else:
                logger.warning("matcher: Groq batch call failed: %s", e)
                return BatchOutcome(results=filtered_results, failed_listings=[l for _, l in to_evaluate])

    return BatchOutcome(results=filtered_results, failed_listings=[l for _, l in to_evaluate])


def _build_batch_prompt(listings: list[JobListing], cv_text: str, config: Config) -> str:
    jobs_block = "\n\n".join(
        f"### Job {i + 1}\nTitle: {l.title}\nCompany: {l.company}\nLocation: {l.location}\nDescription: {l.description[:1000]}"
        for i, l in enumerate(listings)
    )
    return f"""You are evaluating job listings for a JUNIOR candidate (0-2 years experience, 3rd-year CS student).

RULE #1 — EXPERIENCE (NON-NEGOTIABLE):
Score EXACTLY 0 if the listing mentions ANY of: 3+ years, 4+ years, 5+ years, senior, lead, principal, head of, בכיר, ראש צוות, or any similar seniority signal. This includes ranges like "4-6 years" or "3-5 שנות". This is the most important rule — enforce it every time, no exceptions.

DATA ENGINEER EXCEPTION: For Data Engineer roles specifically, score EXACTLY 0 if the listing requires more than 1 year of experience. Apply this before all other rules.

If experience level is not mentioned, the job is eligible — continue scoring.

RULE #2 — ROLE FIT:
Wanted roles: software engineer, backend, Python, DevOps, QA, automation, data engineer, ML, cloud, infrastructure, IoT, embedded systems, IT support (L1 helpdesk only — NOT hardware repair or PC technician).
Unwanted: full-stack, UI/UX, economics, freelance, coordinator, מתאם.

RULE #3 — SKILLS:
Candidate skills: Python, C, C++, SQL, REST APIs, distributed systems, MQTT, NumPy, Pandas, Scikit-learn, AWS, Git, basic ML.
Score high (70-90) if most primary required skills match. Score low if a skill central to the role is completely absent. Missing secondary/nice-to-have skills → reduce moderately, don't reject.

## CV
{cv_text}

## Jobs to score
{jobs_block}

## Output
Return a JSON object with ONE field "results", an array of EXACTLY {len(listings)} objects in order. Each: "score" (int 0-100) and "reasoning" (one sentence stating experience requirement found, or "no experience requirement mentioned" if absent).

{{"results": [{{"score": 0, "reasoning": "Requires 5 years of experience."}}, {{"score": 75, "reasoning": "No experience requirement mentioned; Python and REST API skills match well."}}, ...]}}

JSON:"""


def _parse_batch_response(text: str, listings: list[JobListing]) -> list[MatchResult | None] | None:
    """Parse a batch response. Returns a list aligned with `listings` (None for items that failed to parse).
    Returns None if the entire response is unparseable."""
    try:
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text)
        items = data.get("results") if isinstance(data, dict) else None
        if not isinstance(items, list):
            logger.warning("matcher: batch response missing 'results' array: %r", text[:200])
            return None

        results: list[MatchResult | None] = []
        for listing, item in zip(listings, items):
            try:
                score = int(item["score"])
                reasoning = str(item["reasoning"])
                if not 0 <= score <= 100:
                    raise ValueError(f"score out of range: {score}")
                results.append(MatchResult(listing=listing, score=score, reasoning=reasoning))
            except Exception as e:
                logger.warning("matcher: failed to parse batch entry for %r: %s", listing.title, e)
                results.append(None)

        # If returned array is shorter than listings, pad with None
        while len(results) < len(listings):
            results.append(None)
        return results
    except Exception as e:
        logger.warning("matcher: failed to parse batch response %r: %s", text[:200], e)
        return None


# Backwards-compatible single-listing match (used by tests, not by orchestrator)
def match(listing: JobListing, cv_text: str, config: Config) -> MatchResult | None:
    outcome = match_batch([listing], cv_text, config)
    return outcome.results.get(0)
