import json
import logging
import os
import time
from dataclasses import dataclass

from google import genai

from src.config_loader import Config
from src.models import JobListing

logger = logging.getLogger(__name__)

# gemini-1.5-flash: free tier 15 RPM, 1500 RPD — more reliable than 2.0-flash free tier
_MODEL_NAME = "gemini-1.5-flash"
_REQUEST_DELAY = 4.5  # seconds between calls — stays safely under 15 RPM
_MAX_RETRIES = 3
_RETRY_DELAY = 60  # seconds to wait on 429


@dataclass
class MatchResult:
    listing: JobListing
    score: int
    reasoning: str


def match(listing: JobListing, cv_text: str, config: Config) -> MatchResult | None:
    if not _passes_region_filter(listing, config):
        logger.debug("Skipping %r — location %r not in configured regions", listing.title, listing.location)
        return None

    api_key = os.environ.get("GEMINI_API_KEY", "")
    client = genai.Client(api_key=api_key)

    prompt = _build_prompt(listing, cv_text, config)
    for attempt in range(_MAX_RETRIES):
        try:
            response = client.models.generate_content(model=_MODEL_NAME, contents=prompt)
            time.sleep(_REQUEST_DELAY)
            return _parse_response(response.text, listing)
        except Exception as e:
            err = str(e)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                logger.warning("matcher: rate limited on %r — waiting %ds (attempt %d/%d)",
                               listing.title, _RETRY_DELAY, attempt + 1, _MAX_RETRIES)
                time.sleep(_RETRY_DELAY)
            else:
                logger.warning("matcher: Gemini call failed for %r: %s", listing.title, e)
                return None
    logger.warning("matcher: giving up on %r after %d attempts", listing.title, _MAX_RETRIES)
    return None


def _passes_region_filter(listing: JobListing, config: Config) -> bool:
    loc = listing.location.strip().lower()
    if not loc or loc in ("israel", "unknown", ""):
        return True
    return any(region.lower() in loc or loc in region.lower() for region in config.regions)


def _build_prompt(listing: JobListing, cv_text: str, config: Config) -> str:
    return f"""You are evaluating a job listing for a candidate. Score how well the candidate fits the role.

## Candidate CV
{cv_text}

## Job Listing
Title: {listing.title}
Company: {listing.company}
Location: {listing.location}
Description: {listing.description}

## Candidate Preferences
Target roles: {", ".join(config.roles)}
Experience levels accepted: {", ".join(config.experience_levels)}

## Instructions
Return ONLY a JSON object with two fields:
- "score": integer 0-100 representing how well the candidate fits this role
- "reasoning": one English sentence explaining the score

Example: {{"score": 82, "reasoning": "Strong Python and REST API experience directly matches the role requirements."}}

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
