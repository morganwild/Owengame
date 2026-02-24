"""
Job Portal Live Feeds
=====================
Fetches live job listings from UK job portals to help house buyers
assess the employment market in areas they're considering.

Data sources:
  - Adzuna API (UK's largest job aggregator — free tier at developer.adzuna.com)
  - Reed API (major UK job board — free key at reed.co.uk/developers)

Set environment variables:
  ADZUNA_APP_ID / ADZUNA_APP_KEY  — or —  REED_API_KEY
"""

import os
import re
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

import requests


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class JobListing:
    title: str
    company: str
    location: str
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    description: str = ""
    url: str = ""
    posted: str = ""
    contract_type: str = ""   # permanent, contract, temp
    category: str = ""
    source: str = ""          # adzuna / reed

    @property
    def salary_display(self) -> str:
        if self.salary_min and self.salary_max:
            if self.salary_min == self.salary_max:
                return f"£{self.salary_min:,.0f}"
            return f"£{self.salary_min:,.0f} – £{self.salary_max:,.0f}"
        if self.salary_min:
            return f"From £{self.salary_min:,.0f}"
        if self.salary_max:
            return f"Up to £{self.salary_max:,.0f}"
        return "Not specified"

    @property
    def salary_mid(self) -> Optional[float]:
        if self.salary_min and self.salary_max:
            return (self.salary_min + self.salary_max) / 2
        return self.salary_min or self.salary_max

    def summary(self) -> str:
        return (
            f"{self.title} @ {self.company}\n"
            f"  {self.location} | {self.salary_display} | {self.contract_type or 'N/A'}\n"
            f"  {self.url}"
        )


@dataclass
class JobSearchCriteria:
    keywords: str = ""
    location: str = ""             # town / city / postcode
    distance_km: int = 16          # ~10 miles default
    min_salary: Optional[int] = None
    max_salary: Optional[int] = None
    contract_type: str = ""        # permanent, contract, temp
    category: str = ""
    max_results: int = 20

    def matches(self, job: JobListing) -> bool:
        if self.min_salary and job.salary_max and job.salary_max < self.min_salary:
            return False
        if self.max_salary and job.salary_min and job.salary_min > self.max_salary:
            return False
        if self.contract_type:
            if self.contract_type.lower() not in (job.contract_type or "").lower():
                return False
        return True


# ---------------------------------------------------------------------------
# Adzuna API
# ---------------------------------------------------------------------------

ADZUNA_BASE = "https://api.adzuna.com/v1/api/jobs/gb/search"

# Standard Adzuna job categories
ADZUNA_CATEGORIES = {
    "it": "IT Jobs",
    "engineering": "Engineering Jobs",
    "healthcare": "Healthcare & Nursing Jobs",
    "teaching": "Teaching Jobs",
    "accounting": "Accounting & Finance Jobs",
    "sales": "Sales Jobs",
    "admin": "Admin Jobs",
    "legal": "Legal Jobs",
    "construction": "Trade & Construction Jobs",
    "retail": "Retail Jobs",
    "hospitality": "Hospitality & Catering Jobs",
    "logistics": "Logistics & Warehouse Jobs",
    "manufacturing": "Manufacturing Jobs",
    "scientific": "Scientific & QA Jobs",
    "social": "Social work Jobs",
    "creative": "Creative & Design Jobs",
    "hr": "HR & Recruitment Jobs",
    "property": "Property Jobs",
    "energy": "Energy, Oil & Gas Jobs",
    "charity": "Charity & Voluntary Jobs",
}


def _get_adzuna_creds() -> tuple[Optional[str], Optional[str]]:
    return (
        os.environ.get("ADZUNA_APP_ID"),
        os.environ.get("ADZUNA_APP_KEY"),
    )


