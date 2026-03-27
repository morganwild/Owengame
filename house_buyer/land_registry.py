"""
Land Registry Price Paid Data
==============================
Queries the UK Land Registry's Linked Data API (free, no key required)
to get recent sale prices in an area — useful for checking whether a
property is fairly priced.

API endpoint: https://landregistry.data.gov.uk/
Uses SPARQL queries via their public endpoint.
"""

from dataclasses import dataclass
from typing import Optional

import requests


SPARQL_ENDPOINT = "https://landregistry.data.gov.uk/app/root/qonsole/query"
PPD_API = "https://landregistry.data.gov.uk/data/ppi/transaction-record.json"


@dataclass
class SoldPrice:
    address: str
    price: int
    date: str
    property_type: str  # D=Detached, S=Semi, T=Terraced, F=Flat
    new_build: bool
    postcode: str

    TYPE_MAP = {"D": "Detached", "S": "Semi-detached", "T": "Terraced", "F": "Flat/Maisonette", "O": "Other"}

    @property
    def type_name(self) -> str:
        return self.TYPE_MAP.get(self.property_type, self.property_type)

    def summary(self) -> str:
        nb = " (new build)" if self.new_build else ""
        return f"£{self.price:,} — {self.type_name}{nb} — {self.address} — {self.date}"


def search_sold_prices(
    postcode: Optional[str] = None,
    town: Optional[str] = None,
    max_results: int = 20,
    min_date: str = "2023-01-01",
) -> list[SoldPrice]:
    """
    Search Land Registry Price Paid Data.

    Uses the linked data API with JSON output.
    At least one of postcode or town must be provided.
    Postcode can be full (SW1A 1AA) or partial (SW1A).
    """
    # Build SPARQL query
    filters = []
    if postcode:
        clean_pc = postcode.strip().upper()
        if len(clean_pc) <= 4:
            # Outcode only — prefix match
            filters.append(f'FILTER(STRSTARTS(?postcode, "{clean_pc}"))')
        else:
            filters.append(f'FILTER(?postcode = "{clean_pc}")')

    if town:
        filters.append(f'FILTER(CONTAINS(UCASE(?town), "{town.strip().upper()}"))')

    if not filters:
        return []

    filter_block = "\n    ".join(filters)

    query = f"""
PREFIX ppd: <http://landregistry.data.gov.uk/def/ppi/>
PREFIX lrcommon: <http://landregistry.data.gov.uk/def/common/>

SELECT ?paon ?saon ?street ?town ?postcode ?amount ?date ?type ?newBuild
WHERE {{
    ?txn ppd:pricePaid ?amount ;
         ppd:transactionDate ?date ;
         ppd:propertyAddress ?addr ;
         ppd:propertyType/skos:prefLabel ?type ;
         ppd:newBuild ?newBuild .

    ?addr lrcommon:paon ?paon ;
          lrcommon:street ?street ;
          lrcommon:town ?town ;
          lrcommon:postcode ?postcode .

    OPTIONAL {{ ?addr lrcommon:saon ?saon }}

    FILTER(?date >= "{min_date}"^^xsd:date)
    {filter_block}
}}
ORDER BY DESC(?date)
LIMIT {max_results}
"""

    try:
        resp = requests.get(
            "https://landregistry.data.gov.uk/app/root/qonsole/query",
            params={"query": query, "output": "json"},
            headers={"Accept": "application/sparql-results+json"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        # Fallback: try the simpler PPD API
        return _search_ppd_simple(postcode, town, max_results)

    results = []
    for row in data.get("results", {}).get("bindings", []):
        saon = row.get("saon", {}).get("value", "")
        paon = row.get("paon", {}).get("value", "")
        street = row.get("street", {}).get("value", "")
        town_val = row.get("town", {}).get("value", "")
        pc = row.get("postcode", {}).get("value", "")
        addr_parts = [p for p in [saon, paon, street, town_val, pc] if p]
        address = ", ".join(addr_parts)

        ptype = row.get("type", {}).get("value", "O")
        # Map full label back to code
        type_code = "O"
        for code, name in SoldPrice.TYPE_MAP.items():
            if name.lower() in ptype.lower():
                type_code = code
                break

        results.append(SoldPrice(
            address=address,
            price=int(float(row["amount"]["value"])),
            date=row["date"]["value"][:10],
            property_type=type_code,
            new_build=row.get("newBuild", {}).get("value", "false").lower() == "true",
            postcode=pc,
        ))

    return results


def _search_ppd_simple(
    postcode: Optional[str],
    town: Optional[str],
    max_results: int,
) -> list[SoldPrice]:
    """Fallback: use the simpler Price Paid Data linked data API."""
    params = {"_pageSize": str(max_results), "_sort": "-transactionDate"}
    if postcode:
        params["propertyAddress.postcode"] = postcode.strip().upper()
    if town:
        params["propertyAddress.town"] = town.strip().upper()

    try:
        resp = requests.get(PPD_API, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    results = []
    for item in data.get("result", {}).get("items", []):
        addr = item.get("propertyAddress", {})
        addr_parts = [
            addr.get("saon", ""),
            addr.get("paon", ""),
            addr.get("street", ""),
            addr.get("town", ""),
            addr.get("postcode", ""),
        ]
        address = ", ".join(p for p in addr_parts if p)

        ptype_raw = item.get("propertyType", "")
        type_code = "O"
        if isinstance(ptype_raw, dict):
            ptype_raw = ptype_raw.get("prefLabel", "O")
        for code, name in SoldPrice.TYPE_MAP.items():
            if name.lower() in str(ptype_raw).lower():
                type_code = code
                break

        results.append(SoldPrice(
            address=address,
            price=int(item.get("pricePaid", 0)),
            date=str(item.get("transactionDate", ""))[:10],
            property_type=type_code,
            new_build=item.get("newBuild", False),
            postcode=addr.get("postcode", ""),
        ))

    return results


def area_price_stats(postcode_prefix: str, min_date: str = "2023-01-01") -> dict:
    """Get summary statistics for an area based on sold prices."""
    sales = search_sold_prices(postcode=postcode_prefix, max_results=50, min_date=min_date)
    if not sales:
        return {"count": 0, "message": "No data found for this area"}

    prices = [s.price for s in sales]
    sorted_prices = sorted(prices)
    n = len(sorted_prices)

    return {
        "count": n,
        "min": sorted_prices[0],
        "max": sorted_prices[-1],
        "mean": sum(prices) // n,
        "median": sorted_prices[n // 2],
        "postcode_prefix": postcode_prefix,
        "date_range": f"{min_date} to present",
        "by_type": _group_by_type(sales),
    }


def _group_by_type(sales: list[SoldPrice]) -> dict:
    """Group sales by property type and compute averages."""
    groups: dict[str, list[int]] = {}
    for s in sales:
        groups.setdefault(s.type_name, []).append(s.price)

    return {
        ptype: {
            "count": len(prices),
            "avg": sum(prices) // len(prices),
            "min": min(prices),
            "max": max(prices),
        }
        for ptype, prices in groups.items()
    }
