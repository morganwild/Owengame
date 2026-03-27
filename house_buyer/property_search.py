"""
Property Search Module
======================
Fetches new property listings from Rightmove RSS feeds and filters them
against user-defined criteria (price, bedrooms, location, property type).

How Rightmove RSS works:
  1. Go to rightmove.co.uk and set up a search with your criteria
  2. Copy the URL — it looks like:
     https://www.rightmove.co.uk/property-for-sale/find.html?locationIdentifier=REGION%5E...&minBedrooms=2&maxPrice=350000
  3. Replace '/property-for-sale/find.html' with '/rss.jsp' — same params work
  4. That RSS feed updates as new properties are listed

This module parses those feeds and applies local filtering.
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import requests


@dataclass
class Property:
    title: str
    price: Optional[int]
    url: str
    address: str
    description: str
    bedrooms: Optional[int]
    published: Optional[str]
    image_url: Optional[str] = None
    property_type: Optional[str] = None  # detached, semi, terrace, flat

    def summary(self) -> str:
        price_str = f"£{self.price:,}" if self.price else "POA"
        beds = f"{self.bedrooms} bed" if self.bedrooms else "? bed"
        return f"{beds} | {price_str} | {self.address}\n  {self.url}"


@dataclass
class SearchCriteria:
    """User-defined filters applied on top of the RSS feed results."""
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    min_bedrooms: Optional[int] = None
    max_bedrooms: Optional[int] = None
    keywords: list[str] = field(default_factory=list)       # must appear in title/desc
    exclude_keywords: list[str] = field(default_factory=list)  # must NOT appear
    property_types: list[str] = field(default_factory=list)    # e.g. ["detached", "semi"]

    def matches(self, prop: Property) -> bool:
        if self.min_price and prop.price and prop.price < self.min_price:
            return False
        if self.max_price and prop.price and prop.price > self.max_price:
            return False
        if self.min_bedrooms and prop.bedrooms and prop.bedrooms < self.min_bedrooms:
            return False
        if self.max_bedrooms and prop.bedrooms and prop.bedrooms > self.max_bedrooms:
            return False

        text = f"{prop.title} {prop.description} {prop.address}".lower()

        if self.keywords:
            if not all(kw.lower() in text for kw in self.keywords):
                return False
        if self.exclude_keywords:
            if any(kw.lower() in text for kw in self.exclude_keywords):
                return False
        if self.property_types and prop.property_type:
            if prop.property_type.lower() not in [pt.lower() for pt in self.property_types]:
                return False

        return True


def _extract_price(text: str) -> Optional[int]:
    """Pull a price like £350,000 from text."""
    match = re.search(r"£([\d,]+)", text)
    if match:
        return int(match.group(1).replace(",", ""))
    return None


def _extract_bedrooms(text: str) -> Optional[int]:
    """Pull bedroom count from text like '3 bedroom' or '3 bed'."""
    match = re.search(r"(\d+)\s*bed", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def _detect_property_type(text: str) -> Optional[str]:
    """Detect property type from description text."""
    text_lower = text.lower()
    for ptype in ["detached", "semi-detached", "terraced", "flat",
                   "apartment", "bungalow", "cottage", "maisonette", "end of terrace"]:
        if ptype in text_lower:
            return ptype
    return None


def fetch_rightmove_rss(rss_url: str, timeout: int = 15) -> list[Property]:
    """Fetch and parse a Rightmove RSS feed URL into Property objects."""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; HouseBuyerTool/1.0)"
    }
    resp = requests.get(rss_url, headers=headers, timeout=timeout)
    resp.raise_for_status()

    root = ET.fromstring(resp.content)
    properties = []

    # RSS 2.0 structure: rss > channel > item
    for item in root.iter("item"):
        title = item.findtext("title", "")
        link = item.findtext("link", "")
        desc = item.findtext("description", "")
        pub_date = item.findtext("pubDate", "")

        # Extract image from description HTML or media namespace
        image_url = None
        img_match = re.search(r'<img[^>]+src="([^"]+)"', desc)
        if img_match:
            image_url = img_match.group(1)

        # Clean HTML from description
        clean_desc = re.sub(r"<[^>]+>", "", desc).strip()
        combined_text = f"{title} {clean_desc}"

        prop = Property(
            title=title,
            price=_extract_price(combined_text),
            url=link,
            address=title,  # Rightmove puts address in the title
            description=clean_desc,
            bedrooms=_extract_bedrooms(combined_text),
            published=pub_date,
            image_url=image_url,
            property_type=_detect_property_type(combined_text),
        )
        properties.append(prop)

    return properties


def search_properties(rss_url: str, criteria: SearchCriteria) -> list[Property]:
    """Fetch from RSS and filter by criteria."""
    all_props = fetch_rightmove_rss(rss_url)
    return [p for p in all_props if criteria.matches(p)]


# --- Demo / manual property entry for when RSS isn't available ---

def create_manual_property(
    address: str,
    price: int,
    bedrooms: int,
    property_type: str = "",
    url: str = "",
    description: str = "",
) -> Property:
    """Create a property manually for analysis when RSS isn't available."""
    return Property(
        title=f"{bedrooms} bed {property_type} - {address}",
        price=price,
        url=url,
        address=address,
        description=description,
        bedrooms=bedrooms,
        published=datetime.now().strftime("%a, %d %b %Y %H:%M:%S"),
        property_type=property_type or None,
    )
