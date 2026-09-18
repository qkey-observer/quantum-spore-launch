"""Cost is a first-class output, not a footnote.

Rates come from IBM's public pages. Dedicated / On-Prem is quote-only; this
module will not invent a number for it. Billed QPU seconds and wall-clock
seconds are stored separately: they differ by orders of magnitude.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from importlib import resources
from typing import Any
from urllib.request import Request, urlopen

from .errors import CostError

SNAPSHOT_RESOURCE = "ibm_rates.json"
PRODUCTS_URL = "https://www.ibm.com/quantum/products"
SECONDS_PER_MINUTE = 60.0
MINUTES_PER_DAY = 60 * 24
DAYS_PER_MONTH = 30
DAYS_PER_YEAR = 365
SECONDS_PER_MONTH = DAYS_PER_MONTH * 24 * 3600
SECONDS_PER_YEAR = DAYS_PER_YEAR * 24 * 3600


def load_snapshot() -> dict[str, Any]:
    text = (
        resources.files("quantum_launch")
        .joinpath("data")
        .joinpath(SNAPSHOT_RESOURCE)
        .read_text(encoding="utf-8")
    )
    return json.loads(text)


def usd_per_billed_second(usd_per_minute: float) -> float:
    return usd_per_minute / SECONDS_PER_MINUTE


def payg_billable_seconds(usage_seconds: float) -> float:
    """Pay-As-You-Go minimum purchase is 1 second, billed per second.

    Raw usage is still reported separately. This only affects the dollar line.
    """
    if usage_seconds <= 0:
        raise CostError("billed QPU time of zero is not a run that happened")
    return max(float(usage_seconds), 1.0)


def job_cost(usage_seconds: float, snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    snap = snapshot or load_snapshot()
    plans = snap["plans"]
    billable = payg_billable_seconds(usage_seconds)
    rows = []
    for key in ("open", "pay_as_you_go", "flex", "premium"):
        plan = plans[key]
        rate = plan.get("usdPerMinute")
        if rate is None:
            continue
        rows.append({
            "plan": plan["name"],
            "usdPerMinute": rate,
            "usd": round(billable * usd_per_billed_second(float(rate)), 6) if rate else 0.0,
            "note": plan.get("cap") or plan.get("minimumPurchase") or plan.get("billing"),
        })
    on_prem = plans["on_prem"]
    return {
        "usageSeconds": usage_seconds,
        "payAsYouGoBillableSeconds": billable,
        "retrievedAt": snap["retrievedAt"],
        "sourceUrl": snap["sourceUrl"],
        "byPlan": rows,
        "onPrem": {"name": on_prem["name"], "price": on_prem["price"]},
    }


def spore_unit_cost(usage_seconds: float, shots: int, snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    if shots < 1:
        raise CostError("shots must be >= 1")
    job = job_cost(usage_seconds, snapshot)
    payg = next(r for r in job["byPlan"] if r["plan"].startswith("Pay-As-You-Go"))
    return {
        **job,
        "shots": shots,
        "usdPerSporePayAsYouGo": round(payg["usd"] / shots, 8),
    }


def continuous_projection(
    usage_seconds: float,
    wall_seconds: float,
    shots: int,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Project continuous operation two ways, both labelled.

    1. Measured loop: jobs/hour from wall-clock (queue included), dollars from
       billed QPU seconds. This is what a shared-queue autonomous loop costs.
    2. 100% billed-QPU month at the public Pay-As-You-Go rate. IBM does not
       publish a dedicated-machine rate; this is the only per-second figure on
       the public page, applied to every second of a 30-day month. It is an
       upper bound using a published rate, not an IBM quote.
    """
    snap = snapshot or load_snapshot()
    if wall_seconds <= 0:
        raise CostError("wall-clock time of zero cannot be used to project a loop")
    payg_rate = float(snap["plans"]["pay_as_you_go"]["usdPerMinute"])
    flex_rate = float(snap["plans"]["flex"]["usdPerMinute"])
    premium_rate = float(snap["plans"]["premium"]["usdPerMinute"])
    per_sec = usd_per_billed_second(payg_rate)
    billable = payg_billable_seconds(usage_seconds)
    jobs_per_hour = 3600.0 / wall_seconds
    billed_seconds_per_hour = jobs_per_hour * billable
    usd_per_hour = billed_seconds_per_hour * per_sec
    usd_per_day = usd_per_hour * 24
    usd_per_month = usd_per_day * DAYS_PER_MONTH
    spores_per_hour = jobs_per_hour * shots
    full_month_seconds = float(SECONDS_PER_MONTH)
    full_year_seconds = float(SECONDS_PER_YEAR)
    payg_30d = round(full_month_seconds * usd_per_billed_second(payg_rate), 2)
    payg_365d = round(full_year_seconds * usd_per_billed_second(payg_rate), 2)
    premium_minutes_year = 5200
    return {
        "retrievedAt": snap["retrievedAt"],
        "sourceUrl": snap["sourceUrl"],
        "assumptions": {
            "usageSecondsPerJob": usage_seconds,
            "wallSecondsPerJob": wall_seconds,
            "shotsPerJob": shots,
            "monthDays": DAYS_PER_MONTH,
            "openPlanCap": snap["plans"]["open"]["cap"],
            "onPrem": snap["plans"]["on_prem"]["price"],
        },
        "measuredLoop": {
            "jobsPerHour": round(jobs_per_hour, 4),
            "sporesPerHour": round(spores_per_hour, 4),
            "billedSecondsPerHour": round(billed_seconds_per_hour, 4),
            "usdPerHourPayAsYouGo": round(usd_per_hour, 2),
            "usdPerDayPayAsYouGo": round(usd_per_day, 2),
            "usdPerMonthPayAsYouGo": round(usd_per_month, 2),
            "usdPerSporePayAsYouGo": round((billable * per_sec) / shots, 8),
            "note": (
                "LOWER BOUND on rate, not a guaranteed throughput. wallSeconds includes "
                "the shared IBM queue, which moves by orders of magnitude (this project "
                "has seen ibm_fez pending 98 and ibm_marrakesh pending 1 at the same "
                "moment). 14,400 jobs × $3.84 = $55,296 / 30 days only if wall stays "
                f"near {wall_seconds} s. A long queue does not raise billed QPU dollars "
                "per job; it collapses how many jobs fit in a month. Shared-queue "
                "autonomous cannot promise a cadence."
            ),
        },
        "reservedAccess": {
            "premiumPublishedFloorUsdPerYear": round(
                5200 * float(snap["plans"]["premium"]["usdPerMinute"]), 2
            ),
            "premiumMinutesPerYear": 5200,
            "premiumUsdPerMinute": float(snap["plans"]["premium"]["usdPerMinute"]),
            "onPrem": snap["plans"]["on_prem"]["price"],
            "dedicatedService": "Price requires quote (IBM Dedicated Service / On-Prem Plan)",
            "note": (
                "Premium is the published reserved-capacity product: 5200 minutes/year "
                "at $48/min = $249,600/year committed. That is still fleet time, not a "
                "machine you hold. Dedicated Service and On-Prem are the products that "
                "remove the shared queue; IBM lists them as quote-only and this program "
                "will not invent a number. The fundraise is for that quote, not for "
                "Pay-As-You-Go queue luck."
            ),
        },
        "keepConnected": {
            "point": (
                "The public claim needs the QPU in the loop for a long time: "
                "measure → launch → next job, hours and days of billed execution, "
                "not a 2-second demo. Open Plan (10 min/month) and Premium's "
                f"{premium_minutes_year} min/year ({premium_minutes_year / 60:.1f} h/year) "
                "are not long enough. Dedicated / On-Prem is the SKU that holds "
                "the machine; IBM lists it as quote-only."
            ),
            "openPlanMinutesPerMonth": 10,
            "premiumMinutesPerYear": premium_minutes_year,
            "premiumHoursPerYear": round(premium_minutes_year / 60, 1),
            "calendarHoursPerMonth": DAYS_PER_MONTH * 24,
            "calendarHoursPerYear": DAYS_PER_YEAR * 24,
        },
        "fullBilledMonthUpperBound": {
            "seconds": int(full_month_seconds),
            "usdPayAsYouGo": payg_30d,
            "usdPayAsYouGoYear": payg_365d,
            "usdFlexRate": round(full_month_seconds * usd_per_billed_second(flex_rate), 2),
            "usdPremiumRate": round(full_month_seconds * usd_per_billed_second(premium_rate), 2),
            "usdFlexRateYear": round(full_year_seconds * usd_per_billed_second(flex_rate), 2),
            "usdPremiumRateYear": round(full_year_seconds * usd_per_billed_second(premium_rate), 2),
            "note": (
                "HIGH numbers: public Pay-As-You-Go $96/min applied to every second "
                "of the calendar (30 days and 365 days). That is the cost of holding "
                "billed QPU time long enough for the claim. IBM Dedicated/On-Prem is "
                "quote-only. Flex/Premium list lower per-minute rates but are sold "
                f"with annual-minute floors ({snap['plans']['flex']['minimumPurchase']}, "
                f"{snap['plans']['premium']['minimumPurchase']}), not as 24/7 machines."
            ),
        },
        "openPlan": {
            "canRunContinuously": False,
            "cap": snap["plans"]["open"]["cap"],
            "note": "The Open Plan grant is ten minutes of billed QPU time per 28-day window. It cannot drive an unattended loop.",
        },
    }


