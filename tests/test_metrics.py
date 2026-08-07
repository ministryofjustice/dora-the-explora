"""Unit tests for the DORA metric computations.

These test the pure ``compute_*`` functions directly with in-memory fixtures, so
they run without network access or an ACCESS_TOKEN.
"""

from datetime import datetime, timedelta

from cfr import compute_change_failure_rate
from df import compute_deployment_frequency
from ltfc import compute_lead_time
from mttr import compute_mean_time_to_recovery


def run(name, conclusion, created_at, workflow_id=1):
    return {
        "name": name,
        "conclusion": conclusion,
        "created_at": created_at,
        "workflow_id": workflow_id,
    }


# --- Change Failure Rate ---------------------------------------------------


def test_cfr_empty_runs_returns_zero_not_crash():
    # Regression: previously raised ZeroDivisionError on an empty run list.
    total, unsuccessful, rate = compute_change_failure_rate([], [])
    assert (total, unsuccessful, rate) == (0, 0, 0.0)


def test_cfr_excludes_workflows_from_both_numerator_and_denominator():
    runs = [
        run("Deploy", "success", "2026-01-01T00:00:00Z"),
        run("Deploy", "failure", "2026-01-01T01:00:00Z"),
        run("Scorecards", "failure", "2026-01-01T02:00:00Z"),  # excluded
    ]
    total, unsuccessful, rate = compute_change_failure_rate(runs, ["Scorecards"])
    # Excluded run must not inflate the failure rate or the denominator.
    assert total == 2
    assert unsuccessful == 1
    assert rate == 50.0


# --- Deployment Frequency --------------------------------------------------


def test_df_same_day_runs_do_not_collapse_to_none():
    # Regression: .days truncation made same-day bursts report "does not deploy".
    runs = [
        run("Deploy", "success", "2026-01-01T00:00:00Z"),
        run("Deploy", "success", "2026-01-01T06:00:00Z"),
        run("Deploy", "success", "2026-01-01T12:00:00Z"),
    ]
    num, freq = compute_deployment_frequency(runs, [])
    assert num == 3
    assert freq == 3.0  # 3 runs over a floored 1-day span


def test_df_frequency_over_multiple_days():
    runs = [
        run("Deploy", "success", "2026-01-01T00:00:00Z"),
        run("Deploy", "success", "2026-01-03T00:00:00Z"),
    ]
    num, freq = compute_deployment_frequency(runs, [])
    assert num == 2
    assert freq == 1.0  # 2 runs over a 2-day span


def test_df_excluded_only_returns_none():
    runs = [run("Scorecards", "success", "2026-01-01T00:00:00Z")]
    num, freq = compute_deployment_frequency(runs, ["Scorecards"])
    assert num == 0
    assert freq is None


# --- Mean Time to Recovery -------------------------------------------------


def test_mttr_failure_then_success_period():
    runs = [
        run("Deploy", "failure", "2026-01-01T00:00:00Z", workflow_id=7),
        run("Deploy", "success", "2026-01-01T02:00:00Z", workflow_id=7),
    ]
    num, mean = compute_mean_time_to_recovery(runs, [])
    assert num == 1
    assert mean == timedelta(hours=2)


def test_mttr_unrecovered_failure_is_discarded():
    runs = [run("Deploy", "failure", "2026-01-01T00:00:00Z", workflow_id=7)]
    num, mean = compute_mean_time_to_recovery(runs, [])
    assert num == 0
    assert mean is None


def test_mttr_out_of_order_runs_are_sorted():
    # Success listed before its failure; sorting must pair them correctly.
    runs = [
        run("Deploy", "success", "2026-01-01T03:00:00Z", workflow_id=7),
        run("Deploy", "failure", "2026-01-01T01:00:00Z", workflow_id=7),
    ]
    num, mean = compute_mean_time_to_recovery(runs, [])
    assert num == 1
    assert mean == timedelta(hours=2)


# --- Lead Time for Change --------------------------------------------------


def pr(number, merged_at, url="https://api.github.com/pr"):
    return {"number": number, "merged_at": merged_at, "url": url}


def test_ltfc_lead_time_from_last_commit_to_merge():
    prs = [pr(1, "2026-01-05T12:00:00Z")]
    start = datetime(2026, 1, 1)
    end = datetime(2026, 1, 31)

    def last_commit(_pr):
        return datetime(2026, 1, 5, 10, 0, 0)  # 2 hours before merge

    num, mean = compute_lead_time(prs, start, end, last_commit)
    assert num == 1
    assert mean == timedelta(hours=2)


def test_ltfc_pr_outside_range_is_ignored():
    prs = [pr(1, "2026-02-05T12:00:00Z")]  # after the range
    start = datetime(2026, 1, 1)
    end = datetime(2026, 1, 31)
    num, mean = compute_lead_time(prs, start, end, lambda _pr: None)
    assert num == 0
    assert mean is None


def test_ltfc_missing_commit_time_falls_back_to_zero_lead_time():
    prs = [pr(1, "2026-01-05T12:00:00Z")]
    start = datetime(2026, 1, 1)
    end = datetime(2026, 1, 31)
    # get_last_commit_time returning None => lead time falls back to merge time.
    num, mean = compute_lead_time(prs, start, end, lambda _pr: None)
    assert num == 1
    assert mean == timedelta(0)
