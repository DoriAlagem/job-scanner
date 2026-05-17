import re
from dataclasses import dataclass
from pathlib import Path
import yaml
from pypdf import PdfReader


@dataclass
class FilterConfig:
    seniority_keywords: tuple[str, ...]
    unwanted_keywords: tuple[str, ...]
    max_years_experience: int
    role_max_years_overrides: dict[str, int] = None

    def __post_init__(self):
        if self.role_max_years_overrides is None:
            self.role_max_years_overrides = {}

    def title_is_blocked(self, title: str) -> bool:
        """True if the title matches any seniority or unwanted keyword."""
        padded = f" {title.lower()} "
        return any(kw in padded for kw in self.seniority_keywords) or \
               any(kw in padded for kw in self.unwanted_keywords)

    def max_years_for(self, title: str) -> int:
        """Effective experience cap for this title, respecting role overrides."""
        title_lower = title.lower()
        for role, override in self.role_max_years_overrides.items():
            if role in title_lower:
                return override
        return self.max_years_experience


@dataclass
class Config:
    regions: list[str]
    match_threshold: int
    email_to: str
    filters: FilterConfig
    search_terms: list[str]


def load_config(config_path: str = "config.yaml") -> Config:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(path) as f:
        data = yaml.safe_load(f)

    required = ["regions", "match_threshold", "email_to", "filters"]
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"Config is missing required fields: {missing}")

    if not isinstance(data["match_threshold"], int) or not 0 <= data["match_threshold"] <= 100:
        raise ValueError(f"match_threshold must be an integer between 0 and 100, got: {data['match_threshold']!r}")
    if not data["email_to"] or not isinstance(data["email_to"], str):
        raise ValueError("email_to must be a non-empty string")
    if not data["regions"] or not isinstance(data["regions"], list):
        raise ValueError("regions must be a non-empty list")

    f = data["filters"]
    filters = FilterConfig(
        seniority_keywords=tuple(f.get("seniority_keywords", [])),
        unwanted_keywords=tuple(f.get("unwanted_keywords", [])),
        max_years_experience=int(f.get("max_years_experience", 2)),
        role_max_years_overrides={k.lower(): int(v) for k, v in f.get("role_max_years_overrides", {}).items()},
    )

    return Config(
        regions=data["regions"],
        match_threshold=data["match_threshold"],
        email_to=data["email_to"],
        filters=filters,
        search_terms=list(data.get("search_terms", [])),
    )


def load_cv_text(cv_path: str = "Dor_Alagem_CV.pdf") -> str:
    path = Path(cv_path)
    if not path.exists():
        raise FileNotFoundError(f"CV file not found: {cv_path}")

    reader = PdfReader(str(path))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return _clean_cv_text(text)


def _clean_cv_text(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [l for l in text.splitlines() if not re.fullmatch(r"\s*\d+\s*", l)]
    return "\n".join(lines).strip()
