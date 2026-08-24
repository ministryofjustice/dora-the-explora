"""Per-application DORA metrics for Modernisation Platform Environments (MPE).

Unlike the per-team scripts (cfr/df/ltfc/mttr), which infer deployments from
"any workflow run on main", this computes the four DORA metrics for each MPE
application from its real, env-gated production deployments. Each application
deploys to a ``<app>-production`` GitHub environment on the
``modernisation-platform-environments`` repository, so a deployment there is a
genuine production release (approved via the environment's deployment gate) --
a much cleaner signal than counting CI runs.

Per application, over the requested window:
  * Deployment Frequency  -- successful production deployments per day, from
    deployment OBJECTS (which persist for years).
  * Lead Time for Change  -- median time from the deployed commit (author date)
    to the production deployment succeeding. Needs the deployment's statuses,
    which GitHub prunes after ~90 days, so this covers the recent window.
  * Change Failure Rate   -- share of conclusive production deployments whose
    status reached failure/error.
  * Mean Time to Recovery -- median time from a failed production deployment to
    the next successful one on the same environment.

The application list is enumerated from the environments repo itself
(terraform/environments/<app>), so it needs no hand-maintained manifest.

Auth: reads ACCESS_TOKEN (see metrics_common.get_access_token), or pass a token
via the environment. Needs repo read on modernisation-platform-environments.

Usage:
    python3 mpe_dora.py --since 2025-01-01
    python3 mpe_dora.py --apps ccms-ebs,nomis --since 2025-01-01
"""

import argparse
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime

import requests

import github_api
from metrics_common import OWNER, configure_logger, get_access_token

MPE_REPO = "modernisation-platform-environments"
SUCCESS_STATE = "success"
FAILURE_STATES = {"failure", "error"}
MIN_DEPLOYS = 10  # apps with fewer production deployments are reported but flagged


def parse_gh_time(value):
    """Parse a GitHub timestamp, tolerating both 'Z' and numeric offsets."""
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def month_key(dt):
    return dt.strftime("%Y-%m")


def _api_get(url, token, params=None, max_tries=6):
    """GET one JSON resource with primary/secondary rate-limit handling."""
    headers = github_api._headers(token)
    delay = 2
    for _ in range(max_tries):
        resp = requests.get(url, headers=headers, params=params,
                            timeout=github_api.REQUEST_TIMEOUT)
        if resp.status_code == 200:
            return resp, resp.json()
        remaining = resp.headers.get("x-ratelimit-remaining")
        if resp.status_code in (403, 429) and remaining == "0":
            reset = resp.headers.get("x-ratelimit-reset")
            wait = 60
            if reset and reset.isdigit():
                wait = min(900, max(1, int(reset) - int(time.time())) + 2)
            print(f"    rate-limited; sleeping {wait}s", file=sys.stderr)
            time.sleep(wait)
            continue
        if resp.status_code in (403, 429, 500, 502, 503):
            time.sleep(delay)
            delay = min(delay * 2, 120)
            continue
        resp.raise_for_status()
    raise RuntimeError(f"giving up on {url}")


def _paginate(url, token, params=None):
    while True:
        resp, data = _api_get(url, token, params=params)
        yield data
        nxt = resp.links.get("next")
        if not nxt:
            break
        url, params = nxt["url"], None


def enumerate_apps(token):
    """Return the MPE application names from terraform/environments/<app>."""
    _, contents = _api_get(
        f"https://api.github.com/repos/{OWNER}/{MPE_REPO}"
        f"/contents/terraform/environments", token)
    return sorted(item["name"] for item in contents if item["type"] == "dir")


