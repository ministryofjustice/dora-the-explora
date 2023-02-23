import requests
from datetime import datetime
import argparse
import json
import os

ACCESS_TOKEN = ''
OWNER = 'ministryofjustice'
NAME = "modernisation-platform"

# API Endpoint
api_url = f"https://api.github.com/repos/{OWNER}/{NAME}/actions/runs"

# Initialize variables
runs = []
next_page = 1
per_page = 100

# Calculate the datetime 90 days ago
date_format = "%Y-%m-%dT%H:%M:%SZ"

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
    params = {"branch": "main", "status": "success", "per_page": per_page}

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
# Retrieve the workflow runs and count the number of successful runs
num_successful_runs = len(runs)

# Compute the number of days between the earliest and latest successful runs
earliest_run_date = datetime.strptime(runs[-1]["created_at"], date_format)
latest_run_date = datetime.strptime(runs[0]["created_at"], date_format)
delta_days = (latest_run_date - earliest_run_date).days

# Calculate the daily deployment frequency
deployment_frequency = num_successful_runs / delta_days

# Print the result
print(f"Daily deployment frequency for {filename}: {deployment_frequency:.2f} deployments/day")
