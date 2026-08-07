"""Per-repository DORA metrics for Cloud Platform (CP) tenants.

Each Cloud Platform *production* namespace provisions a GitHub Actions deployer
service account via a Terraform resource file (``resources/*github*.tf`` in the
``cloud-platform-environments`` repo). That definition names the repository the
service account deploys for, via ``github_repo = "..."`` (module-template form)
or ``github_repos = ["...", ...]`` (locals form). This is the authoritative
namespace->repo link -- more reliable than the free-text ``source-code``
annotation -- so this tool resolves tenant repos from the service account
definitions of production namespaces, then computes the four DORA metrics for
each from its GitHub Deployments.

IMPORTANT difference from MPE: CP applications deploy in different ways. Some
emit GitHub Deployment objects (usable here); many deploy via Concourse/kubectl
and emit NONE. This tool therefore performs a capability check per repo and
clearly reports "no GitHub deployment signal" rather than silently miscounting.
For repos that DO emit deployments, over the requested window:

  * Deployment Frequency  -- successful production deployments per day.
  * Lead Time for Change  -- deployed commit author-date -> prod deploy success.
  * Change Failure Rate   -- share of conclusive prod deployments hitting error.
  * Mean Time to Recovery -- failed prod deployment -> next successful one.

"Production" is inferred from the environment name (production/prod/live) or the
deployment's production_environment flag.

Auth: reads ACCESS_TOKEN (see metrics_common.get_access_token). Needs repo read
on cloud-platform-environments and on the tenant repos.

Usage:
    python3 cp_dora.py --since 2025-01-01
    python3 cp_dora.py --repos laa-court-data-adaptor,address-matcher-api
    python3 cp_dora.py --limit 2    # only scan 2 code-search pages (quick)
"""

import argparse
import base64
import re
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime

import requests

import github_api
from metrics_common import OWNER, configure_logger, get_access_token

CP_REPO = "cloud-platform-environments"
LIVE_PREFIX = "namespaces/live.cloud-platform.service.justice.gov.uk/"
# The service account definition names the deploy repo as github_repo = "x" or
# github_repos = ["x", ...]; it may live in any *.tf under the namespace.
GITHUB_REPO_RE = re.compile(r'github_repos?\s*=\s*(\[.*?\]|"[^"]+")', re.S)
QUOTED_RE = re.compile(r'"([\w.-]+)"')
PROD_ENV_RE = re.compile(r"(^|[-/])(production|prod|live)([-/]|$)", re.IGNORECASE)
SUCCESS_STATE = "success"
FAILURE_STATES = {"failure", "error"}
MIN_DEPLOYS = 10


def parse_gh_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def month_key(dt):
    return dt.strftime("%Y-%m")


def _api_get(url, token, params=None, max_tries=6):
    headers = github_api._headers(token)
    delay = 2
    for _ in range(max_tries):
        resp = requests.get(url, headers=headers, params=params,
                            timeout=github_api.REQUEST_TIMEOUT)
        if resp.status_code == 200:
            return resp, resp.json()
        if resp.status_code == 404:
            return resp, None  # repo/endpoint gone; caller handles
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
        if data is None:
            break
        yield data
        nxt = resp.links.get("next")
        if not nxt:
            break
        url, params = nxt["url"], None


def _prod_namespace(path):
    """Return the production namespace for a repo file path, else None."""
    if not path.startswith(LIVE_PREFIX):
        return None
    ns = path[len(LIVE_PREFIX):].split("/")[0]
    return ns if (ns.endswith("-prod") or ns.endswith("-production")) else None


def enumerate_cp_repos(token, limit=None):
    """Return CP tenant repos from production namespaces' service account defs.

    Uses GitHub code search to find the ``github_repo``/``github_repos``
    argument wherever it lives in a namespace's ``resources/*.tf`` (it is not
    confined to a github-named file), restricts to production namespaces, then
    reads only those files to extract the repo name(s). Code search is capped at
    1000 results and rate-limited, so ``_api_get`` handles the pacing.
    """
    # 1. find candidate files via code search (paths only). Code search returns
    #    at most 1000 results (10 pages of 100); `limit` caps pages for quick runs.
    max_pages = min(limit, 10) if limit else 10
    paths = set()
    for page in range(1, max_pages + 1):
        url = (f"https://api.github.com/search/code?q=github_repo+"
               f"repo:{OWNER}/{CP_REPO}&per_page=100&page={page}")
        _, data = _api_get(url, token)
        items = (data or {}).get("items", [])
        for it in items:
            if _prod_namespace(it["path"]):
                paths.add(it["path"])
        if len(items) < 100:
            break

    # 2. read each candidate file and extract the deploy repo(s)
    repos = set()
    for path in sorted(paths):
        _, blob = _api_get(
            f"https://api.github.com/repos/{OWNER}/{CP_REPO}/contents/{path}",
            token)
        if not blob or "content" not in blob:
            continue
        text = base64.b64decode(blob["content"]).decode("utf-8", "replace")
        m = GITHUB_REPO_RE.search(text)
        if m:
            for name in QUOTED_RE.findall(m.group(1)):
                repos.add(name)
    print(f"resolved {len(repos)} deploy repos from {len(paths)} production "
          f"namespace service-account definitions", file=sys.stderr)
    return sorted(repos)


