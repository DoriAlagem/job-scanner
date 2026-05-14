import json
import logging
import os
import time
from dataclasses import dataclass

from groq import Groq

from src.config_loader import Config
from src.models import JobListing

logger = logging.getLogger(__name__)

# Llama 3.1 8B on Groq free tier: 30 RPM, 14400 RPD, fast inference
_MODEL_NAME = "llama-3.1-8b-instant"
_REQUEST_DELAY = 2.0  # seconds between calls — stays under 30 RPM
_MAX_RETRIES = 3
_RETRY_DELAY = 60  # seconds to wait on 429


class QuotaExhausted(Exception):
    """Raised when Gemini daily quota is exhausted — caller should stop and send results so far."""


@dataclass
class MatchResult:
    listing: JobListing
    score: int
    reasoning: str


_SENIORITY_KEYWORDS = (
    " senior", "senior ", "sr.", " sr ", " lead ", "team lead", "tech lead",
    "principal", "head of", " chief", "vp ", " director",
    "בכיר", "ראש צוות", " ראש ",
)


def _passes_title_filter(listing: JobListing) -> bool:
    title = f" {listing.title.lower()} "
    return not any(kw in title for kw in _SENIORITY_KEYWORDS)


def match(listing: JobListing, cv_text: str, config: Config) -> MatchResult | None:
    if not _passes_region_filter(listing, config):
        logger.debug("Skipping %r — location %r not in configured regions", listing.title, listing.location)
        return None

    if not _passes_title_filter(listing):
        logger.debug("Skipping %r — seniority keyword in title", listing.title)
        return None

    api_key = os.environ.get("GROQ_API_KEY", "")
    client = Groq(api_key=api_key)

    prompt = _build_prompt(listing, cv_text, config)
    for attempt in range(_MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=_MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            text = response.choices[0].message.content
            time.sleep(_REQUEST_DELAY)
            return _parse_response(text, listing)
        except Exception as e:
            err = str(e)
            if "429" in err or "rate_limit" in err.lower():
                if attempt < _MAX_RETRIES - 1:
                    logger.warning("matcher: rate limited on %r — waiting %ds (attempt %d/%d)",
                                   listing.title, _RETRY_DELAY, attempt + 1, _MAX_RETRIES)
                    time.sleep(_RETRY_DELAY)
                else:
                    logger.error("matcher: quota exhausted after %d attempts — stopping run", _MAX_RETRIES)
                    raise QuotaExhausted("Groq daily quota exhausted")
            else:
                logger.warning("matcher: Groq call failed for %r: %s", listing.title, e)
                return None
    return None


def _passes_region_filter(listing: JobListing, config: Config) -> bool:
    loc = listing.location.strip().lower()
    if not loc or loc in ("israel", "unknown", ""):
        return True
    return any(region.lower() in loc or loc in region.lower() for region in config.regions)


def _build_prompt(listing: JobListing, cv_text: str, config: Config) -> str:
    return f"""You are a strict job-fit evaluator for a junior Computer Science candidate. Be conservative — default to LOW scores unless the role is clearly a good fit. The email threshold is {config.match_threshold}; only listings genuinely worth applying to should reach it.

## Candidate profile
- Junior, 0–2 years of professional experience. Currently a 3rd-year CS student.
- Demonstrated skills (from CV): Python, C, C++, SQL, REST APIs, distributed systems, MQTT, automation workflows, NumPy, Pandas, Scikit-learn, AWS, Git, basic machine learning (academic).

## Candidate CV (full text)
{cv_text}

## Job listing
Title: {listing.title}
Company: {listing.company}
Location: {listing.location}
Description: {listing.description}

## Hard deal-breakers (score 0 if ANY apply)
1. Listing explicitly requires 3 or more years of experience (e.g. "3+ years", "5 years required", "must have 7 years").
2. Title or description describes a senior, lead, principal, or head-of role (Hebrew: בכיר, ראש צוות).
3. The role is hardware-focused IT support — PC technician, desktop technician, hardware repair, field technician. ONLY L1 helpdesk / user-facing software support is acceptable for IT-support-type roles.
4. A required PRIMARY skill is one the candidate has zero exposure to — e.g. "Go Developer" with no Go, "RPG Developer" with no RPG, ".NET" role with no .NET, "React Native" as primary stack with no React. (Don't penalize for missing secondary / nice-to-have skills — see soft rules below.)

## Soft rules (use judgment, don't auto-reject)
- The candidate should have MOST of the role's required primary skills, not all.
- Weigh each missing skill by how critical it is to the role:
  - Missing a CENTRAL skill (the role is named after it / it's the main daily tool) → score very low.
  - Missing SECONDARY skills (one of many bullets, nice-to-have, "experience with X is a plus") → reduce score moderately, don't reject.
- Project manager, technical PM, customer-facing engineering roles ARE acceptable if the listed required skills overlap with the candidate's skills.
- Roles outside core software (e.g. marketing, finance, sales) → score very low.
- Default to lower scores when uncertain — prefer false negatives over false positives.

## Output
Return ONLY a JSON object with two fields:
- "score": integer 0-100
- "reasoning": one English sentence explaining the score, mentioning the most decisive factor (experience cap, missing central skill, strong skill alignment, etc.)

Example of a good fit: {{"score": 82, "reasoning": "Python backend role requiring 0-2 years and REST/AWS skills directly demonstrated in the candidate's CV."}}
Example of a bad fit: {{"score": 10, "reasoning": "Role requires 5+ years of professional Go experience; candidate is junior with no Go on the CV."}}

JSON:"""


def _parse_response(text: str, listing: JobListing) -> MatchResult | None:
    try:
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text)
        score = int(data["score"])
        reasoning = str(data["reasoning"])
        if not 0 <= score <= 100:
            raise ValueError(f"Score out of range: {score}")
        return MatchResult(listing=listing, score=score, reasoning=reasoning)
    except Exception as e:
        logger.warning("matcher: failed to parse Gemini response %r: %s", text[:100], e)
        return None