def app_dora(app, since, token, max_deploys=400):
    """Compute the four DORA metrics for one MPE application."""
    env = f"{app}-production"
    url = f"https://api.github.com/repos/{OWNER}/{MPE_REPO}/deployments"

    monthly = defaultdict(int)
    lead_times = []
    n_deploys = 0
    n_conclusive = 0
    n_failed = 0
    outcomes = []  # (time, "ok"|"fail") per deployment, for MTTR

    stop = False
    for page in _paginate(url, token, {"per_page": 100, "environment": env}):
        if stop:
            break
        for dep in page:  # newest first
            created = parse_gh_time(dep["created_at"])
            if created < since:
                stop = True
                break
            n_deploys += 1
            monthly[month_key(created)] += 1
            if n_deploys >= max_deploys:
                stop = True
                break

            try:
                _, statuses = _api_get(
                    f"https://api.github.com/repos/{OWNER}/{MPE_REPO}"
                    f"/deployments/{dep['id']}/statuses?per_page=100", token)
            except Exception:
                statuses = []
            success_t = None
            failed = False
            for s in statuses:
                st = s["state"]
                if st == SUCCESS_STATE and success_t is None:
                    success_t = parse_gh_time(s["created_at"])
                if st in FAILURE_STATES:
                    failed = True
            if statuses:
                n_conclusive += 1
                if failed:
                    n_failed += 1
                outcomes.append((success_t or created,
                                 "fail" if (failed and success_t is None) else "ok"))
            if success_t is not None:
                try:
                    _, commit = _api_get(
                        f"https://api.github.com/repos/{OWNER}/{MPE_REPO}"
                        f"/commits/{dep['sha']}", token)
                    ct = parse_gh_time(commit["commit"]["author"]["date"])
                    if (success_t - ct).total_seconds() >= 0:
                        lead_times.append((success_t - ct).total_seconds())
                # A missing/errored commit drops one deployment's lead time only.
                except Exception:  # nosec B110
                    pass

    # MTTR: failed deployment -> next successful deployment
    outcomes.sort(key=lambda e: e[0])
    open_fail = None
    recoveries = []
    for t, outcome in outcomes:
        if outcome == "fail" and open_fail is None:
            open_fail = t
        elif outcome == "ok" and open_fail is not None:
            recoveries.append((t - open_fail).total_seconds())
            open_fail = None

    span_days = max(1, len(monthly) * 30) if monthly else 1
    return {
        "app": app,
        "deploys": n_deploys,
        "df_per_day": n_deploys / span_days,
        "lead_time_median_h": (statistics.median(lead_times) / 3600
                               if lead_times else None),
        "cfr_pct": (100 * n_failed / n_conclusive) if n_conclusive else None,
        "mttr_median_h": (statistics.median(recoveries) / 3600
                          if recoveries else None),
    }


def _fmt(v, suffix=""):
    return f"{v:.1f}{suffix}" if v is not None else "-"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", default="2025-01-01",
                        help="earliest deployment date to consider (YYYY-MM-DD)")
    parser.add_argument("--apps", default=None,
                        help="comma-separated app names (default: all MPE apps)")
    args = parser.parse_args()

    since = datetime.strptime(args.since, "%Y-%m-%d")
    token = get_access_token()
    logger = configure_logger()

    apps = (args.apps.split(",") if args.apps else enumerate_apps(token))

    results = []
    for i, app in enumerate(apps):
        print(f"[{i+1}/{len(apps)}] {app}", file=sys.stderr)
        try:
            results.append(app_dora(app, since, token))
        except Exception as e:
            print(f"  skip {app}: {e}", file=sys.stderr)

    report = format_report(results, args.since)
    print(report)
    logger.info(report)


def _table(rows):
    """Render a Markdown table of app result dicts (deploys-desc)."""
    out = ["| Application | Deploys | DF/day | Lead time | CFR | MTTR |",
           "| --- | --: | --: | --: | --: | --: |"]
    for r in sorted(rows, key=lambda r: -r["deploys"]):
        out.append(
            f"| {r['app']} | {r['deploys']} | {r['df_per_day']:.2f} | "
            f"{_fmt(r['lead_time_median_h'], 'h')} | "
            f"{_fmt(r['cfr_pct'], '%')} | {_fmt(r['mttr_median_h'], 'h')} |")
    return "\n".join(out)


def format_report(results, since):
    """Build a Markdown report: summary, active apps, collapsed long tail."""
    active = [r for r in results if r["deploys"] >= MIN_DEPLOYS]
    low_n = [r for r in results if 0 < r["deploys"] < MIN_DEPLOYS]
    no_deploys = [r for r in results if r["deploys"] == 0]

    total_deploys = sum(r["deploys"] for r in results)
    lead_times = [r["lead_time_median_h"] for r in active
                  if r["lead_time_median_h"] is not None]
    cfrs = [r["cfr_pct"] for r in active if r["cfr_pct"] is not None]

    lines = [
        "# DORA metrics for MPE applications",
        f"Production deployments since **{since}**.",
        "",
        f"- **{len(active)}** applications with ≥{MIN_DEPLOYS} production "
        f"deployments (shown below); {len(low_n)} with fewer, {len(no_deploys)} "
        f"with none (collapsed).",
        f"- **{total_deploys}** production deployments across the cohort.",
    ]
    if lead_times:
        lines.append(f"- Median lead time across active apps: "
                     f"**{statistics.median(lead_times):.1f}h**.")
    if cfrs:
        lines.append(f"- Median change failure rate across active apps: "
                     f"**{statistics.median(cfrs):.0f}%**.")
    lines += ["", "## Active applications", "", _table(active)]

    if low_n:
        lines += ["",
                  f"<details><summary>{len(low_n)} apps with 1–"
                  f"{MIN_DEPLOYS - 1} deployments</summary>", "",
                  _table(low_n), "", "</details>"]
    if no_deploys:
        names = ", ".join(sorted(r["app"] for r in no_deploys))
        lines += ["",
                  f"<details><summary>{len(no_deploys)} apps with no "
                  f"production deployments in range</summary>", "",
                  names, "", "</details>"]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