def repo_dora(repo, since, token, max_deploys=400):
    """Compute DORA for one CP repo, or flag no deployment signal."""
    url = f"https://api.github.com/repos/{OWNER}/{repo}/deployments"
    monthly = defaultdict(int)
    lead_times = []
    n_deploys = 0
    n_conclusive = 0
    n_failed = 0
    outcomes = []
    any_deployments = False

    stop = False
    for page in _paginate(url, token, {"per_page": 100}):
        any_deployments = any_deployments or len(page) > 0
        if stop:
            break
        for dep in page:
            if not (dep.get("production_environment")
                    or PROD_ENV_RE.search(dep.get("environment") or "")):
                continue
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
                    f"https://api.github.com/repos/{OWNER}/{repo}"
                    f"/deployments/{dep['id']}/statuses?per_page=100", token)
            except Exception:
                statuses = None
            statuses = statuses or []
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
                        f"https://api.github.com/repos/{OWNER}/{repo}"
                        f"/commits/{dep['sha']}", token)
                    if commit:
                        ct = parse_gh_time(commit["commit"]["author"]["date"])
                        if (success_t - ct).total_seconds() >= 0:
                            lead_times.append((success_t - ct).total_seconds())
                # A missing/errored commit drops one deployment's lead time only.
                except Exception:  # nosec B110
                    pass

    if not any_deployments:
        return {"repo": repo, "deploys": 0, "signal": False}

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
        "repo": repo, "signal": True, "deploys": n_deploys,
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
    parser.add_argument("--repos", default=None,
                        help="comma-separated repo names (default: enumerate CP)")
    parser.add_argument("--limit", type=int, default=None,
                        help="cap code-search pages when enumerating (quick runs)")
    args = parser.parse_args()

    since = datetime.strptime(args.since, "%Y-%m-%d")
    token = get_access_token()
    logger = configure_logger()

    repos = (args.repos.split(",") if args.repos
             else enumerate_cp_repos(token, args.limit))
    print(f"{len(repos)} CP tenant repos to check", file=sys.stderr)

    results = []
    for i, repo in enumerate(repos):
        print(f"[{i+1}/{len(repos)}] {repo}", file=sys.stderr)
        try:
            results.append(repo_dora(repo, since, token))
        except Exception as e:
            print(f"  skip {repo}: {e}", file=sys.stderr)

    with_signal = [r for r in results if r.get("signal")]
    no_signal = [r for r in results if not r.get("signal")]

    header = (f"DORA metrics for Cloud Platform tenants (production deployments "
              f"since {args.since})")
    rows = [header, "",
            f"repos checked: {len(results)}   with GitHub deployment signal: "
            f"{len(with_signal)}   without (Concourse/kubectl etc): {len(no_signal)}",
            "",
            f"{'repository':<48}{'deploys':>8}{'DF/day':>8}"
            f"{'leadT':>8}{'CFR':>7}{'MTTR':>9}",
            "-" * 88]
    for r in sorted(with_signal, key=lambda r: -r["deploys"]):
        flag = "" if r["deploys"] >= MIN_DEPLOYS else "  (low n)"
        rows.append(
            f"{r['repo']:<48}{r['deploys']:>8}{r['df_per_day']:>8.2f}"
            f"{_fmt(r['lead_time_median_h'],'h'):>8}"
            f"{_fmt(r['cfr_pct'],'%'):>7}{_fmt(r['mttr_median_h'],'h'):>9}{flag}")
    if no_signal:
        rows.append("")
        rows.append(f"No GitHub deployment signal ({len(no_signal)} repos, likely "
                    f"Concourse/kubectl): "
                    + ", ".join(r["repo"] for r in no_signal[:40])
                    + (" ..." if len(no_signal) > 40 else ""))

    report = "\n".join(rows)
    print(report)
    logger.info(report)


if __name__ == "__main__":
    main()
