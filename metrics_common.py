"""Shared helpers for the DORA metric scripts (cfr / df / ltfc / mttr).

Each metric script repeats the same setup: read the access token, parse the
command-line arguments, load the team's repo list, and configure logging. Those
are collected here so the metric scripts can stay focused on computing and
reporting a single metric.
"""

import argparse
import json
import logging
import os
from collections import namedtuple
from datetime import datetime

OWNER = "ministryofjustice"

# Format GitHub uses for workflow-run / commit timestamps, e.g. 2023-04-01T00:00:00Z
GITHUB_DATE_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

# Parsed command-line arguments plus the values derived from them.
Args = namedtuple(
    "Args",
    ["filename", "team_name", "date_query", "start_date", "end_date"],
)

# A team's configuration loaded from its JSON manifest.
TeamConfig = namedtuple("TeamConfig", ["repos", "excluded_workflows"])


def get_access_token():
    """Return the GitHub token from ACCESS_TOKEN, with a clear error if unset."""
    try:
        return os.environ["ACCESS_TOKEN"]
    except KeyError:
        raise SystemExit(
            "ACCESS_TOKEN environment variable is not set. Set it to a GitHub "
            "personal access token with permission to read Actions workflow runs."
        ) from None


def parse_args():
    """Parse the shared (filename, date_query) command-line arguments.

    Returns an ``Args`` tuple where ``team_name`` is the manifest filename
    without its extension, and ``start_date`` / ``end_date`` are parsed from the
    ``2023-04-01..2023-05-01`` date range.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("filename", help="path to the input JSON file")
    parser.add_argument(
        "date_query", help="date range in the format 2023-04-01..2023-05-01"
    )
    parsed = parser.parse_args()

    team_name, _ = os.path.splitext(parsed.filename)
    date_range = parsed.date_query.split("..")
    start_date = datetime.strptime(date_range[0], "%Y-%m-%d")
    end_date = datetime.strptime(date_range[-1], "%Y-%m-%d")

    return Args(
        filename=parsed.filename,
        team_name=team_name,
        date_query=parsed.date_query,
        start_date=start_date,
        end_date=end_date,
    )


def load_team_config(path):
    """Load a team's repo list and excluded-workflow denylist from its manifest."""
    with open(path) as f:
        data = json.load(f)
    return TeamConfig(
        repos=data["repos"],
        excluded_workflows=data.get("excluded_workflows", []),
    )


def configure_logger():
    """Return the shared 'MetricLogger' that appends message-only lines to output.log."""
    logger = logging.getLogger("MetricLogger")
    logger.setLevel(logging.INFO)

    fh = logging.FileHandler("output.log")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter("%(message)s"))

    # Avoid stacking duplicate handlers if this is called more than once.
    if not logger.handlers:
        logger.addHandler(fh)

    return logger
