# SaskAir Watch

Hourly weather and air quality for Saskatoon, built on AWS with a full DevOps workflow.
DEVP-600 final project by Harsh Thaker and Saket Shah, Saskatchewan Polytechnic.

## Sprint 1 increment (v1.0)

Every hour, EventBridge runs the **Ingest Lambda**. It calls the free Open-Meteo weather and
air quality REST APIs and saves the raw JSON to S3 in date folders:

```
s3://saskair-watch-raw-<account>-<region>/raw/city=saskatoon/year=2026/month=11/day=03/hour=14.json
```

Everything is created by `template.yaml` (CloudFormation) and deployed by GitHub Actions.

```
.github/workflows/pipeline.yml   CI/CD: test + lint on PRs, deploy + smoke test on main
template.yaml                    S3 bucket, Lambda, IAM role, EventBridge rule, log group, error alarm
src/ingest/app.py                Ingest Lambda (Python 3.12, no extra libraries)
tests/test_ingest.py             Unit tests (URLs, S3 key, retries, handler)
scripts/create_backlog.sh        Creates the product backlog as GitHub issues
```

## Setup (one time)

1. **Create the repo.** Make a new GitHub repo, push this folder, and add your partner as a collaborator.
2. **Protect main.** Settings > Branches > add a rule for `main`: require a pull request with 1 approval
   and require the "Build and test" check to pass.
3. **Create the backlog.** Install the GitHub CLI, run `gh auth login`, then `bash scripts/create_backlog.sh`.
   Create a GitHub Project (Board view) and add all the issues. Use columns To do / In progress / Done.
4. **Add AWS credentials.** In the repo go to Settings > Secrets and variables > Actions.
   - Secrets: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and, for AWS Academy, `AWS_SESSION_TOKEN`.
   - Variables: `ARTIFACT_BUCKET` (a globally unique name, e.g. `saskair-artifacts-<yourname>`),
     `AWS_REGION` (e.g. `us-east-1`).
   - **AWS Academy Learner Lab only:** you can't create IAM roles there, so also add the variable
     `EXISTING_ROLE_ARN` = the ARN of `LabRole` (IAM > Roles > LabRole). Learner Lab keys expire when
     the lab session ends, so copy fresh keys into the secrets before each deploy.
5. **Set a budget.** In AWS Billing, create a monthly budget (e.g. $5) with an email alert.

## Daily workflow

```bash
git checkout -b feature/SA-4-ingest-lambda
# make changes
python -m pytest -v          # run tests locally (pip install -r requirements-dev.txt)
git push -u origin feature/SA-4-ingest-lambda
# open a pull request -> tests run -> partner reviews -> merge -> pipeline deploys
```

## Check that it works (Sprint Review demo)

- **GitHub > Actions:** the latest run on `main` is green, including "Smoke test".
- **Lambda > saskair-watch-ingest > Test:** run it once and see `statusCode 200` with the AQI and temperature.
- **S3 > saskair-watch-raw-...:** open `raw/city=saskatoon/...` and see one file per hour.
- **CloudWatch > Log groups > /aws/lambda/saskair-watch-ingest:** one log entry per hour.
- **EventBridge > Rules > saskair-watch-hourly:** schedule `rate(1 hour)`, enabled.

Tag the release when Sprint 1 is done: `git tag v1.0 && git push origin v1.0`.

## Clean up

Delete the `saskair-watch` stack in CloudFormation. Empty the raw data bucket first, because
CloudFormation can't delete a bucket that still has files in it.
