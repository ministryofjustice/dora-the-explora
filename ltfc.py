"""Lead Time for Change: mean time between a PR's last commit and its merge."""

from datetime import datetime, timedelta

from github_api import get_merged_pull_requests, make_github_api_call
from metrics_common import (
    OWNER,
    configure_logger,
    get_access_token,
    load_team_config,
    parse_args,
)


def _parse_pr_timestamp(value):
    # GitHub timestamps end in 'Z'; strip it for datetime.fromisoformat on 3.9.
    return datetime.fromisoformat(value[:-1])


def compute_lead_time(prs, start_date, end_date, get_last_commit_time):
    """Return (num_prs, mean_lead_time) over PRs merged within [start, end].

    ``get_last_commit_time(pr)`` returns the datetime of the PR's final commit,
    or ``None`` if it could not be determined (in which case the PR contributes a
    zero lead time, matching the previous behaviour of falling back to the merge
    time). ``mean_lead_time`` is ``None`` when no PRs fall in range.
    """
    total_lead_time = timedelta()
    num_prs = 0
    for pr in prs:
        merged_at = _parse_pr_timestamp(pr["merged_at"])
        if not (start_date <= merged_at <= end_date):
            continue
        num_prs += 1
        commit_time = get_last_commit_time(pr) or merged_at
        total_lead_time += merged_at - commit_time

    if num_prs == 0:
        return 0, None
    return num_prs, total_lead_time / num_prs


def main():
    args = parse_args()
    logger = configure_logger()
    access_token = get_access_token()
    config = load_team_config(args.filename)

    def get_last_commit_time(pr):
        """Fetch the PR's commits and return the last commit's committer date."""
        try:
            commits = make_github_api_call(pr["url"] + "/commits", access_token)
        except Exception as e:
            print(f"Error retrieving commits: {e}")
            return None
        if not commits:
            return None
        last_commit = commits[-1]
        return _parse_pr_timestamp(last_commit["commit"]["committer"]["date"])

    team_lead_time = timedelta()
    team_merged_pull_requests = 0
    for repo in config.repos:
        params = {
            "state": "closed",
            "sort": "updated",
            "direction": "desc",
            "per_page": 100,
            "base": "main",
        }
        try:
            merged_pull_requests = get_merged_pull_requests(
                OWNER, repo, access_token, params
            )
        except Exception as e:
            print(f"Error retrieving pull requests: {e}")
            continue

        print(f"Found {len(merged_pull_requests)} merged pull requests.")

        num_prs, mean_lead_time = compute_lead_time(
            merged_pull_requests, args.start_date, args.end_date, get_last_commit_time
        )
        if mean_lead_time is not None:
            team_lead_time += mean_lead_time * num_prs
        team_merged_pull_requests += num_prs

    if team_merged_pull_requests > 0:
        mean_lead_time = team_lead_time / team_merged_pull_requests
        message = (
            f"Mean lead time for {args.team_name} team over "
            f"{team_merged_pull_requests} merged pull requests: "
            f"{mean_lead_time.days} days, "
            f"{mean_lead_time.seconds // 3600} hours, "
            f"{(mean_lead_time.seconds % 3600) // 60} minutes"
        )
        print(f"\033[32m\033[1m{message}\033[0m")
        logger.info(f"\n{message}")
    else:
        print("No merged pull requests found.")
        logger.info("No merged pull requests found.")


if __name__ == "__main__":
    main()
