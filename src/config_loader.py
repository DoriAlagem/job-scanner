from dataclasses import dataclass
from pathlib import Path
import yaml
from pypdf import PdfReader


@dataclass
class Config:
    roles: list[str]
    experience_levels: list[str]
    location: str
    regions: list[str]
    match_threshold: int
    email_language: str
    email_to: str


def load_config(config_path: str = "config.yaml") -> Config:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(path) as f:
        data = yaml.safe_load(f)

    required = ["roles", "experience_levels", "location", "regions", "match_threshold", "email_language", "email_to"]
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"Config is missing required fields: {missing}")

    return Config(
        roles=data["roles"],
        experience_levels=data["experience_levels"],
        location=data["location"],
        regions=data["regions"],
        match_threshold=data["match_threshold"],
        email_language=data["email_language"],
        email_to=data["email_to"],
    )


def load_cv_text(cv_path: str = "Dor_Alagem_CV.pdf") -> str:
    path = Path(cv_path)
    if not path.exists():
        raise FileNotFoundError(f"CV file not found: {cv_path}")

    reader = PdfReader(str(path))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return text.strip()
