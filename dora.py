import requests
import datetime

# replace with your personal access token and repo information
<<<<<<< HEAD
<<<<<<< HEAD
ACCESS_TOKEN = ''
OWNER = 'ministryofjustice'
REPO = 'modernisation-platform-environments'
=======
ACCESS_TOKEN = 'your_token_here'
OWNER = 'owner_name'
REPO = 'repo_name'
>>>>>>> 9fa47a0 (Breaking out mean time to recovery into hours and minutes.)
=======
ACCESS_TOKEN = ''
OWNER = 'ministryofjustice'
REPO = 'modernisation-platform'
>>>>>>> 1b116fa (Optimising the script)

# headers to include the access token in the request
headers = {
    'Authorization': f'token {ACCESS_TOKEN}',
    'Accept': 'application/vnd.github.v3+json'
}

# endpoint for getting workflow runs on the main branch for the last 90 days
url = f'https://api.github.com/repos/{OWNER}/{REPO}/actions/runs?branch=main&per_page=100&status=completed&event=push'

# retrieve all pages of the workflow runs
runs = []
while url:
    response = requests.get(url, headers=headers)
    page_runs = response.json()['workflow_runs']
    runs.extend(page_runs)
    url = response.links.get('next', {}).get('url')

# sort the workflow runs by created_at in ascending order
runs = sorted(runs, key=lambda run: datetime.datetime.fromisoformat(run['created_at'].replace('Z', '')))

# filter the unsuccessful runs
unsuccessful_runs = [run for run in runs if run['conclusion'] != 'success']

# find the periods between the first unsuccessful run and the first subsequent successful run for each workflow
workflow_periods = {}
for run in runs:
    workflow_id = run['workflow_id']
    workflow_name = run['name']
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

print(workflow_recovery_times)
# calculate the mean time to recovery across all workflows
total_recovery_time = sum((time_to_recovery for workflow_times in workflow_recovery_times.values() for time_to_recovery in workflow_times), datetime.timedelta(0))
total_workflows = len(workflow_recovery_times)
mean_time_to_recovery = total_recovery_time / total_workflows if total_workflows > 0 else None

if mean_time_to_recovery is not None:
    days, seconds = mean_time_to_recovery.days, mean_time_to_recovery.seconds
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    print(f"Number of unsuccessful runs: {len(unsuccessful_runs)}")
    print(f"Mean time to recovery: {days} days, {hours} hours, {minutes} minutes")
else:
    print("No unsuccessful workflow runs found in the last 90 days.")