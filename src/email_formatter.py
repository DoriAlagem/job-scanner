from src.matcher import MatchResult


def format_digest(results: list[MatchResult]) -> str:
    if not results:
        return "No matching job listings found in this run."

    lines = [
        "Job Scanner Digest",
        "=" * 50,
        f"{len(results)} matching job(s) found:",
        "",
    ]

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

    return "\n".join(lines)
