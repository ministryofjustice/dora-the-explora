"""Change Failure Rate: percentage of workflow runs on main that did not succeed."""

from github_api import get_workflow_runs
from metrics_common import (
    OWNER,
    configure_logger,
    get_access_token,
    load_team_config,
    parse_args,
)


def compute_change_failure_rate(runs, excluded_workflows):
    """Return (total_runs, unsuccessful_runs, failure_rate_percent).

    Both the numerator and denominator ignore excluded workflows so the rate is
    computed over a single, consistent population. Returns a 0.0 rate when there
    are no counted runs rather than dividing by zero.
    """
    counted = [run for run in runs if run["name"] not in excluded_workflows]
    total_runs = len(counted)
    unsuccessful_runs = len(
        [run for run in counted if run["conclusion"] != "success"]
    )
    failure_rate = (unsuccessful_runs / total_runs) * 100 if total_runs else 0.0
    return total_runs, unsuccessful_runs, failure_rate


def main():
    args = parse_args()
    logger = configure_logger()
    access_token = get_access_token()
    config = load_team_config(args.filename)

    runs = []
    for repo in config.repos:
        params = {
            "branch": "main",
            "status": "completed",
            "per_page": 100,
            "created": args.date_query,
        }
        try:
            runs += get_workflow_runs(OWNER, repo, access_token, params)
        except Exception as e:
            print(f"Error retrieving workflow runs: {e}")

    total_runs, unsuccessful_runs, failure_rate = compute_change_failure_rate(
        runs, config.excluded_workflows
    )

    logger.info(f"Total Workflow Runs: {total_runs}")
    logger.info(f"Total Unsuccessful Runs: {unsuccessful_runs}")
    logger.info(f"\nChange Failure Rate for {args.team_name}: {failure_rate:.2f}%")

    print(f"Total Workflow Runs: {total_runs}")
    print(f"Total Unsuccessful Runs: {unsuccessful_runs}")
    print(
        f"\033[32m\033[1mChange Failure Rate for {args.team_name}: "
        f"{failure_rate:.2f}%\033[0m"
    )


if __name__ == "__main__":
    main()
