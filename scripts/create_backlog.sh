#!/usr/bin/env bash
# Creates the SaskAir Watch product backlog as GitHub issues.
# Run once from the repo folder after: gh auth login
# Then add the issues to your GitHub Project board (Projects > Add items).
set -euo pipefail

for l in "sprint-1:1d76db" "sprint-2:0e8a16" "sprint-3:fbca04" "stretch:cccccc" \
         "priority-high:b60205" "priority-medium:d93f0b" "priority-low:c5def5"; do
  gh label create "${l%%:*}" --color "${l##*:}" --force >/dev/null
done

issue () { gh issue create --title "$1" --body "$2" --label "$3" >/dev/null && echo "Created: $1"; }

# Sprint 1 - Data collection and pipeline
issue "SA-1 Set up GitHub repo, branch rules and project board" "Story points: 2. Done when: main is protected, PRs need 1 review, board has To do / In progress / Done." "sprint-1,priority-high"
issue "SA-2 Define AWS resources in CloudFormation" "As a developer, I want all AWS resources in a template so we can rebuild the stack any time. Story points: 5. Done when: template creates S3, Lambda, IAM role, EventBridge rule and passes cfn-lint." "sprint-1,priority-high"
issue "SA-3 CI/CD pipeline with GitHub Actions" "As a developer, I want every PR tested and every merge deployed automatically. Story points: 5. Done when: tests + lint run on PRs, deploy + smoke test run on merge to main." "sprint-1,priority-high"
issue "SA-4 Collect weather and AQI every hour" "As a user, I want fresh data every hour without anyone doing it by hand. Story points: 5. Done when: Ingest Lambda calls both Open-Meteo APIs, retries on failure, runs hourly." "sprint-1,priority-high"
issue "SA-5 Archive raw data in S3 by date" "As the team, I want raw JSON saved in date folders so we keep the original data. Story points: 3. Done when: a new file appears under raw/city=saskatoon/year=/month=/day=/ every hour." "sprint-1,priority-medium"
issue "SA-6 CloudWatch logs and error alarm" "As the team, I want to know if the hourly job fails. Story points: 2. Done when: logs kept 14 days and alarm fires on any Lambda error." "sprint-1,priority-medium"

# Sprint 2 - Processing, storage and API
issue "SA-7 Clean and transform the data" "Story points: 5. Handle missing values, convert units, round numbers, with unit tests." "sprint-2,priority-high"
issue "SA-8 Store clean data in DynamoDB" "Story points: 3. One record per city per hour." "sprint-2,priority-high"
issue "SA-9 Query Lambda for latest, trends and daily averages" "Story points: 5." "sprint-2,priority-high"
issue "SA-10 API Gateway REST endpoints /latest and /history" "Story points: 3." "sprint-2,priority-high"
issue "SA-11 API tests in the pipeline" "Story points: 2." "sprint-2,priority-medium"

# Sprint 3 - Dashboard, alerts and monitoring
issue "SA-12 Dashboard website hosted on S3" "Story points: 5. HTML, CSS, JavaScript." "sprint-3,priority-high"
issue "SA-13 AQI colour level and Chart.js trend charts" "Story points: 3. Current AQI colour, 24-hour and 7-day charts." "sprint-3,priority-high"
issue "SA-14 Email alerts with SNS" "Story points: 3. Alert when AQI or temperature passes a limit." "sprint-3,priority-high"
issue "SA-15 CloudWatch dashboard and missed-run alarm" "Story points: 2." "sprint-3,priority-medium"

# Stretch goal
issue "SA-16 Compare Regina and Prince Albert" "Story points: 3. Only if time allows." "stretch,priority-low"
