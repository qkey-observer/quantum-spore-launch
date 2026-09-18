from quantum_launch.cost import (
    DAYS_PER_MONTH,
    DAYS_PER_YEAR,
    SECONDS_PER_MONTH,
    SECONDS_PER_YEAR,
    continuous_projection,
    format_ledger,
    job_cost,
    load_snapshot,
    payg_billable_seconds,
    spore_unit_cost,
    usd_per_billed_second,
)
from quantum_launch.errors import CostError
import pytest


def test_snapshot_rates_are_the_public_figures() -> None:
    snap = load_snapshot()
    assert snap["sourceUrl"] == "https://www.ibm.com/quantum/products"
    assert snap["plans"]["pay_as_you_go"]["usdPerMinute"] == 96
    assert snap["plans"]["flex"]["usdPerMinute"] == 72
    assert snap["plans"]["premium"]["usdPerMinute"] == 48
    assert snap["plans"]["open"]["usdPerMinute"] == 0
    assert snap["plans"]["on_prem"]["usdPerMinute"] is None
    assert "quote" in snap["plans"]["on_prem"]["price"].lower()


def test_zero_usage_is_not_a_run() -> None:
    with pytest.raises(CostError):
        payg_billable_seconds(0)


def test_payg_minimum_purchase_is_one_second() -> None:
    assert payg_billable_seconds(0.2) == 1.0
    assert payg_billable_seconds(2.4) == 2.4


def test_job_cost_at_payg() -> None:
    line = job_cost(2.4)
    payg = next(r for r in line["byPlan"] if r["plan"].startswith("Pay-As-You-Go"))
    assert payg["usd"] == round(2.4 * (96 / 60), 6)
    unit = spore_unit_cost(2.4, 4)
    assert unit["usdPerSporePayAsYouGo"] == round(payg["usd"] / 4, 8)


def test_full_billed_month_is_arithmetic_over_the_public_rate() -> None:
    proj = continuous_projection(2.4, 180.0, 4)
    assert DAYS_PER_MONTH == 30
    assert SECONDS_PER_MONTH == 30 * 24 * 3600
    assert proj["fullBilledMonthUpperBound"]["usdPayAsYouGo"] == round(
        SECONDS_PER_MONTH * usd_per_billed_second(96), 2
    )
    assert proj["fullBilledMonthUpperBound"]["usdPayAsYouGo"] == 4147200.0
    assert DAYS_PER_YEAR == 365
    assert SECONDS_PER_YEAR == 365 * 24 * 3600
    assert proj["fullBilledMonthUpperBound"]["usdPayAsYouGoYear"] == 50457600.0
    assert proj["keepConnected"]["premiumHoursPerYear"] == 86.7
    assert proj["keepConnected"]["openPlanMinutesPerMonth"] == 10
    text = format_ledger(proj, job_cost(2.4))
    assert "KEEP THE QPU" in text
    assert "$4147200.0" in text
    assert "$50457600.0" in text
    assert text.index("KEEP THE QPU") < text.index("LOWER BOUND")
    assert proj["openPlan"]["canRunContinuously"] is False
    loop = proj["measuredLoop"]
    # 3600/180 = 20 jobs/hour * 2.4 billed s * $1.60/s = $76.80/hour
    assert loop["jobsPerHour"] == 20.0
    assert loop["usdPerHourPayAsYouGo"] == 76.8
    assert loop["usdPerMonthPayAsYouGo"] == round(76.8 * 24 * 30, 2)
    assert loop["usdPerMonthPayAsYouGo"] == 55296.0
    assert "LOWER BOUND" in loop["note"]
    assert "ibm_fez" in loop["note"] and "ibm_marrakesh" in loop["note"]
    reserved = proj["reservedAccess"]
    assert reserved["premiumPublishedFloorUsdPerYear"] == 249600.0
    assert "quote" in reserved["dedicatedService"].lower()
    assert "will not invent" in reserved["note"]
