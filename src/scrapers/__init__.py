from src.scrapers import alljobs, dell, drushim, google, jobmaster, linkedin
from src.scrapers.base import Scraper


def build_registry() -> dict[str, Scraper]:
    """Return the canonical scraper registry: source name → scraper module.

    Centralises the list of active scrapers so adding a new one is a
    single-line edit here, with no changes to the orchestrator.
    """
    return {
        "drushim": drushim,
        "jobmaster": jobmaster,
        "alljobs": alljobs,
        "linkedin": linkedin,
        "google": google,
        "dell": dell,
    }
