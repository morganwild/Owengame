"""
Property Feeds — Live House Search
====================================
Fetches live property listings from UK property portals to help you find
houses for sale in your target area.

Data sources:
  - Zoopla API (developer.zoopla.co.uk — requires free API key)
  - Nestoria API (free, no key needed — aggregates multiple portals)

Set environment variable:
  ZOOPLA_API_KEY  — for Zoopla results (optional, Nestoria works without keys)
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
class PropertyListing:
    title: str
    price: Optional[int] = None
    address: str = ""
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    property_type: str = ""      # detached, semi, flat, etc.
    description: str = ""
    url: str = ""
    image_url: str = ""
    listing_status: str = ""     # for_sale, under_offer, sold_stc
    agent_name: str = ""
    listed_date: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    source: str = ""             # zoopla / nestoria

    @property
    def price_display(self) -> str:
        if self.price:
            return f"£{self.price:,}"
        return "POA"

    def summary(self) -> str:
        beds = f"{self.bedrooms} bed" if self.bedrooms else "? bed"
        ptype = self.property_type or ""
        return (
            f"{beds} {ptype} — {self.price_display}\n"
            f"  {self.address}\n"
            f"  {self.url}"
        )


@dataclass
class PropertySearchCriteria:
    location: str = ""               # town, city, or postcode
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    min_bedrooms: Optional[int] = None
    max_bedrooms: Optional[int] = None
    property_type: str = ""          # detached, semi, flat, terraced, bungalow
    keywords: str = ""               # e.g. "garden garage"
    radius_miles: float = 1.0
    listing_status: str = "sale"     # sale, rent
    max_results: int = 20

    def matches(self, listing: PropertyListing) -> bool:
        if self.min_price and listing.price and listing.price < self.min_price:
            return False
        if self.max_price and listing.price and listing.price > self.max_price:
            return False
        if self.min_bedrooms and listing.bedrooms and listing.bedrooms < self.min_bedrooms:
            return False
        if self.max_bedrooms and listing.bedrooms and listing.bedrooms > self.max_bedrooms:
            return False
        if self.property_type:
            if self.property_type.lower() not in (listing.property_type or "").lower():
                return False
        if self.keywords:
            text = f"{listing.title} {listing.description} {listing.address}".lower()
            if not all(kw.lower() in text for kw in self.keywords.split()):
                return False
        return True


# ---------------------------------------------------------------------------
# Zoopla API
# ---------------------------------------------------------------------------

ZOOPLA_BASE = "https://api.zoopla.co.uk/api/v1/property_listings.json"

ZOOPLA_PROPERTY_TYPES = [
    "detached", "semi-detached", "terraced", "flat",
    "bungalow", "maisonette", "land", "park_home",
]


def _get_zoopla_key() -> Optional[str]:
    return os.environ.get("ZOOPLA_API_KEY")


def search_zoopla(criteria: PropertySearchCriteria, page: int = 1) -> list[PropertyListing]:
    """Search Zoopla API for property listings. Requires ZOOPLA_API_KEY env var."""
    api_key = _get_zoopla_key()
    if not api_key:
        return []

    params: dict = {
        "api_key": api_key,
        "area": criteria.location,
        "radius": criteria.radius_miles,
        "listing_status": criteria.listing_status,
        "page_number": page,
        "page_size": min(criteria.max_results, 100),
        "order_by": "age",
        "ordering": "descending",
    }

    if criteria.min_price:
        params["minimum_price"] = criteria.min_price
    if criteria.max_price:
        params["maximum_price"] = criteria.max_price
    if criteria.min_bedrooms:
        params["minimum_beds"] = criteria.min_bedrooms
    if criteria.max_bedrooms:
        params["maximum_beds"] = criteria.max_bedrooms
    if criteria.property_type:
        params["property_type"] = criteria.property_type
    if criteria.keywords:
        params["keywords"] = criteria.keywords

    try:
        resp = requests.get(ZOOPLA_BASE, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    listings = []
    for item in data.get("listing", []):
        listings.append(PropertyListing(
            title=item.get("displayable_address", ""),
            price=_safe_int(item.get("price")),
            address=item.get("displayable_address", ""),
            bedrooms=_safe_int(item.get("num_bedrooms")),
            bathrooms=_safe_int(item.get("num_bathrooms")),
            property_type=item.get("property_type", ""),
            description=_clean_html(item.get("description", ""))[:500],
            url=item.get("details_url", ""),
            image_url=item.get("image_url", ""),
            listing_status=item.get("listing_status", ""),
            agent_name=item.get("agent_name", ""),
            listed_date=_parse_date(item.get("first_published_date", "")),
            latitude=_safe_float(item.get("latitude")),
            longitude=_safe_float(item.get("longitude")),
            source="zoopla",
        ))

    return listings


def get_zoopla_area_stats(location: str) -> Optional[dict]:
    """Get area value estimates from Zoopla."""
    api_key = _get_zoopla_key()
    if not api_key:
        return None

    try:
        resp = requests.get(
            "https://api.zoopla.co.uk/api/v1/area_value_graphs.json",
            params={"api_key": api_key, "area": location, "output_type": "outcode"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("average_values_graph_url"):
            return {
                "average_sold_price": data.get("average_sold_price_1year"),
                "average_sold_price_7year": data.get("average_sold_price_7year"),
                "number_of_sales_1year": data.get("number_of_sales_1year"),
                "number_of_sales_7year": data.get("number_of_sales_7year"),
                "turnover": data.get("turnover"),
                "prices_url": data.get("area_values_url", ""),
            }
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Nestoria API (free — no API key required)
# ---------------------------------------------------------------------------

NESTORIA_BASE = "https://api.nestoria.co.uk/api"


def search_nestoria(criteria: PropertySearchCriteria, page: int = 1) -> list[PropertyListing]:
    """
    Search Nestoria API for UK property listings.
    Free API — no key required. Aggregates from multiple portals.
    """
    params: dict = {
        "action": "search_listings",
        "encoding": "json",
        "country": "uk",
        "listing_type": "buy" if criteria.listing_status == "sale" else "rent",
        "page": page,
        "number_of_results": min(criteria.max_results, 50),
        "sort": "newest",
    }

    if criteria.location:
        params["place_name"] = criteria.location

    if criteria.min_price:
        params["price_min"] = criteria.min_price
    if criteria.max_price:
        params["price_max"] = criteria.max_price
    if criteria.min_bedrooms:
        params["bedroom_min"] = criteria.min_bedrooms
    if criteria.max_bedrooms:
        params["bedroom_max"] = criteria.max_bedrooms
    if criteria.property_type:
        params["property_type"] = criteria.property_type
    if criteria.keywords:
        params["keywords"] = criteria.keywords

    try:
        resp = requests.get(NESTORIA_BASE, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    response = data.get("response", {})
    listings = []

    for item in response.get("listings", []):
        listings.append(PropertyListing(
            title=item.get("title", ""),
            price=_safe_int(item.get("price")),
            address=_build_nestoria_address(item),
            bedrooms=_safe_int(item.get("bedroom_number")),
            bathrooms=_safe_int(item.get("bathroom_number")),
            property_type=item.get("property_type", ""),
            description=_clean_html(item.get("summary", ""))[:500],
            url=item.get("lister_url", "") or item.get("listing_url", ""),
            image_url=item.get("img_url", ""),
            listing_status="for_sale",
            agent_name=item.get("datasource_name", ""),
            listed_date=_parse_date(item.get("updated_in_days_formatted", "")),
            latitude=_safe_float(item.get("latitude")),
            longitude=_safe_float(item.get("longitude")),
            source="nestoria",
        ))

    return listings


def _build_nestoria_address(item: dict) -> str:
    parts = []
    if item.get("title"):
        parts.append(item["title"])
    return ", ".join(parts) if parts else "Address not available"


# ---------------------------------------------------------------------------
# Unified search + area statistics
# ---------------------------------------------------------------------------

def search_property_feeds(criteria: PropertySearchCriteria) -> list[PropertyListing]:
    """
    Search all configured property portals and merge results.
    Tries Zoopla first (if key set), then Nestoria (always available).
    """
    listings: list[PropertyListing] = []

    # Try Zoopla
    zoopla = search_zoopla(criteria)
    listings.extend(zoopla)

    # Try Nestoria (free, always available)
    nestoria = search_nestoria(criteria)
    listings.extend(nestoria)

    # Apply local filters
    listings = [l for l in listings if criteria.matches(l)]

    # Deduplicate by address + price (same property from different sources)
    seen = set()
    unique = []
    for l in listings:
        key = (l.address.lower().strip(), l.price)
        if key not in seen:
            seen.add(key)
            unique.append(l)

    return unique[:criteria.max_results]


def area_property_stats(location: str, criteria: Optional[PropertySearchCriteria] = None) -> dict:
    """
    Get property market summary for an area.
    Shows price ranges, type breakdown, and available listings.
    """
    if criteria is None:
        criteria = PropertySearchCriteria(
            location=location,
            max_results=50,
        )

    listings = search_property_feeds(criteria)

    if not listings:
        return {
            "count": 0,
            "location": location,
            "message": "No properties found — try a different location or check your ZOOPLA_API_KEY",
            "sources_configured": _sources_configured(),
        }

    # Price analysis
    prices = [l.price for l in listings if l.price and l.price > 0]
    price_stats = {}
    if prices:
        sorted_p = sorted(prices)
        n = len(sorted_p)
        price_stats = {
            "count_with_price": n,
            "min": sorted_p[0],
            "max": sorted_p[-1],
            "mean": round(sum(sorted_p) / n),
            "median": sorted_p[n // 2],
        }

    # Property type breakdown
    types: dict[str, list[int]] = {}
    for l in listings:
        ptype = l.property_type.capitalize() if l.property_type else "Other"
        types.setdefault(ptype, [])
        if l.price and l.price > 0:
            types[ptype].append(l.price)

    type_stats = {}
    for ptype, prs in sorted(types.items(), key=lambda x: -len(x[1]) if x[1] else 0):
        type_stats[ptype] = {
            "count": sum(1 for l in listings if (l.property_type.capitalize() if l.property_type else "Other") == ptype),
            "avg_price": round(sum(prs) / len(prs)) if prs else None,
            "min_price": min(prs) if prs else None,
            "max_price": max(prs) if prs else None,
        }

    # Bedroom breakdown
    bed_counts: dict[str, list[int]] = {}
    for l in listings:
        beds = f"{l.bedrooms} bed" if l.bedrooms else "Unknown"
        bed_counts.setdefault(beds, [])
        if l.price and l.price > 0:
            bed_counts[beds].append(l.price)

    bed_stats = {}
    for beds, prs in sorted(bed_counts.items()):
        bed_stats[beds] = {
            "count": sum(1 for l in listings if (f"{l.bedrooms} bed" if l.bedrooms else "Unknown") == beds),
            "avg_price": round(sum(prs) / len(prs)) if prs else None,
        }

    # Top agents
    agent_counts: dict[str, int] = {}
    for l in listings:
        if l.agent_name:
            agent_counts[l.agent_name] = agent_counts.get(l.agent_name, 0) + 1
    top_agents = sorted(agent_counts.items(), key=lambda x: -x[1])[:10]

    return {
        "count": len(listings),
        "location": location,
        "prices": price_stats,
        "by_type": type_stats,
        "by_bedrooms": bed_stats,
        "top_agents": [{"name": a[0], "listings": a[1]} for a in top_agents],
        "sources_configured": _sources_configured(),
        "sample_listings": [
            {
                "title": l.title,
                "address": l.address,
                "price": l.price_display,
                "bedrooms": l.bedrooms,
                "type": l.property_type or "N/A",
                "agent": l.agent_name,
                "url": l.url,
                "source": l.source,
            }
            for l in listings[:10]
        ],
    }


def _sources_configured() -> dict:
    return {
        "zoopla": bool(_get_zoopla_key()),
        "nestoria": True,  # Always available — no key needed
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def _parse_date(date_str: str) -> str:
    if not date_str:
        return ""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S",
                "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str[:19], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_str[:10]


def _safe_int(val) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def _safe_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
