import requests

# Shared authentication / accept headers for the GitHub REST API.
ACCEPT_HEADER = "application/vnd.github.v3+json"
REQUEST_TIMEOUT = 30


def _headers(token):
    return {"Authorization": f"Bearer {token}", "Accept": ACCEPT_HEADER}


def _paginate(url, headers, params=None):
    """Yield each JSON response page, following GitHub's Link 'next' header.

    ``params`` applies to the first request only; each subsequent page is fetched
    from the fully-formed ``next`` URL (which already encodes page and query
    parameters), so ``params`` is cleared after the first request.
    """
    while True:
        response = requests.get(
            url, headers=headers, params=params, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
        yield response.json()

        if "next" not in response.links:
            break

        url = response.links["next"]["url"]
        params = None


def get_workflow_runs(owner, repo, token, params):
    """Retrieves all workflow runs for a given repository using the provided query parameters."""
    url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs"
    workflow_runs = []
    try:
        for page in _paginate(url, _headers(token), params):
            workflow_runs.extend(page["workflow_runs"])
        return workflow_runs
    except requests.exceptions.RequestException as e:
        raise ValueError(f"Error retrieving workflow runs: {e}") from e


def get_merged_pull_requests(owner, repo, token, params):
    """Retrieve all merged pull requests for a repo using the given query params."""
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    merged_pull_requests = []
    try:
        for page in _paginate(url, _headers(token), params):
            # Filter only the merged pull requests from the list of closed pull requests
            merged_pull_requests.extend(
                pr for pr in page if pr["merged_at"] is not None
            )
        return merged_pull_requests
    except requests.exceptions.RequestException as e:
        raise ValueError(f"Error retrieving pull requests: {e}") from e


def make_github_api_call(url, token, params=None):
    """Retrieve all pages of a GitHub list endpoint (e.g. a PR's commits).

    Returns the concatenated items across every page so callers can rely on the
    true first/last element, not just the first page's 30 items.
    """
    items = []
    try:
        for page in _paginate(url, _headers(token), params):
            items.extend(page)
        return items
    except requests.exceptions.RequestException as e:
        raise ValueError(f"Error retrieving data from {url}: {e}") from e
