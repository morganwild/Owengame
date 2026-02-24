#!/usr/bin/env python3
"""
House Buyer Tool — Interactive CLI
===================================
Run: python -m house_buyer.main

Features:
  1. Property search via Rightmove RSS feeds
  2. Mortgage repayment calculator with live BoE base rate
  3. Deposit comparison table (see how deposit % affects repayments)
  4. Stamp duty calculator
  5. Affordability checker (income-based, with lender stress test)
  6. Land Registry area price lookup
  7. Full purchase cost breakdown
  8. Analyse a specific property (all-in-one)
  9. Job market search (Adzuna / Reed live feeds)
"""

import sys
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt, FloatPrompt, Confirm

from .mortgage import (
    calculate_mortgage,
    deposit_comparison,
    get_boe_base_rate,
    LENDER_SPREADS,
)
from .property_search import (
    SearchCriteria,
    search_properties,
    fetch_rightmove_rss,
    create_manual_property,
)
from .stamp_duty import (
    calculate_stamp_duty,
    check_affordability,
    total_purchase_cost,
)
from .land_registry import search_sold_prices, area_price_stats
from .job_search import (
    search_jobs,
    area_job_stats,
    JobSearchCriteria,
    ADZUNA_CATEGORIES,
    _sources_configured,
)

console = Console()


def show_menu():
    console.print(Panel.fit(
        "[bold cyan]House Buyer Tool[/bold cyan]\n\n"
        "  [1] Search properties (Rightmove RSS)\n"
        "  [2] Mortgage repayment calculator\n"
        "  [3] Deposit comparison table\n"
        "  [4] Stamp duty calculator\n"
        "  [5] Affordability checker\n"
        "  [6] Area sold prices (Land Registry)\n"
        "  [7] Full purchase cost breakdown\n"
        "  [8] Analyse a specific property (all-in-one)\n"
        "  [9] Job market search (live feeds)\n"
        "  [q] Quit",
        title="Main Menu",
    ))
    return Prompt.ask("Choose an option", choices=["1", "2", "3", "4", "5", "6", "7", "8", "9", "q"])


def option_search_properties():
    console.print("\n[bold]Property Search via Rightmove RSS[/bold]")
    console.print(
        "To get an RSS URL:\n"
        "  1. Search on rightmove.co.uk with your criteria\n"
        "  2. Copy the URL\n"
        "  3. Replace '/property-for-sale/find.html' with '/rss.jsp'\n"
        "  Example: https://www.rightmove.co.uk/rss.jsp?locationIdentifier=REGION%5E...\n"
    )
    rss_url = Prompt.ask("Paste Rightmove RSS URL (or 'skip' to enter manually)")

    if rss_url.lower() == "skip":
        console.print("[yellow]Manual property entry — enter details for analysis[/yellow]")
        return

    # Optional local filters on top of RSS
    criteria = SearchCriteria()
    if Confirm.ask("Apply additional filters?", default=False):
        min_p = Prompt.ask("Min price (or blank)", default="")
        if min_p:
            criteria.min_price = int(min_p)
        max_p = Prompt.ask("Max price (or blank)", default="")
        if max_p:
            criteria.max_price = int(max_p)
        min_b = Prompt.ask("Min bedrooms (or blank)", default="")
        if min_b:
            criteria.min_bedrooms = int(min_b)
        kw = Prompt.ask("Must-have keywords (comma-sep, or blank)", default="")
        if kw:
            criteria.keywords = [k.strip() for k in kw.split(",")]
        excl = Prompt.ask("Exclude keywords (comma-sep, or blank)", default="")
        if excl:
            criteria.exclude_keywords = [k.strip() for k in excl.split(",")]

    console.print("\n[cyan]Fetching properties...[/cyan]")
    try:
        if criteria.min_price or criteria.max_price or criteria.min_bedrooms or criteria.keywords or criteria.exclude_keywords:
            props = search_properties(rss_url, criteria)
        else:
            props = fetch_rightmove_rss(rss_url)
    except Exception as e:
        console.print(f"[red]Error fetching RSS: {e}[/red]")
        return

    if not props:
        console.print("[yellow]No properties found matching your criteria.[/yellow]")
        return

    table = Table(title=f"Found {len(props)} properties")
    table.add_column("#", style="dim")
    table.add_column("Beds", justify="center")
    table.add_column("Price", justify="right", style="green")
    table.add_column("Type")
    table.add_column("Address", max_width=50)

    for i, p in enumerate(props, 1):
        price_str = f"£{p.price:,}" if p.price else "POA"
        table.add_row(
            str(i),
            str(p.bedrooms or "?"),
            price_str,
            p.property_type or "—",
            p.address[:50],
        )

    console.print(table)

    # Offer to analyse a property
    if Confirm.ask("\nAnalyse a property from the list?", default=True):
        idx = IntPrompt.ask("Property number") - 1
        if 0 <= idx < len(props):
            _analyse_property(props[idx].price or 0, props[idx].address)


