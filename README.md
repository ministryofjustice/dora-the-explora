# DORA Metrics from GitHub

## What do these scripts do?

These scripts are an attempt to calculate [DORA METRICS](https://cloud.google.com/blog/products/devops-sre/using-the-four-keys-to-measure-your-devops-performance) using information retrieved via GitHub API.

The repo contains five python scripts, `cfr.py`, `df.py`, `ltfc.py` and `mttr.py` compute each of the four metrics while `github_apy.py` is a library module containing the calls to the API.

## How are the metrics calculated?

* `cfr.py` -- computes Change Failure Rate by retrieving the last 1000 workflow runs against the `main` branch and then dividing the number of unsuccesful runs by the total number of runs and multiplying bu 100% to get a percentage. Assumptions are made regarding what each failure represents, and I offer no opinion on how reasonable this assumption is. 
* `df.py` -- computes Deployment Frequency by retrieving the last 1000 workflow runs against the `main` branch, computing the number of days between the first and the last run and the dividing the number of runs by the number of days to get an approximate number of deployments to production over the 24 hour period.
* `ltfc.py` -- computes Lead Time for Change and is the longest-executing script for large number of PRs, as it must retrieve commits for every merged PR. The script only retrieves commits for up to 500 merged PRs as a way to balance the execution time and having large enough data set for the metric to be meaningfull. The metric is computed by averaging out the time period between the last commit to each PR (when development can be considered complete and the change is ready for production) and the time it is merged (kicking off the deployment into production.)
* `mttr.py` -- computes Mean Time to Recovery and takes failed workflow runs on main as a proxy for failures and subsequent successful execution of the same workflow as recovery. The reasonableness of these assumptions are left up to the judgement of the reader. Doubtless, using actual monitoring outputs and alerts would provide a more accurate measurement of this metric. The metric is computed by taking the mean of the periods between the first failure of the workflow run on main and the first susequent successful run of the same workflow. Failures with no subsequent successful runs are discarded. The sum of the lengths of the failure/success periods is divided by the total number of periods to compute the metric.

## How to run them?

These scripts rely heavily on workflow runs which only authenticated users have access to, so running them requires having a [Github Personal Access Token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token) with enough permissions to get workflow runs for Github Actions on the target repositories. The scripts will retrieve the token from the `ACCESS_TOKEN` environment variable. With the envvar unset, the scripts will fail with authentication errors. 

Each script takes as a parameter a `json` file which contains a list of repositories against which it should run. See `modernisation-platform.json` for an example. The reason for the `json` is that the scripts don't compute DORA metrics for a repo, the metrics are computed for a team, which the name of the file used as the team name in the script outputs. The list of repos will contain all repositories which contain the team-managed code. The metrics are computed over all the repos in the list. 

To execute each script, run `python3 script_name.py team.json`
