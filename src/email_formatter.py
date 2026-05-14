from src.matcher import MatchResult


def format_digest(
    results: list[MatchResult],
    failed_count: int = 0,
    quota_exhausted: bool = False,
) -> str:
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

    if failed_count > 0 or quota_exhausted:
        lines.append("-" * 50)
        if failed_count > 0:
            lines.append(f"⚠ {failed_count} listing(s) failed to evaluate — they will be retried in the next run.")
        if quota_exhausted:
            lines.append("⚠ Daily Groq quota was exhausted before all listings could be evaluated. Remaining listings will be retried in the next run.")

    return "\n".join(lines)