def option_mortgage_calculator():
    console.print("\n[bold]Mortgage Repayment Calculator[/bold]")

    # Fetch base rate
    console.print("[dim]Fetching Bank of England base rate...[/dim]")
    base_rate = get_boe_base_rate()
    if base_rate:
        console.print(f"[green]Current BoE base rate: {base_rate}%[/green]")
    else:
        console.print("[yellow]Could not fetch BoE rate, using 4.50% as fallback[/yellow]")
        base_rate = 4.50

    price = IntPrompt.ask("Property price (£)")
    deposit_pct = FloatPrompt.ask("Deposit percentage", default=10.0)
    term = IntPrompt.ask("Mortgage term (years)", default=25)

    console.print("\nRate types: " + ", ".join(LENDER_SPREADS.keys()))
    rate_type = Prompt.ask("Rate type", default="average_fixed_2yr")

    result = calculate_mortgage(price, deposit_pct, term, rate_type, base_rate)
    console.print(Panel(result.summary(), title="Mortgage Summary", border_style="green"))


def option_deposit_comparison():
    console.print("\n[bold]Deposit Comparison Table[/bold]")
    price = IntPrompt.ask("Property price (£)")
    term = IntPrompt.ask("Mortgage term (years)", default=25)

    results = deposit_comparison(price, term)

    table = Table(title=f"Deposit comparison for £{price:,} over {term} years")
    table.add_column("Deposit %", justify="center")
    table.add_column("Deposit £", justify="right", style="green")
    table.add_column("Loan £", justify="right")
    table.add_column("Rate %", justify="center")
    table.add_column("Monthly £", justify="right", style="bold")
    table.add_column("Total Interest £", justify="right", style="red")

    for r in results:
        table.add_row(
            f"{r.deposit_percent:.0f}%",
            f"£{r.deposit_amount:,}",
            f"£{r.loan_amount:,}",
            f"{r.interest_rate:.2f}%",
            f"£{r.monthly_repayment:,.0f}",
            f"£{r.total_interest:,.0f}",
        )

    console.print(table)


def option_stamp_duty():
    console.print("\n[bold]Stamp Duty Calculator[/bold]")
    price = IntPrompt.ask("Property price (£)")
    ftb = Confirm.ask("First-time buyer?", default=False)
    additional = Confirm.ask("Additional property (2nd home/BTL)?", default=False)

    result = calculate_stamp_duty(price, ftb, additional)
    console.print(Panel(result.summary(), title="Stamp Duty", border_style="yellow"))


def option_affordability():
    console.print("\n[bold]Affordability Checker[/bold]")
    income = IntPrompt.ask("Combined annual income (£)")
    loan = IntPrompt.ask("Desired loan amount (£)")
    rate = FloatPrompt.ask("Expected interest rate (%)", default=5.5)
    term = IntPrompt.ask("Mortgage term (years)", default=25)

    result = check_affordability(income, loan, rate, term)
    style = "green" if result.passes_affordability and result.passes_stress_test else "red"
    console.print(Panel(result.summary(), title="Affordability", border_style=style))


def option_area_prices():
    console.print("\n[bold]Area Sold Prices (Land Registry)[/bold]")
    console.print("Enter a postcode prefix (e.g. 'BS1', 'SW1A') or town name")

    postcode = Prompt.ask("Postcode prefix (or blank)", default="")
    town = Prompt.ask("Town name (or blank)", default="")
    min_date = Prompt.ask("Earliest date", default="2023-01-01")

    if not postcode and not town:
        console.print("[red]Need at least a postcode or town[/red]")
        return

    console.print("[cyan]Querying Land Registry...[/cyan]")
    stats = area_price_stats(postcode or None, min_date)

    if stats.get("count", 0) == 0:
        console.print("[yellow]No data found. Try a different postcode or town.[/yellow]")
        # Also try by town if postcode failed
        if postcode and not town:
            console.print("[dim]Tip: try searching by town name instead[/dim]")
        return

    console.print(Panel(
        f"Area: {postcode or town}\n"
        f"Sales found: {stats['count']}\n"
        f"Price range: £{stats['min']:,} — £{stats['max']:,}\n"
        f"Average: £{stats['mean']:,}\n"
        f"Median: £{stats['median']:,}\n"
        f"Period: {stats['date_range']}",
        title="Area Price Summary",
        border_style="cyan",
    ))

    if stats.get("by_type"):
        table = Table(title="By Property Type")
        table.add_column("Type")
        table.add_column("Count", justify="center")
        table.add_column("Avg Price", justify="right", style="green")
        table.add_column("Range", justify="right")

        for ptype, data in stats["by_type"].items():
            table.add_row(
                ptype,
                str(data["count"]),
                f"£{data['avg']:,}",
                f"£{data['min']:,} — £{data['max']:,}",
            )
        console.print(table)


