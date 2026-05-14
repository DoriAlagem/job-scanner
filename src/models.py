from dataclasses import dataclass


@dataclass
class JobListing:
    title: str
    company: str
    location: str
    url: str
    description: str
    source: str
