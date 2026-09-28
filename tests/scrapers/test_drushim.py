from src.scrapers.drushim import _parse_listings

_HTML = """
<article class="job-card-module-x__abc__card" data-nagish="job-card-item">
  <h3 class="job-card-header-module-x__abc__title">מפתח/ת Python</h3>
  <span class="job-card-header-module-x__abc__companyName">Acme</span>
  <div class="job-card-meta-module-x__abc__row"><span>תל אביב</span></div>
  <div class="job-card-meta-module-x__abc__row"><span>3-4 שנים</span> <span>משרה מלאה</span></div>
  <div class="job-card-meta-module-x__abc__row"><span>לפני 5 דקות</span></div>
  <p class="job-card-module-x__abc__description">Backend role</p>
  <a class="job-card-module-x__abc__readMoreBtn" href="/job/1/abc/">פרטי המשרה</a>
  <a class="job-card-module-x__abc__applyBtn" href="/job/1/abc/">הגשת מועמדות</a>
</article>
"""


def test_parses_job_card():
    [job] = _parse_listings(_HTML, set())
    assert job.title == "מפתח/ת Python"
    assert job.company == "Acme"
    assert job.location == "תל אביב"
    assert job.url == "https://www.drushim.co.il/job/1/abc/"
    assert "3-4 שנים" in job.description and "Backend role" in job.description


def test_dedups_by_url():
    seen: set[str] = set()
    assert len(_parse_listings(_HTML, seen)) == 1
    assert _parse_listings(_HTML, seen) == []
