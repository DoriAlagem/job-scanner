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


@dataclass
class Config:
    roles: list[str]
    experience_levels: list[str]
    location: str
    regions: list[str]
    match_threshold: int
    email_language: str
    email_to: str
    filters: FilterConfig


def load_config(config_path: str = "config.yaml") -> Config:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(path) as f:
        data = yaml.safe_load(f)

    required = ["roles", "experience_levels", "location", "regions", "match_threshold", "email_language", "email_to", "filters"]
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"Config is missing required fields: {missing}")

    f = data["filters"]
    filters = FilterConfig(
        seniority_keywords=tuple(f.get("seniority_keywords", [])),
        unwanted_keywords=tuple(f.get("unwanted_keywords", [])),
        max_years_experience=int(f.get("max_years_experience", 2)),
        role_max_years_overrides={k.lower(): int(v) for k, v in f.get("role_max_years_overrides", {}).items()},
    )

    return Config(
        roles=data["roles"],
        experience_levels=data["experience_levels"],
        location=data["location"],
        regions=data["regions"],
        match_threshold=data["match_threshold"],
        email_language=data["email_language"],
        email_to=data["email_to"],
        filters=filters,
    )


def load_cv_text(cv_path: str = "Dor_Alagem_CV.pdf") -> str:
    path = Path(cv_path)
    if not path.exists():
        raise FileNotFoundError(f"CV file not found: {cv_path}")

    reader = PdfReader(str(path))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return text.strip()
