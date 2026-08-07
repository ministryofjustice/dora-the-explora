"""Mean Time to Recovery: mean gap between a failed workflow run on main and the
next successful run of the same workflow."""

from collections import defaultdict
from datetime import datetime, timedelta

from github_api import get_workflow_runs
from metrics_common import (
    OWNER,
    configure_logger,
    get_access_token,
    load_team_config,
    parse_args,
)


def _parse_timestamp(run):
    return datetime.fromisoformat(run["created_at"].replace("Z", ""))


def compute_mean_time_to_recovery(runs, excluded_workflows):
    """Return (num_periods, mean_recovery) across all failure->recovery periods.

    Runs are sorted by creation time. For each workflow, the first failure opens
    a period which is closed by the next success of that same workflow. Failures
    with no subsequent success are discarded. ``mean_recovery`` is ``None`` when
    there are no completed periods.
    """
    sorted_runs = sorted(runs, key=_parse_timestamp)

    # Per workflow: the open failure timestamp (if any) and the closed periods.
    open_failure = {}
    recovery_times = defaultdict(list)

    for run in sorted_runs:
        if run["name"] in excluded_workflows:
            continue

        workflow_id = run["workflow_id"]
        timestamp = _parse_timestamp(run)

        if run["conclusion"] != "success":
            open_failure.setdefault(workflow_id, timestamp)
        elif workflow_id in open_failure:
            start = open_failure.pop(workflow_id)
            recovery_times[workflow_id].append(timestamp - start)

    all_periods = [period for periods in recovery_times.values() for period in periods]
    num_periods = len(all_periods)
    if num_periods == 0:
        return 0, None

    total_recovery_time = sum(all_periods, timedelta(0))
    return num_periods, total_recovery_time / num_periods


def main():
    args = parse_args()
    logger = configure_logger()
    access_token = get_access_token()
    config = load_team_config(args.filename)

    runs = []
    for repo in config.repos:
        params = {"branch": "main", "per_page": 100, "created": args.date_query}
        try:
            repo_run = get_workflow_runs(OWNER, repo, access_token, params)
            print(f"Retrieved {len(repo_run)} workflow runs for {OWNER}/{repo}")
            runs += repo_run
        except Exception as e:
            print(f"Error retrieving workflow runs: {e}")

    print(f"Retrieved {len(runs)} workflow runs in total")

    num_periods, mean_time_to_recovery = compute_mean_time_to_recovery(
        runs, config.excluded_workflows
    )
    print(f"Total Workflows: {num_periods}")

    if mean_time_to_recovery is not None:
        days = mean_time_to_recovery.days
        hours = mean_time_to_recovery.seconds // 3600
        minutes = (mean_time_to_recovery.seconds % 3600) // 60
        message = (
            f"Mean time to recovery for {args.team_name}: "
            f"{days} days, {hours} hours, {minutes} minutes"
        )
        print(f"\033[32m\033[1m{message}\033[0m")
        logger.info(f"\n{message}")
    else:
        message = (
            f"No failure/recovery periods found for {args.team_name} "
            f"in {args.date_query}."
        )
        print(message)
        logger.info(message)


if __name__ == "__main__":
    main()
