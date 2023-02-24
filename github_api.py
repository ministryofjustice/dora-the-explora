import requests

def get_workflow_runs(owner, repo, token, params):
    """Retrieves all workflow runs for a given repository using the provided query parameters."""

    # Set the necessary authentication headers using the personal access token (PAT)
    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.github.v3+json'
    }

    # Define the API endpoint to retrieve the workflow runs for the given repository
    url = f'https://api.github.com/repos/{owner}/{repo}/actions/runs'

    # Retrieve all workflow runs for the given repository using the provided query parameters
    workflow_runs = []
    try:
        while True:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            response_json = response.json()

            workflow_runs.extend(response_json['workflow_runs'])

            if 'next' in response.links:
                url = response.links['next']['url']
            else:
                break

        return workflow_runs

    except requests.exceptions.RequestException as e:
        # Raise an error if there's a problem retrieving the workflow runs
        raise ValueError(f"Error retrieving workflow runs: {e}")
