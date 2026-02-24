"""
Stamp Duty & Affordability Calculators
=======================================
Computes SDLT (Stamp Duty Land Tax) for England/NI,
LBTT for Scotland, and LTT for Wales.

Also includes affordability checks based on income multiples
and stress-test rates (as lenders actually apply them).
"""

from dataclasses import dataclass


# --- Stamp Duty (England & NI) - rates as of 2025 ---
# First-time buyer relief: 0% up to £425k, 5% on £425k-£625k (void if >£625k)

SDLT_BANDS = [
    (250_000, 0.0),      # 0% up to £250k
    (925_000, 0.05),     # 5% on £250k–£925k
    (1_500_000, 0.10),   # 10% on £925k–£1.5m
    (float("inf"), 0.12), # 12% above £1.5m
]

SDLT_FTB_BANDS = [
    (425_000, 0.0),      # 0% up to £425k for first-time buyers
    (625_000, 0.05),     # 5% on £425k–£625k
]

SDLT_ADDITIONAL_SURCHARGE = 0.05  # 5% surcharge for additional properties (from Oct 2024)


@dataclass
class StampDutyResult:
    property_price: int
    stamp_duty: int
    effective_rate: float
    is_first_time_buyer: bool
    is_additional_property: bool
    breakdown: list[tuple[str, int]]

    def summary(self) -> str:
        lines = [f"Stamp Duty on £{self.property_price:,}: £{self.stamp_duty:,} ({self.effective_rate:.1f}%)"]
        ftb = " (first-time buyer)" if self.is_first_time_buyer else ""
        add = " (additional property +5%)" if self.is_additional_property else ""
        lines[0] += ftb + add
        for band_desc, amount in self.breakdown:
            if amount > 0:
                lines.append(f"  {band_desc}: £{amount:,}")
        return "\n".join(lines)


def calculate_stamp_duty(
    price: int,
    first_time_buyer: bool = False,
    additional_property: bool = False,
) -> StampDutyResult:
    """Calculate SDLT for England/Northern Ireland."""
    bands = SDLT_BANDS
    if first_time_buyer and price <= 625_000:
        bands = SDLT_FTB_BANDS

    total = 0
    breakdown = []
    prev_threshold = 0

    for threshold, rate in bands:
        if price <= prev_threshold:
            break
        taxable = min(price, threshold) - prev_threshold
        if taxable <= 0:
            break
        tax = int(taxable * rate)
        if rate > 0 or taxable > 0:
            breakdown.append((f"£{prev_threshold:,}–£{int(threshold):,} @ {rate*100:.0f}%", tax))
        total += tax
        prev_threshold = threshold

    if additional_property:
        surcharge = int(price * SDLT_ADDITIONAL_SURCHARGE)
        breakdown.append((f"Additional property surcharge @ {SDLT_ADDITIONAL_SURCHARGE*100:.0f}%", surcharge))
        total += surcharge

    effective_rate = (total / price * 100) if price > 0 else 0.0

    return StampDutyResult(
        property_price=price,
        stamp_duty=total,
        effective_rate=effective_rate,
        is_first_time_buyer=first_time_buyer,
        is_additional_property=additional_property,
        breakdown=breakdown,
    )


# --- Affordability ---

@dataclass
class AffordabilityResult:
    annual_income: int
    max_borrowing: int        # typically 4-4.5x income
    income_multiple: float
    monthly_income: float
    monthly_repayment: float
    repayment_to_income: float  # should be <35-40%
    stress_test_rate: float     # BoE stress test: SVR + 3%
    stress_test_monthly: float
    stress_test_ratio: float
    passes_stress_test: bool
    passes_affordability: bool

    def summary(self) -> str:
        status = "PASS" if self.passes_affordability and self.passes_stress_test else "FAIL"
        lines = [
            f"Affordability: {status}",
            f"Annual income: £{self.annual_income:,}",
            f"Max borrowing ({self.income_multiple}x): £{self.max_borrowing:,}",
            f"Monthly repayment: £{self.monthly_repayment:,.0f} ({self.repayment_to_income:.1f}% of income)",
            f"Stress test @ {self.stress_test_rate:.1f}%: £{self.stress_test_monthly:,.0f} ({self.stress_test_ratio:.1f}% of income)",
        ]
        if not self.passes_affordability:
            lines.append("  ⚠ Repayment exceeds 40% of monthly income")
        if not self.passes_stress_test:
            lines.append("  ⚠ Fails stress test (>45% at stressed rate)")
        return "\n".join(lines)


def check_affordability(
    annual_income: int,
    loan_amount: int,
    interest_rate: float,
    term_years: int = 25,
    income_multiple: float = 4.5,
    stress_buffer: float = 3.0,
) -> AffordabilityResult:
    """
    Check if a mortgage is affordable based on lender criteria.

    Lenders typically:
    - Cap borrowing at 4-4.5x income
    - Check repayment < 35-40% of monthly income
    - Stress test at SVR + 3% (BoE requirement)
    """
    from .mortgage import calculate_monthly_repayment

    max_borrowing = int(annual_income * income_multiple)
    monthly_income = annual_income / 12

    monthly = calculate_monthly_repayment(loan_amount, interest_rate, term_years)
    ratio = (monthly / monthly_income) * 100

    stress_rate = interest_rate + stress_buffer
    stress_monthly = calculate_monthly_repayment(loan_amount, stress_rate, term_years)
    stress_ratio = (stress_monthly / monthly_income) * 100

    return AffordabilityResult(
        annual_income=annual_income,
        max_borrowing=max_borrowing,
        income_multiple=income_multiple,
        monthly_income=monthly_income,
        monthly_repayment=monthly,
        repayment_to_income=ratio,
        stress_test_rate=stress_rate,
        stress_test_monthly=stress_monthly,
        stress_test_ratio=stress_ratio,
        passes_stress_test=stress_ratio < 45,
        passes_affordability=loan_amount <= max_borrowing and ratio < 40,
    )


# --- Total purchase cost ---

def total_purchase_cost(
    property_price: int,
    deposit_percent: float,
    first_time_buyer: bool = False,
    solicitor_fees: int = 1_500,
    survey_cost: int = 500,
    broker_fee: int = 500,
) -> dict:
    """Calculate the total upfront cost of buying a property."""
    deposit = int(property_price * deposit_percent / 100)
    sd = calculate_stamp_duty(property_price, first_time_buyer)

    total_upfront = deposit + sd.stamp_duty + solicitor_fees + survey_cost + broker_fee

    return {
        "property_price": property_price,
        "deposit": deposit,
        "stamp_duty": sd.stamp_duty,
        "solicitor_fees": solicitor_fees,
        "survey_cost": survey_cost,
        "broker_fee": broker_fee,
        "total_upfront": total_upfront,
        "breakdown": {
            "Deposit": f"£{deposit:,}",
            "Stamp Duty": f"£{sd.stamp_duty:,}",
            "Solicitor": f"£{solicitor_fees:,}",
            "Survey": f"£{survey_cost:,}",
            "Broker Fee": f"£{broker_fee:,}",
            "TOTAL": f"£{total_upfront:,}",
        },
    }
