import requests
import datetime
import json
import pprint
import argparse
import os
# replace with your personal access token and repo information

OWNER = 'ministryofjustice'

# Read ACCESS_TOKEN from environment
ACCESS_TOKEN = os.environ['ACCESS_TOKEN']

# headers to include the access token in the request

headers = {
    'Authorization': f'token {ACCESS_TOKEN}',
    'Accept': 'application/vnd.github.v3+json'
}

# set up the command-line argument parser
parser = argparse.ArgumentParser()
parser.add_argument('filename', help='path to the input JSON file')
args = parser.parse_args()


# load the repository names from a JSON file
with open(args.filename, 'r') as f:
    repos = json.load(f)['repos']

filename, file_extension = os.path.splitext(args.filename)

# create a list to store the workflow runs for the repositories
runs = []

# url = f'https://api.github.com/repos/{OWNER}/{REPO}/actions/runs?branch=main&per_page=100&status=completed'

# loop over each repository
for repo in repos:
    # API Endpoint
    api_url = f"https://api.github.com/repos/{OWNER}/{repo}/actions/runs"

    # Initialize variables
    next_page = 1
    per_page = 100

    # Calculate the datetime 90 days ago
    date_format = "%Y-%m-%dT%H:%M:%SZ"

    # Get all successful workflow runs on the main branch
    headers = {"Authorization": f"Token {ACCESS_TOKEN}"}
    params = {"branch": "main", "per_page": per_page}
    while next_page is not None:
        if next_page != 1:
            params["page"] = next_page
        response = requests.get(api_url, headers=headers, params=params)
        if response.status_code == 200:
            runs += response.json()["workflow_runs"]
            if "Link" in response.headers:
                links = response.headers["Link"]
                next_page_link = [link for link in links.split(",") if "rel=\"next\"" in link]
                if next_page_link:
                    next_page = int(next_page_link[0].split("page=")[-1].split(">")[0])
                else:
                    next_page = None
            else:
                next_page = None
        else:
            print(f"Error retrieving workflow runs: {response.status_code}")
            break

# sort the workflow runs by created_at in ascending order
runs = sorted(runs, key=lambda run: datetime.datetime.fromisoformat(run['created_at'].replace('Z', '')))

# filter the unsuccessful runs
unsuccessful_runs = [run for run in runs if run['conclusion'] != 'success']

# find the periods between the first unsuccessful run and the first subsequent successful run for each workflow
workflow_periods = {}
for run in runs:
    workflow_id = run['workflow_id']
    workflow_name = run['name']
    if workflow_name == "Terraform Static Code Analysis":
        continue
    if run['conclusion'] != 'success':
        if workflow_id not in workflow_periods:
            workflow_periods[workflow_id] = []
        if not workflow_periods[workflow_id] or workflow_periods[workflow_id][-1]['end']:
            failure_time = datetime.datetime.fromisoformat(run['created_at'].replace('Z', ''))
            workflow_periods[workflow_id].append({'start': failure_time, 'end': None})
            print(f"Found new failure for workflow '{workflow_name}' at {failure_time}")
    else:
        if workflow_id in workflow_periods and workflow_periods[workflow_id]:
            period = workflow_periods[workflow_id][-1]
            if not period['end']:
                success_time = datetime.datetime.fromisoformat(run['created_at'].replace('Z', ''))
                period['end'] = success_time
                print(f"Found new success for workflow '{workflow_name}' at {success_time}")


# calculate the time to recovery for each workflow
workflow_recovery_times = {workflow_id: [period['end'] - period['start'] for period in periods if period['end']]
                          for workflow_id, periods in workflow_periods.items()}

pprint.pprint(workflow_recovery_times)

# calculate the mean time to recovery across all workflows
total_recovery_time = sum((time_to_recovery for workflow_times in workflow_recovery_times.values() for time_to_recovery in workflow_times), datetime.timedelta(0))
total_workflows = len(workflow_recovery_times)
mean_time_to_recovery = total_recovery_time / total_workflows if total_workflows > 0 else None

if mean_time_to_recovery is not None:
    days, seconds = mean_time_to_recovery.days, mean_time_to_recovery.seconds
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    print(f"Number of unsuccessful runs: {len(unsuccessful_runs)}")
    print(f"Mean time to recovery for {filename}: {days} days, {hours} hours, {minutes} minutes")
else:
    print("No unsuccessful workflow runs found in the last 90 days.")