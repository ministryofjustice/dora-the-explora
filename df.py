"""Deployment Frequency: successful workflow runs on main per day over the range."""

from datetime import datetime

from github_api import get_workflow_runs
from metrics_common import (
    GITHUB_DATE_FORMAT,
    OWNER,
    configure_logger,
    get_access_token,
    load_team_config,
    parse_args,
)


def compute_deployment_frequency(runs, excluded_workflows):
    """Return (num_runs, deployments_per_day) for the counted successful runs.

    ``deployments_per_day`` is ``None`` when there are no counted runs. The span
    is measured from the earliest to the latest counted run (the caller passes
    already-successful runs), and is floored at one day so a burst of runs inside
    a single day does not collapse to a divide-by-zero.
    """
    counted = [run for run in runs if run["name"] not in excluded_workflows]
    num_runs = len(counted)
    if num_runs == 0:
        return 0, None

    run_dates = [
        datetime.strptime(run["created_at"], GITHUB_DATE_FORMAT) for run in counted
    ]
    span_days = (max(run_dates) - min(run_dates)).total_seconds() / 86400
    span_days = max(span_days, 1.0)  # avoid inflating frequency within a single day

    return num_runs, num_runs / span_days


def main():
    args = parse_args()
    logger = configure_logger()
    access_token = get_access_token()
    config = load_team_config(args.filename)

    runs = []
    for repo in config.repos:
        params = {
            "branch": "main",
            "status": "success",
            "per_page": 100,
            "created": args.date_query,
        }
        try:
            runs += get_workflow_runs(OWNER, repo, access_token, params)
        except Exception as e:
            print(f"Error retrieving workflow runs: {e}")

    num_runs, deployment_frequency = compute_deployment_frequency(
        runs, config.excluded_workflows
    )

    if deployment_frequency is not None:
        message = (
            f"Daily deployment frequency for {args.team_name}: "
            f"{deployment_frequency:.2f} deployments/day"
        )
        print(f"\033[1m\033[32m{message}\033[0m")
        logger.info(f"\n{message}")
    else:
        message = f"{args.team_name} does not use github actions for deployments"
        print(f"\033[1m\033[32m{message}\033[0m")
        logger.info(message)


if __name__ == "__main__":
    main()