def search_adzuna(
    criteria: JobSearchCriteria,
    page: int = 1,
) -> list[JobListing]:
    """Search Adzuna API for jobs. Requires ADZUNA_APP_ID / ADZUNA_APP_KEY env vars."""
    app_id, app_key = _get_adzuna_creds()
    if not app_id or not app_key:
        return []

    params: dict = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": min(criteria.max_results, 50),
        "content-type": "application/json",
    }

    if criteria.keywords:
        params["what"] = criteria.keywords
    if criteria.location:
        params["where"] = criteria.location
        params["distance"] = criteria.distance_km
    if criteria.min_salary:
        params["salary_min"] = criteria.min_salary
    if criteria.max_salary:
        params["salary_max"] = criteria.max_salary
    if criteria.contract_type:
        ct_map = {"permanent": "permanent", "contract": "contract", "temp": "contract"}
        params["contract_type"] = ct_map.get(criteria.contract_type.lower(), "")
    if criteria.category:
        params["category"] = criteria.category

    try:
        resp = requests.get(
            f"{ADZUNA_BASE}/{page}",
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    jobs = []
    for item in data.get("results", []):
        jobs.append(JobListing(
            title=item.get("title", "").strip(),
            company=item.get("company", {}).get("display_name", "Unknown"),
            location=item.get("location", {}).get("display_name", ""),
            salary_min=item.get("salary_min"),
            salary_max=item.get("salary_max"),
            description=_clean_html(item.get("description", "")),
            url=item.get("redirect_url", ""),
            posted=_parse_date(item.get("created", "")),
            contract_type=item.get("contract_type", "") or "",
            category=item.get("category", {}).get("label", ""),
            source="adzuna",
        ))

    return jobs


def get_adzuna_salary_stats(location: str, category: str = "") -> Optional[dict]:
    """Get salary histogram / stats for a location from Adzuna."""
    app_id, app_key = _get_adzuna_creds()
    if not app_id or not app_key:
        return None

    params: dict = {
        "app_id": app_id,
        "app_key": app_key,
        "location0": "UK",
        "location1": location,
    }
    if category:
        params["category"] = category

    try:
        resp = requests.get(
            "https://api.adzuna.com/v1/api/jobs/gb/history",
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        # Returns monthly average salary data
        if data.get("month"):
            months = data["month"]
            recent = list(months.values())[-6:]  # last 6 months
            return {
                "avg_salary": round(sum(recent) / len(recent)),
                "trend": recent,
                "months": list(months.keys())[-6:],
            }
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Reed API
# ---------------------------------------------------------------------------

REED_BASE = "https://www.reed.co.uk/api/1.0/search"


def _get_reed_key() -> Optional[str]:
    return os.environ.get("REED_API_KEY")


def search_reed(criteria: JobSearchCriteria) -> list[JobListing]:
    """Search Reed API for jobs. Requires REED_API_KEY env var."""
    api_key = _get_reed_key()
    if not api_key:
        return []

    params: dict = {
        "resultsToTake": min(criteria.max_results, 100),
    }

    if criteria.keywords:
        params["keywords"] = criteria.keywords
    if criteria.location:
        params["locationName"] = criteria.location
        params["distancefromlocation"] = max(1, criteria.distance_km // 2)  # Reed uses miles
    if criteria.min_salary:
        params["minimumSalary"] = criteria.min_salary
    if criteria.max_salary:
        params["maximumSalary"] = criteria.max_salary
    if criteria.contract_type:
        if criteria.contract_type.lower() == "permanent":
            params["permanent"] = "true"
        elif criteria.contract_type.lower() in ("contract", "temp"):
            params["contract"] = "true"

    try:
        resp = requests.get(
            REED_BASE,
            params=params,
            auth=(api_key, ""),  # Reed uses API key as basic auth username
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    jobs = []
    for item in data.get("results", []):
        jobs.append(JobListing(
            title=item.get("jobTitle", "").strip(),
            company=item.get("employerName", "Unknown"),
            location=item.get("locationName", ""),
            salary_min=item.get("minimumSalary"),
            salary_max=item.get("maximumSalary"),
            description=_clean_html(item.get("jobDescription", "")),
            url=item.get("jobUrl", ""),
            posted=_parse_date(item.get("date", "")),
            contract_type="permanent" if item.get("isPermanent") else "contract" if item.get("isContract") else "",
            category=item.get("category", "") if isinstance(item.get("category"), str) else "",
            source="reed",
        ))

    return jobs


# ---------------------------------------------------------------------------
# Unified search + statistics
# ---------------------------------------------------------------------------

def search_jobs(criteria: JobSearchCriteria) -> list[JobListing]:
    """
    Search all configured job portals and merge results.
    Tries Adzuna first, then Reed. Uses whichever has credentials configured.
    """
    jobs: list[JobListing] = []

    # Try Adzuna
    adzuna_jobs = search_adzuna(criteria)
    jobs.extend(adzuna_jobs)

    # Try Reed
    reed_jobs = search_reed(criteria)
    jobs.extend(reed_jobs)

    # Apply local filters (salary range, contract type)
    jobs = [j for j in jobs if criteria.matches(j)]

    # Deduplicate by title + company
    seen = set()
    unique = []
    for j in jobs:
        key = (j.title.lower().strip(), j.company.lower().strip())
        if key not in seen:
            seen.add(key)
            unique.append(j)

    return unique[:criteria.max_results]


def area_job_stats(location: str) -> dict:
    """
    Get job market summary statistics for an area.
    Useful for assessing employment prospects before buying.
    """
    criteria = JobSearchCriteria(
        location=location,
        max_results=50,
    )
    jobs = search_jobs(criteria)

    if not jobs:
        return {
            "count": 0,
            "location": location,
            "message": "No jobs found — check your API keys (ADZUNA_APP_ID/ADZUNA_APP_KEY or REED_API_KEY)",
            "sources_configured": _sources_configured(),
        }

    # Salary analysis
    salaries = [j.salary_mid for j in jobs if j.salary_mid and j.salary_mid > 0]
    salary_stats = {}
    if salaries:
        sorted_sal = sorted(salaries)
        n = len(sorted_sal)
        salary_stats = {
            "count_with_salary": n,
            "min": round(sorted_sal[0]),
            "max": round(sorted_sal[-1]),
            "mean": round(sum(sorted_sal) / n),
            "median": round(sorted_sal[n // 2]),
        }

    # Category breakdown
    categories: dict[str, list[float]] = {}
    for j in jobs:
        cat = j.category or "Other"
        categories.setdefault(cat, [])
        if j.salary_mid and j.salary_mid > 0:
            categories[cat].append(j.salary_mid)

    cat_stats = {}
    for cat, sals in sorted(categories.items(), key=lambda x: -len(x[1]) if x[1] else 0):
        cat_stats[cat] = {
            "count": sum(1 for j in jobs if (j.category or "Other") == cat),
            "avg_salary": round(sum(sals) / len(sals)) if sals else None,
        }

    # Contract type breakdown
    contract_counts: dict[str, int] = {}
    for j in jobs:
        ct = j.contract_type.capitalize() if j.contract_type else "Not specified"
        contract_counts[ct] = contract_counts.get(ct, 0) + 1

    # Top employers
    employer_counts: dict[str, int] = {}
    for j in jobs:
        employer_counts[j.company] = employer_counts.get(j.company, 0) + 1
    top_employers = sorted(employer_counts.items(), key=lambda x: -x[1])[:10]

    return {
        "count": len(jobs),
        "location": location,
        "salary": salary_stats,
        "by_category": cat_stats,
        "by_contract": contract_counts,
        "top_employers": [{"name": e[0], "openings": e[1]} for e in top_employers],
        "sources_configured": _sources_configured(),
        "sample_jobs": [
            {
                "title": j.title,
                "company": j.company,
                "salary": j.salary_display,
                "type": j.contract_type or "N/A",
                "url": j.url,
            }
            for j in jobs[:10]
        ],
    }


def _sources_configured() -> dict:
    app_id, app_key = _get_adzuna_creds()
    return {
        "adzuna": bool(app_id and app_key),
        "reed": bool(_get_reed_key()),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def _parse_date(date_str: str) -> str:
    if not date_str:
        return ""
    # Try ISO format
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str[:19], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_str[:10]
