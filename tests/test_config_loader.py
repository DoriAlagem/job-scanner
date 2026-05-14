import pytest
import yaml
from pathlib import Path
from src.config_loader import load_config, load_cv_text, Config, FilterConfig

_FILTERS = {
    "seniority_keywords": [" senior", "senior ", "principal"],
    "unwanted_keywords": ["full stack", "freelance"],
    "max_years_experience": 2,
}


@pytest.fixture
def config_file(tmp_path):
    data = {
        "roles": ["Backend Developer", "Python Developer"],
        "experience_levels": ["entry level", "junior", "0-2 years experience"],
        "location": "Israel",
        "regions": ["תל אביב", "Tel Aviv", "הרצליה"],
        "match_threshold": 70,
        "email_language": "English",
        "email_to": "dor3382@gmail.com",
        "filters": _FILTERS,
    }
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(data))
    return p


def test_load_config_returns_correct_values(config_file):
    config = load_config(str(config_file))
    assert config.roles == ["Backend Developer", "Python Developer"]
    assert config.experience_levels == ["entry level", "junior", "0-2 years experience"]
    assert config.location == "Israel"
    assert config.regions == ["תל אביב", "Tel Aviv", "הרצליה"]
    assert config.match_threshold == 70
    assert config.email_language == "English"
    assert config.email_to == "dor3382@gmail.com"


def test_load_config_loads_filters(config_file):
    config = load_config(str(config_file))
    assert isinstance(config.filters, FilterConfig)
    assert " senior" in config.filters.seniority_keywords
    assert "full stack" in config.filters.unwanted_keywords
    assert config.filters.max_years_experience == 2


def test_load_config_raises_on_missing_file():
    with pytest.raises(FileNotFoundError, match="Config file not found"):
        load_config("nonexistent.yaml")


def test_load_config_raises_on_missing_fields(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump({"roles": ["Backend Developer"]}))
    with pytest.raises(ValueError, match="missing required fields"):
        load_config(str(p))


def test_load_cv_text_returns_nonempty_string():
    cv_path = str(Path(__file__).parent.parent / "Dor_Alagem_CV.pdf")
    text = load_cv_text(cv_path)
    assert isinstance(text, str)
    assert len(text) > 100


def test_load_cv_text_raises_on_missing_file():
    with pytest.raises(FileNotFoundError, match="CV file not found"):
        load_cv_text("nonexistent.pdf")
