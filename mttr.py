import requests
from datetime import datetime, timedelta
from github_api import get_workflow_runs
import json
import pprint
import argparse
import os
from collections import defaultdict
# replace with your personal access token and repo information

OWNER = 'ministryofjustice'

workflow_periods = defaultdict(list)
workflow_stacks = defaultdict(list)

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

# Calculate the date 90 days ago from today's date
ninety_days_ago = datetime.now() - timedelta(days=90)
date_string = ninety_days_ago.strftime('%Y-%m-%dT%H:%M:%SZ')

# loop over each repository
for repo in repos:


    # Initialize variables
    next_page = 1
    per_page = 100

    # Get all successful workflow runs on the main branch
    headers = {"Authorization": f"Token {ACCESS_TOKEN}"}
    params = {"branch": "main", "per_page": per_page, "completed_at": f">{date_string}"}
    try:
        runs = get_workflow_runs(OWNER,repo, ACCESS_TOKEN,params)
    except requests.exceptions.RequestException as e:
        # Log message if there's a problem retrieving the workflow runs
        print(f"Error retrieving workflow runs: {e}")

# sort the workflow runs by created_at in ascending order
runs = sorted(runs, key=lambda run: datetime.fromisoformat(run['created_at'].replace('Z', '')))

# filter the unsuccessful runs
unsuccessful_runs = [run for run in runs if run['conclusion'] != 'success']

# find the periods between the first unsuccessful run and the first subsequent successful run for each workflow
for run in runs:
    workflow_id = run['workflow_id']
    workflow_name = run['name']

    if workflow_name == "Terraform Static Code Analysis":
        continue

    timestamp = datetime.fromisoformat(run['created_at'].replace('Z', ''))

    if run['conclusion'] != 'success':
        if not workflow_stacks[workflow_id]:
            workflow_stacks[workflow_id].append(timestamp)
            print(f"Found new failure for workflow '{workflow_name}' at {timestamp}")
    else:
        if workflow_stacks[workflow_id]:
            start = workflow_stacks[workflow_id].pop()
            period = {'start': start, 'end': timestamp}
            workflow_periods[workflow_id].append(period)
            print(f"Found new success for workflow '{workflow_name}' at {timestamp}")
        workflow_stacks[workflow_id] = []
# calculate the time to recovery for each workflow
workflow_recovery_times = {workflow_id: [period['end'] - period['start'] for period in periods if period['end']]
                          for workflow_id, periods in workflow_periods.items()}

pprint.pprint(workflow_recovery_times)

# calculate the mean time to recovery across all workflows
total_recovery_time = sum((time_to_recovery for workflow_times in workflow_recovery_times.values() for time_to_recovery in workflow_times), timedelta(0))
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