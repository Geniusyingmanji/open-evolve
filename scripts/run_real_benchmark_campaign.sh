#!/usr/bin/env bash
set -u -o pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="${ROOT_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}"

STAMP="$(date -u +%Y%m%d_%H%M%S)"
CAMPAIGN_DIR="${OPEN_EVOLVE_CAMPAIGN_DIR:-${ROOT_DIR}/.open_evolve/campaigns/${STAMP}}"
mkdir -p "$CAMPAIGN_DIR"

run_step() {
  local name="$1"
  shift
  local log_path="${CAMPAIGN_DIR}/${name}.log"
  local status_path="${CAMPAIGN_DIR}/${name}.status"
  {
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] START ${name}"
    echo "COMMAND: $*"
    "$@"
    rc=$?
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] END ${name} rc=${rc}"
    echo "${rc}" > "${status_path}"
    return "${rc}"
  } > "${log_path}" 2>&1
}

echo "campaign_dir=${CAMPAIGN_DIR}" | tee "${CAMPAIGN_DIR}/campaign.env"

run_step frontier_gpt55_archive_25eval \
  python3 -m open_evolve.cli run-frontier \
    --benchmark WirelessChannelSimulation/HighReliableSimulation \
    --workspace .open_evolve/frontier_campaign \
    --run-id "frontier_gpt55_archive_25eval_${STAMP}" \
    --search archive \
    --iterations 24 \
    --max-evaluations 25 \
    --parent-pool-size 2 \
    --samples 1 \
    --max-output-tokens 7000 \
    --llm-timeout-seconds 120 \
    --llm-retries 1 \
    --timeout-seconds 900 \
    --evaluator-timeout-seconds 300

run_step ale_ahc039_numeric_25eval \
  python3 -m open_evolve.cli run-ale \
    --problem ahc039 \
    --lite \
    --workspace .open_evolve/ale_campaign \
    --run-id "ale_ahc039_numeric_25eval_${STAMP}" \
    --operator numeric \
    --iterations 12 \
    --max-evaluations 25 \
    --samples 3 \
    --numeric-jitter 9000 \
    --numeric-changes 2 \
    --numeric-min-abs 1000 \
    --code-language cpp20 \
    --judge-version 202301 \
    --num-workers 1 \
    --timeout-seconds 900

run_step ale_ahc039_private_final \
  python3 -m open_evolve.cli eval-ale \
    --problem ahc039 \
    --lite \
    --split private \
    --code-language cpp20 \
    --judge-version 202301 \
    --num-workers 1 \
    --timeout-seconds 900

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] campaign complete" | tee -a "${CAMPAIGN_DIR}/campaign.env"
