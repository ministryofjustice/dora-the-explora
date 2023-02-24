import requests
from datetime import datetime, timedelta
import argparse
import json
import os
from github_api import get_workflow_runs


OWNER = 'ministryofjustice'


# Initialize variables
runs = []
next_page = 1
per_page = 100

# Calculate the date 90 days ago from today's date
ninety_days_ago = datetime.now() - timedelta(days=90)
date_string = ninety_days_ago.strftime('%Y-%m-%dT%H:%M:%SZ')
date_format = "%Y-%m-%dT%H:%M:%SZ"

# Read ACCESS_TOKEN from environment
ACCESS_TOKEN = os.environ['ACCESS_TOKEN']

# Get all successful workflow runs on the main branch
# headers to include the access token in the request
headers = {
    'Authorization': f'token {ACCESS_TOKEN}',
    'Accept': 'application/vnd.github.v3+json'
}

# set up the command-line argument parser
parser = argparse.ArgumentParser()
parser.add_argument('filename', help='path to the input JSON file')
args = parser.parse_args()

filename, file_extension = os.path.splitext(args.filename)

# load the repository names from a JSON file
with open(args.filename, 'r') as f:
    repos = json.load(f)['repos']

for repo in repos:
    params = {"branch": "main", "status": "success", "per_page": per_page, "completed_at": f">{date_string}"}
    try:
        runs = get_workflow_runs(OWNER,repo, ACCESS_TOKEN,params)
    except requests.exceptions.RequestException as e:
        # Log message if there's a problem retrieving the workflow runs
        print(f"Error retrieving workflow runs: {e}")

# Count the number of successful runs
num_successful_runs = len(runs)

# Compute the number of days between the earliest and latest successful runs
earliest_run_date = datetime.strptime(runs[-1]["created_at"], date_format)
latest_run_date = datetime.strptime(runs[0]["created_at"], date_format)
delta_days = (latest_run_date - earliest_run_date).days

# Calculate the daily deployment frequency
deployment_frequency = num_successful_runs / delta_days

# Print the result
print(f"Daily deployment frequency for {filename}: {deployment_frequency:.2f} deployments/day")