def format_ledger(projection: dict[str, Any], job: dict[str, Any]) -> str:
    bound = projection["fullBilledMonthUpperBound"]
    keep = projection["keepConnected"]
    reserved = projection["reservedAccess"]
    loop = projection["measuredLoop"]
    lines = [
        "COST LEDGER  (write the HIGH numbers; a short job is not the product)",
        f"  rates retrieved  {job['retrievedAt']}  {job['sourceUrl']}",
        f"  {keep['point']}",
        "  KEEP THE QPU IN THE LOOP (public PAYG $96/min × calendar time, if billed every second):",
        f"    30 days     ${bound['usdPayAsYouGo']}",
        f"    365 days    ${bound['usdPayAsYouGoYear']}",
        f"    Flex rate 30d / 365d    ${bound['usdFlexRate']} / ${bound['usdFlexRateYear']}",
        f"    Premium rate 30d / 365d ${bound['usdPremiumRate']} / ${bound['usdPremiumRateYear']}",
        f"    Dedicated / On-Prem     {reserved['dedicatedService']}",
        f"  {bound['note']}",
        "  published minutes are NOT long enough for this claim:",
        f"    Open Plan     {keep['openPlanMinutesPerMonth']} min / month",
        f"    Premium floor {keep['premiumMinutesPerYear']} min / year  = {keep['premiumHoursPerYear']} h/year  (${reserved['premiumPublishedFloorUsdPerYear']}/year committed)",
        f"    calendar      {keep['calendarHoursPerMonth']} h / 30d,  {keep['calendarHoursPerYear']} h / year",
        f"    {reserved['note']}",
        f"  billed QPU this job  {job['usageSeconds']} s   (raw)   PAYG billable {job['payAsYouGoBillableSeconds']} s",
        "  this job at list rates:",
    ]
    for row in job["byPlan"]:
        lines.append(f"    {row['plan']:<22}  ${row['usd']:<12}  (${row['usdPerMinute']}/min)")
    lines.append(f"    {job['onPrem']['name']:<22}  {job['onPrem']['price']}")
    lines += [
        "  shared-queue loop if wall-clock stays short (LOWER BOUND, not the claim):",
        f"    per 30 days  ${loop['usdPerMonthPayAsYouGo']}   per spore ${loop['usdPerSporePayAsYouGo']}",
        f"    {loop['note']}",
        f"  Open Plan: {projection['openPlan']['note']}",
    ]
    return "\n".join(lines)


def try_fetch_live_rates(timeout_s: float = 8.0) -> dict[str, Any] | None:
    """Best-effort re-read of the public products page. Failure returns None."""
    try:
        req = Request(PRODUCTS_URL, headers={"User-Agent": "quantum-spore-launch/1.0"})
        with urlopen(req, timeout=timeout_s) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None
    minutes = {}
    for name, pat in (
        ("pay_as_you_go", r"\$96\s*USD\s*/\s*minute"),
        ("flex", r"\$72\s*USD\s*/\s*minute"),
        ("premium", r"\$48\s*USD\s*/\s*minute"),
    ):
        minutes[name] = bool(re.search(pat, html, re.I))
    return {
        "fetchedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "url": PRODUCTS_URL,
        "sawPayAsYouGo96": minutes["pay_as_you_go"],
        "sawFlex72": minutes["flex"],
        "sawPremium48": minutes["premium"],
    }
