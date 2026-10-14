#!/usr/bin/env bash
# Prints a Markdown line-coverage table from lcov reports, used by the CI `coverage` job for the PR
# comment and the job summary. Usage: coverage-summary.sh api=coverage/api.lcov web=web/coverage/lcov.info
# Line coverage = lines hit (LH) / lines found (LF), summed per report and over all reports.
set -euo pipefail

_pct() {
  awk -v hit="$1" -v found="$2" 'BEGIN { if (found == 0) print "n/a"; else printf "%.1f%%", 100 * hit / found }'
}

rows=""
total_found=0
total_hit=0
for arg in "$@"; do
  name="${arg%%=*}"
  file="${arg#*=}"
  if [[ ! -f "$file" ]]; then
    rows+="| ${name} | n/a | report missing |"$'\n'
    continue
  fi
  read -r found hit < <(awk -F: '/^LF:/ { f += $2 } /^LH:/ { h += $2 } END { print f + 0, h + 0 }' "$file")
  total_found=$((total_found + found))
  total_hit=$((total_hit + hit))
  rows+="| ${name} | $(_pct "$hit" "$found") | ${hit} / ${found} |"$'\n'
done

echo "### Coverage"
echo
echo "| Suite | Lines | Hit / found |"
echo "|---|---|---|"
printf '%s' "$rows"
echo "| **Total** | **$(_pct "$total_hit" "$total_found")** | ${total_hit} / ${total_found} |"
