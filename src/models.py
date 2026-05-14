from dataclasses import dataclass


@dataclass
class JobListing:
    title: str
    company: str
    location: str
    url: str
    description: str
    source: str

    def __post_init__(self) -> None:
        if not self.url:
            raise ValueError("JobListing.url must be non-empty")
        if not self.title:
            raise ValueError("JobListing.title must be non-empty")
        if not self.source:
            raise ValueError("JobListing.source must be non-empty")
