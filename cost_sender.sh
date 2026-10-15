#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
START=$(date -d '-4 days' +%F)
END=$(date +%F)

RAW=$(aws ce get-cost-and-usage \
  --time-period "Start=$START,End=$END" \
  --granularity DAILY \
  --metrics UnblendedCost \
  --group-by "Type=DIMENSION,Key=SERVICE" \
  --region us-east-1 \
  --output json)

CSV="$SCRIPT_DIR/cost-breakdown.csv"
IMAGE="$SCRIPT_DIR/cost-breakdown.png"

echo "$RAW" | jq -r '
def r: (. * 100 | round) / 100;
def row($name; $m; $dates):
  [$dates[] | ($m[.] // 0)] as $v
  | {name: $name, total: ($v | add // 0), vals: $v};

[.ResultsByTime[].TimePeriod.Start] as $dates
| (reduce .ResultsByTime[] as $day ({};
    reduce $day.Groups[] as $g (.;
      .[$g.Keys[0]][$day.TimePeriod.Start] = ($g.Metrics.UnblendedCost.Amount | tonumber)))) as $svc
| (reduce .ResultsByTime[] as $day ({};
    .[$day.TimePeriod.Start] = ([$day.Groups[].Metrics.UnblendedCost.Amount | tonumber] | add // 0))) as $tot
| (["Service", "Service total"] + $dates | @csv),
  ( ([row("Total costs"; $tot; $dates)]
     + ([$svc | to_entries[] | row(.key; .value; $dates)] | sort_by(-.total)))
    | .[]
    | ([.name, (.total | r)] + (.vals | map(r))) | @csv )
' > "$CSV"

echo "Saved: $CSV"

python3 "$SCRIPT_DIR/generate_cost_image.py" "$CSV" "$IMAGE"
echo "Image: $IMAGE"

MESSAGE="Daily AWS Cost Summary Bill From $(date -d '-4 days' '+%d %b') - $(date -d '-1 day' '+%d %b')"

python3 "$SCRIPT_DIR/send_to_slack.py" "$IMAGE" "$MESSAGE"
echo "Done: image sent to Slack."