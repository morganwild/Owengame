"""
Mortgage Repayment Calculator
=============================
Calculates monthly/annual repayments for a property given:
  - Property price
  - Deposit percentage (adjustable slider)
  - Interest rate (fetched from Bank of England base rate + lender spread)
  - Mortgage term

Data sources:
  - Bank of England base rate: Free statistical API
    https://www.bankofengland.co.uk/boeapps/database/fromshowcolumns.asp?Travel=NIxAZxSUx&FromSeries=1&ToSeries=50&DAession=DA&Ession=ES&SeriesCodes=IUDBEDR&UsingCodes=Y&CSVF=TN&Ession=ES
  - Typical lender spreads are hardcoded but adjustable
"""

from dataclasses import dataclass
from typing import Optional

import requests


BOE_BASE_RATE_URL = (
    "https://www.bankofengland.co.uk/boeapps/database/fromshowcolumns.asp"
    "?Travel=NIxAZxSUx&FromSeries=1&ToSeries=50&DAT=RNG"
    "&VFD=2024-01-01&VTD=2026-12-31"
    "&SeriesCodes=IUDBEDR&UsingCodes=Y&CSVF=TN"
)

# Typical lender spreads above base rate (percentage points)
LENDER_SPREADS = {
    "best_fixed_2yr": 0.75,   # competitive 2-year fix
    "average_fixed_2yr": 1.25,
    "best_fixed_5yr": 0.90,
    "average_fixed_5yr": 1.40,
    "standard_variable": 2.25,
    "tracker": 0.50,          # base + 0.5%
}

# LTV tiers — lenders charge more for higher LTV
LTV_PREMIUM = {
    60: 0.0,    # 40%+ deposit — best rates
    75: 0.10,
    80: 0.20,
    85: 0.40,
    90: 0.65,
    95: 1.00,   # 5% deposit — highest premium
}


def get_boe_base_rate() -> Optional[float]:
    """Fetch the latest Bank of England base rate from their statistical API."""
    try:
        resp = requests.get(BOE_BASE_RATE_URL, timeout=10)
        resp.raise_for_status()
        # CSV format: Date, Value
        lines = resp.text.strip().split("\n")
        # Find last non-empty data line
        for line in reversed(lines):
            parts = line.strip().split(",")
            if len(parts) >= 2:
                try:
                    return float(parts[1].strip())
                except ValueError:
                    continue
        return None
    except Exception:
        return None


def get_ltv_premium(ltv_percent: float) -> float:
    """Get the additional rate premium based on loan-to-value ratio."""
    for threshold in sorted(LTV_PREMIUM.keys()):
        if ltv_percent <= threshold:
            return LTV_PREMIUM[threshold]
    return LTV_PREMIUM[95]


@dataclass
class MortgageResult:
    property_price: int
    deposit_amount: int
    deposit_percent: float
    loan_amount: int
    interest_rate: float       # annual %
    base_rate: float
    lender_spread: float
    ltv_premium: float
    term_years: int
    monthly_repayment: float
    total_repayment: float
    total_interest: float
    rate_type: str

    def summary(self) -> str:
        return (
            f"Property: £{self.property_price:,}\n"
            f"Deposit: £{self.deposit_amount:,} ({self.deposit_percent:.1f}%)\n"
            f"Loan: £{self.loan_amount:,} (LTV {100 - self.deposit_percent:.1f}%)\n"
            f"Rate: {self.interest_rate:.2f}% ({self.rate_type}) "
            f"[base {self.base_rate:.2f}% + spread {self.lender_spread:.2f}% + LTV premium {self.ltv_premium:.2f}%]\n"
            f"Term: {self.term_years} years\n"
            f"Monthly: £{self.monthly_repayment:,.2f}\n"
            f"Total repaid: £{self.total_repayment:,.2f}\n"
            f"Total interest: £{self.total_interest:,.2f}"
        )


def calculate_monthly_repayment(loan: float, annual_rate_pct: float, term_years: int) -> float:
    """Standard annuity formula for monthly repayment."""
    if annual_rate_pct == 0:
        return loan / (term_years * 12)
    monthly_rate = (annual_rate_pct / 100) / 12
    n_payments = term_years * 12
    return loan * (monthly_rate * (1 + monthly_rate) ** n_payments) / (
        (1 + monthly_rate) ** n_payments - 1
    )


def calculate_mortgage(
    property_price: int,
    deposit_percent: float = 10.0,
    term_years: int = 25,
    rate_type: str = "average_fixed_2yr",
    base_rate_override: Optional[float] = None,
) -> MortgageResult:
    """
    Calculate mortgage repayments for a property.

    Args:
        property_price: Full property price in GBP
        deposit_percent: Deposit as percentage of property price (5-100)
        term_years: Mortgage term in years
        rate_type: Key from LENDER_SPREADS dict
        base_rate_override: Manually set base rate instead of fetching from BoE
    """
    deposit_percent = max(5.0, min(100.0, deposit_percent))

    deposit_amount = int(property_price * deposit_percent / 100)
    loan_amount = property_price - deposit_amount
    ltv = 100 - deposit_percent

    # Get base rate
    if base_rate_override is not None:
        base_rate = base_rate_override
    else:
        base_rate = get_boe_base_rate()
        if base_rate is None:
            base_rate = 4.50  # sensible fallback

    spread = LENDER_SPREADS.get(rate_type, LENDER_SPREADS["average_fixed_2yr"])
    ltv_prem = get_ltv_premium(ltv)
    interest_rate = base_rate + spread + ltv_prem

    monthly = calculate_monthly_repayment(loan_amount, interest_rate, term_years)
    total = monthly * term_years * 12

    return MortgageResult(
        property_price=property_price,
        deposit_amount=deposit_amount,
        deposit_percent=deposit_percent,
        loan_amount=loan_amount,
        interest_rate=interest_rate,
        base_rate=base_rate,
        lender_spread=spread,
        ltv_premium=ltv_prem,
        term_years=term_years,
        monthly_repayment=monthly,
        total_repayment=total,
        total_interest=total - loan_amount,
        rate_type=rate_type,
    )


def deposit_comparison(property_price: int, term_years: int = 25, rate_type: str = "average_fixed_2yr") -> list[MortgageResult]:
    """Compare repayments across different deposit percentages."""
    return [
        calculate_mortgage(property_price, dep, term_years, rate_type)
        for dep in [5, 10, 15, 20, 25, 30, 40, 50]
    ]