def option_purchase_cost():
    console.print("\n[bold]Full Purchase Cost Breakdown[/bold]")
    price = IntPrompt.ask("Property price (£)")
    deposit_pct = FloatPrompt.ask("Deposit percentage", default=10.0)
    ftb = Confirm.ask("First-time buyer?", default=False)
    solicitor = IntPrompt.ask("Solicitor/conveyancer fees (£)", default=1500)
    survey = IntPrompt.ask("Survey cost (£)", default=500)
    broker = IntPrompt.ask("Broker fee (£)", default=500)

    costs = total_purchase_cost(price, deposit_pct, ftb, solicitor, survey, broker)

    table = Table(title="Upfront Costs")
    table.add_column("Item")
    table.add_column("Cost", justify="right", style="green")

    for item, amount in costs["breakdown"].items():
        style = "bold green" if item == "TOTAL" else ""
        table.add_row(item, amount, style=style)

    console.print(table)


def _analyse_property(price: int, address: str = ""):
    """Run all analyses on a single property."""
    if not price:
        price = IntPrompt.ask("Property price (£)")
    if not address:
        address = Prompt.ask("Address", default="Unknown")

    console.print(f"\n[bold cyan]Full Analysis: {address}[/bold cyan]")
    console.print(f"[bold]Price: £{price:,}[/bold]\n")

    deposit_pct = FloatPrompt.ask("Your deposit %", default=10.0)
    income = IntPrompt.ask("Combined annual income (£)", default=50000)
    ftb = Confirm.ask("First-time buyer?", default=False)
    term = IntPrompt.ask("Mortgage term (years)", default=25)

    # Mortgage
    mortgage = calculate_mortgage(price, deposit_pct, term)
    console.print(Panel(mortgage.summary(), title="Mortgage", border_style="green"))

    # Stamp duty
    sd = calculate_stamp_duty(price, ftb)
    console.print(Panel(sd.summary(), title="Stamp Duty", border_style="yellow"))

    # Affordability
    afford = check_affordability(income, mortgage.loan_amount, mortgage.interest_rate, term)
    style = "green" if afford.passes_affordability and afford.passes_stress_test else "red"
    console.print(Panel(afford.summary(), title="Affordability", border_style=style))

    # Total upfront
    costs = total_purchase_cost(price, deposit_pct, ftb)
    table = Table(title="Total Upfront Costs")
    table.add_column("Item")
    table.add_column("Cost", justify="right", style="green")
    for item, amount in costs["breakdown"].items():
        table.add_row(item, amount, style="bold green" if item == "TOTAL" else "")
    console.print(table)

    # Deposit comparison
    console.print()
    option_deposit_comparison_for(price, term)


def option_deposit_comparison_for(price: int, term: int):
    """Mini deposit comparison embedded in property analysis."""
    results = deposit_comparison(price, term)

    table = Table(title="How deposit % affects your repayments")
    table.add_column("Deposit %", justify="center")
    table.add_column("Deposit £", justify="right")
    table.add_column("Monthly £", justify="right", style="bold")
    table.add_column("Rate %", justify="center")
    table.add_column("Total Interest £", justify="right", style="red")

    for r in results:
        table.add_row(
            f"{r.deposit_percent:.0f}%",
            f"£{r.deposit_amount:,}",
            f"£{r.monthly_repayment:,.0f}",
            f"{r.interest_rate:.2f}%",
            f"£{r.total_interest:,.0f}",
        )
    console.print(table)


def option_job_search():
    console.print("\n[bold]Job Market Search (Live Feeds)[/bold]")

    # Check configured sources
    sources = _sources_configured()
    if sources["adzuna"]:
        console.print("[green]Adzuna API: configured[/green]")
    else:
        console.print("[yellow]Adzuna API: not configured (set ADZUNA_APP_ID & ADZUNA_APP_KEY)[/yellow]")
    if sources["reed"]:
        console.print("[green]Reed API: configured[/green]")
    else:
        console.print("[yellow]Reed API: not configured (set REED_API_KEY)[/yellow]")

    if not sources["adzuna"] and not sources["reed"]:
        console.print(
            "\n[red]No job portal API keys configured.[/red]\n"
            "[dim]Get free keys:\n"
            "  Adzuna: https://developer.adzuna.com  (set ADZUNA_APP_ID & ADZUNA_APP_KEY)\n"
            "  Reed:   https://www.reed.co.uk/developers  (set REED_API_KEY)[/dim]"
        )
        return

    console.print()
    mode = Prompt.ask(
        "Search mode",
        choices=["search", "stats"],
        default="search",
    )

    if mode == "stats":
        _job_area_stats()
    else:
        _job_search_interactive()


