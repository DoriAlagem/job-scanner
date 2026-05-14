import random
from src.matcher import MatchResult

_NO_MATCH_QUIPS = [
    "The job market is playing hard to get today. Try again later! 😎",
    "Zero matches. The algorithm checked twice — just to be sure. 🔍",
    "No jobs found. Even the bots are taking a day off. 🤖",
    "Nothing matched today. Your standards are high and we respect that. 👑",
    "Crickets. Actual crickets. 🦗 But don't worry — we'll keep looking.",
    "The job boards gave us nothing worth your time. You're welcome. 🛡️",
    "404: Dream job not found. We'll try again in a few hours. 🚀",
    "Nada. Zip. Zilch. But hey — at least you got an email! 📬",
]


def format_digest(
    results: list[MatchResult],
    failed_count: int = 0,
    quota_exhausted: bool = False,
) -> str:
    lines = [
        "Job Scanner Digest",
        "=" * 50,
    ]

    if results:
        lines += [f"{len(results)} matching job(s) found:", ""]
        for i, r in enumerate(results, 1):
            lines += [
                f"{i}. {r.listing.title}",
                f"   Company:  {r.listing.company}",
                f"   Location: {r.listing.location}",
                f"   Match:    {r.score}%",
                f"   Why:      {r.reasoning}",
                f"   Apply:    {r.listing.url}",
                "",
            ]
    else:
        lines += ["", random.choice(_NO_MATCH_QUIPS), ""]

    if failed_count > 0 or quota_exhausted:
        lines.append("-" * 50)
        if failed_count > 0:
            lines.append(f"⚠ {failed_count} listing(s) failed to evaluate — they will be retried in the next run.")
        if quota_exhausted:
            lines.append("⚠ Daily Groq quota was exhausted before all listings could be evaluated. Remaining listings will be retried in the next run.")

    return "\n".join(lines)
