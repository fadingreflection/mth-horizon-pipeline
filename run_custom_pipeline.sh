#!/usr/bin/env bash
# Time-horizon pipeline with mode switching:
#   horizon_only  — sparse campaign (<50 task_ids): P50 for current model only
#   full          — enough tasks: legacy anchors + trendline + P50 plot
#
# Usage:
#   ./run_custom_pipeline.sh              # reuse model_runs; refit by mode
#   FORCE_PREPARE=1 ./run_custom_pipeline.sh   # rebuild from .eval + horizon chain
#
# Override mode detection (optional):
#   FORCE_TRENDLINE=1  — always run trendline stages
#   FORCE_TRENDLINE=0  — never run trendline stages
set -euo pipefail

REPO="/home/fedotova/mth-horizon-pipeline"
PY="$REPO/.venv/bin/python"
export PYTHONPATH="$REPO${PYTHONPATH:+:$PYTHONPATH}"
cd "$REPO"

MODE_FILE="$REPO/analysis/figures/data/horizon_mode.json"
TRENDLINE_MIN_DEFAULT=50

echo "=== [1/4] whoami / python ==="
whoami
"$PY" -c 'import sys; print(sys.version)'

echo "=== [2/4] uv sync ==="
uv sync

if [[ "${FORCE_PREPARE:-0}" == "1" ]]; then
  echo "=== [3/4] prepare_runs (FORCE_PREPARE=1) ==="
  cd "$REPO/analysis"
  "$PY" -m figures.stages.prepare_runs \
    --human-snapshot figures/data/human_snapshot.json \
    --output-dir figures/data
else
  echo "=== [3/4] prepare_runs skipped (set FORCE_PREPARE=1 to rebuild from .eval) ==="
  # Infer mode from existing model_runs if horizon_mode.json missing
  if [[ ! -f "$MODE_FILE" ]]; then
    echo "  horizon_mode.json missing — inferring from model_runs.parquet"
    "$PY" - <<PY
import json
from pathlib import Path
import pandas as pd
base = Path("$REPO/analysis/figures/data")
mr = base / "model_runs.parquet"
min_tasks = $TRENDLINE_MIN_DEFAULT
if not mr.exists():
    raise SystemExit("model_runs.parquet not found; run with FORCE_PREPARE=1")
df = pd.read_parquet(mr)
# Prefer non-legacy aliases if present
legacy = {"GPT-2", "GPT-3", "GPT-3.5"}
camp = df[~df["alias"].isin(legacy)] if "alias" in df.columns else df
n = int(camp["task_id"].nunique()) if len(camp) else int(df["task_id"].nunique())
aliases = sorted(camp["alias"].unique().tolist()) if len(camp) and "alias" in camp.columns else []
mode = "full" if n >= min_tasks else "horizon_only"
info = {
    "mode": mode,
    "include_trendline": mode == "full",
    "n_campaign_tasks": n,
    "trendline_min_campaign_tasks": min_tasks,
    "campaign_aliases": aliases,
    "inferred": True,
}
base.mkdir(parents=True, exist_ok=True)
(base / "horizon_mode.json").write_text(json.dumps(info, indent=2))
print("  wrote", info)
PY
  fi
fi

# Resolve whether to run trendline
INCLUDE_TRENDLINE="$("$PY" - <<'PY'
import json, os
from pathlib import Path
force = os.environ.get("FORCE_TRENDLINE")
if force is not None and force != "":
    print("1" if force == "1" else "0")
else:
    p = Path("/home/fedotova/mth-horizon-pipeline/analysis/figures/data/horizon_mode.json")
    info = json.loads(p.read_text())
    print("1" if info.get("include_trendline") else "0")
PY
)"
MODE_NAME="$("$PY" -c "import json; print(json.load(open('$MODE_FILE'))['mode'])")"
N_TASKS="$("$PY" -c "import json; print(json.load(open('$MODE_FILE')).get('n_campaign_tasks','?'))")"

echo "=== mode: $MODE_NAME (campaign tasks=$N_TASKS, include_trendline=$INCLUDE_TRENDLINE) ==="

echo "=== [4/4] time-horizon stages ==="
cd "$REPO/analysis/figures"
if [[ "${FORCE_PREPARE:-0}" == "1" ]]; then
  uv run dvc repro -s bootstrap_runs_human_2M -f
fi
uv run dvc repro -s fit_summaries_human_2M -f

if [[ "$INCLUDE_TRENDLINE" == "1" ]]; then
  echo "--- full mode: fit_trendline + trendline plot ---"
  uv run dvc repro -s fit_trendline_human_2M -f
  uv run dvc repro -s trendline_p50_runs_human_2M -f
else
  echo "--- horizon_only: skipping fit_trendline / trendline plot ---"
fi

echo "=== DONE: horizon summary ==="
"$PY" - <<'PY'
import json
import pandas as pd
from pathlib import Path
base = Path("/home/fedotova/mth-horizon-pipeline/analysis/figures/data")
mode = json.loads((base / "horizon_mode.json").read_text())
print("horizon_mode:", json.dumps(mode, indent=2))
df = pd.read_parquet(base / "model_runs.parquet")
print("\nmodel_runs aliases:")
print(df["alias"].value_counts())
aliases = mode.get("campaign_aliases") or []
if aliases:
    print(f"\ncampaign model rows ({aliases}):")
    print(df[df.alias.isin(aliases)][["alias", "task_id", "score_binarized", "total_tokens"]])
ms = base / "model_summaries_human_2M.parquet"
if ms.exists():
    s = pd.read_parquet(ms)
    cols = [c for c in ["agent", "p50", "p80", "is_sota", "n_tasks", "release_date"] if c in s.columns]
    print("\nmodel_summaries (P50 horizon):")
    print(s[cols].to_string(index=False))
if mode.get("include_trendline"):
    tp = base / "trendline_params_human_2M.json"
    if tp.exists():
        print("\ntrendline_params:")
        print(json.dumps(json.loads(tp.read_text()), indent=2)[:2000])
    out = Path("/home/fedotova/mth-horizon-pipeline/analysis/figures/out")
    print("\nhorizon figures:")
    for p in sorted(out.glob("trendline_p50_runs_human_2M*")):
        print(" ", p)
else:
    print("\n(no trendline — horizon_only mode)")
PY