def _job_search_interactive():
    location = Prompt.ask("Location (town/city/postcode)", default="London")
    keywords = Prompt.ask("Keywords (e.g. 'software engineer', or blank)", default="")
    min_sal = Prompt.ask("Min salary (or blank)", default="")
    max_sal = Prompt.ask("Max salary (or blank)", default="")
    contract = Prompt.ask("Contract type (permanent/contract/temp or blank)", default="")

    criteria = JobSearchCriteria(
        keywords=keywords,
        location=location,
        min_salary=int(min_sal) if min_sal else None,
        max_salary=int(max_sal) if max_sal else None,
        contract_type=contract,
        max_results=20,
    )

    console.print("\n[cyan]Searching job portals...[/cyan]")
    jobs = search_jobs(criteria)

    if not jobs:
        console.print("[yellow]No jobs found. Try broadening your search.[/yellow]")
        return

    table = Table(title=f"Found {len(jobs)} jobs near {location}")
    table.add_column("#", style="dim")
    table.add_column("Title", max_width=35)
    table.add_column("Company", max_width=20)
    table.add_column("Salary", justify="right", style="green")
    table.add_column("Type")
    table.add_column("Source", style="dim")

    for i, j in enumerate(jobs, 1):
        table.add_row(
            str(i),
            j.title[:35],
            j.company[:20],
            j.salary_display,
            j.contract_type or "—",
            j.source,
        )

    console.print(table)

    # Show URL for a selected job
    if Confirm.ask("\nView a job URL?", default=False):
        idx = IntPrompt.ask("Job number") - 1
        if 0 <= idx < len(jobs):
            console.print(f"\n[bold]{jobs[idx].title}[/bold] @ {jobs[idx].company}")
            console.print(f"[cyan]{jobs[idx].url}[/cyan]")
            if jobs[idx].description:
                console.print(f"\n{jobs[idx].description[:300]}...")


def _job_area_stats():
    location = Prompt.ask("Location (town/city)", default="London")

    console.print(f"\n[cyan]Fetching job market data for {location}...[/cyan]")
    stats = area_job_stats(location)

    if stats.get("count", 0) == 0:
        console.print("[yellow]No data found. Check your API keys or try a different location.[/yellow]")
        return

    # Summary panel
    sal = stats.get("salary", {})
    sal_text = ""
    if sal:
        sal_text = (
            f"\nSalary data ({sal['count_with_salary']} jobs with salary):\n"
            f"  Range: £{sal['min']:,} — £{sal['max']:,}\n"
            f"  Average: £{sal['mean']:,}\n"
            f"  Median: £{sal['median']:,}"
        )

    console.print(Panel(
        f"Location: {location}\n"
        f"Jobs found: {stats['count']}"
        f"{sal_text}",
        title="Job Market Summary",
        border_style="cyan",
    ))

    # Category breakdown
    if stats.get("by_category"):
        table = Table(title="By Category")
        table.add_column("Category", max_width=30)
        table.add_column("Jobs", justify="center")
        table.add_column("Avg Salary", justify="right", style="green")

        for cat, data in stats["by_category"].items():
            avg = f"£{data['avg_salary']:,}" if data.get("avg_salary") else "—"
            table.add_row(cat[:30], str(data["count"]), avg)
        console.print(table)

    # Top employers
    if stats.get("top_employers"):
        table = Table(title="Top Employers Hiring")
        table.add_column("Employer", max_width=35)
        table.add_column("Openings", justify="center")

        for emp in stats["top_employers"][:10]:
            table.add_row(emp["name"][:35], str(emp["openings"]))
        console.print(table)

    # Contract type split
    if stats.get("by_contract"):
        table = Table(title="By Contract Type")
        table.add_column("Type")
        table.add_column("Count", justify="center")
        for ct, count in stats["by_contract"].items():
            table.add_row(ct, str(count))
        console.print(table)


def option_analyse_property():
    _analyse_property(0)


def main():
    console.print("[bold cyan]House Buyer Tool v1.0[/bold cyan]")
    console.print("[dim]Live data: BoE base rate, Land Registry, Rightmove RSS, Adzuna/Reed jobs[/dim]\n")

    while True:
        try:
            choice = show_menu()

            actions = {
                "1": option_search_properties,
                "2": option_mortgage_calculator,
                "3": option_deposit_comparison,
                "4": option_stamp_duty,
                "5": option_affordability,
                "6": option_area_prices,
                "7": option_purchase_cost,
                "8": option_analyse_property,
                "9": option_job_search,
            }

            if choice == "q":
                console.print("[dim]Goodbye![/dim]")
                break

            if choice in actions:
                actions[choice]()
                console.print()
        except KeyboardInterrupt:
            console.print("\n[dim]Goodbye![/dim]")
            break
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


if __name__ == "__main__":
    main()
