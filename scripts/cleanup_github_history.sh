#!/usr/bin/env bash
set -euo pipefail

repo="repos/${GITHUB_REPOSITORY}"
current_run=$(gh api "$repo/actions/runs/$GITHUB_RUN_ID")
workflow_id=$(jq -er '.workflow_id' <<< "$current_run")
run_started_at=$(jq -er '.run_started_at' <<< "$current_run")

deployments=$(gh api --paginate --slurp "$repo/deployments?environment=github-pages&per_page=100")
# Confirm the newest Pages deployment belongs to this run before deleting anything.
latest_deployment=$(jq -ce 'add | sort_by(.created_at, .id) | last' <<< "$deployments")
latest_id=$(jq -er     --arg sha "$GITHUB_SHA" --arg start "$run_started_at"     'select(.sha == $sha and .created_at >= $start) | .id' <<< "$latest_deployment")
latest_state=$(gh api "$repo/deployments/$latest_id/statuses?per_page=1" --jq '.[0].state')
if [[ "$latest_state" != "success" ]]; then
    echo "Expected successful github-pages deployment $latest_id, found: $latest_state" >&2
    exit 1
fi

old_deployments=$(jq -r --argjson keep "$latest_id" 'add | .[] | select(.id != $keep) | .id' <<< "$deployments")
old_runs=$(gh api --paginate "$repo/actions/workflows/$workflow_id/runs?per_page=100"     --jq ".workflow_runs[] | select(.status == \"completed\" and .run_number < $GITHUB_RUN_NUMBER) | .id")

for id in $old_deployments; do
    state=$(gh api "$repo/deployments/$id/statuses?per_page=1" --jq '.[0].state')
    if [[ "$state" != "inactive" ]]; then
        gh api --silent --method POST "$repo/deployments/$id/statuses" -f state=inactive
    fi
    gh api --silent --method DELETE "$repo/deployments/$id"
    echo "Deleted github-pages deployment $id"
done

for id in $old_runs; do
    gh api --silent --method DELETE "$repo/actions/runs/$id"
    echo "Deleted workflow run $id"
done
