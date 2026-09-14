"""Stage 1: Prepare pipeline data from .eval cache + human snapshot.

Loads model evaluation results from cached .eval files, builds
best_available_times from the human snapshot, and produces the two
canonical pipeline tables:

  - model_runs.parquet: evaluation results only (no difficulty column)
  - task_difficulties.parquet: one row per task, explicit columns per
    difficulty source (completion, estimate, first-blood, model estimate)

Also produces best_available_times.json. Legacy models (GPT-2, GPT-3, GPT-3.5) are
merged from the June 2025 study.
"""

import json
import sys
from pathlib import Path

import pandas as pd

_NOTEBOOKS_DIR = Path(__file__).resolve().parents[2]
# analysis/ — for `import lib.*`; repo root — for `import analysis.config`
if str(_NOTEBOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_NOTEBOOKS_DIR))
_REPO_ROOT = str(_NOTEBOOKS_DIR.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from lib.corrections import KNOWN_OUTLIERS, TIMING_CORRECTIONS  # noqa: E402
from lib.data import (  # noqa: E402
    build_best_available_times,
    build_task_difficulties,
    load_cybench_first_blood,
    load_model_time_estimates,
)
from lib.eval_sets import SMALL_QWEN_EVAL_SETS  # noqa: E402
from lib.corrections import EXCLUDED_SESSIONS  # noqa: E402
from lib.outliers import OutlierRegistry  # noqa: E402
from lib.results import load_campaign_runs, load_legacy_runs  # noqa: E402

# Legacy GPT-2/3/3.5 from June 2025 study — time-axis anchors for trendline.
# Loaded only in "full" mode (campaign has enough tasks). In "horizon_only"
# mode (sparse custom .eval) they are skipped: we fit P50 for the current
# model only and do not build a multi-model trendline.
LEGACY_MODELS = [
    {"alias_filter": "GPT 2", "agent": "openai/gpt2-xl", "alias": "GPT-2"},
    {"alias_filter": "GPT 3", "agent": "openai/davinci-002", "alias": "GPT-3"},
    {"alias_filter": "GPT 3.5", "agent": "openai/gpt-3.5-turbo", "alias": "GPT-3.5"},
]

# Below this many unique campaign task_ids → horizon_only (no legacy, no trendline).
# At/above → full mode (legacy anchors + trendline stages).
TRENDLINE_MIN_CAMPAIGN_TASKS = 50

# Custom-only campaign list for this checkout.
CAMPAIGNS = [
    {
        "eval_sets": SMALL_QWEN_EVAL_SETS,
        "agent": "together/Qwen/Small-Qwen",
        "alias": "Small Qwen",
    },
]


def _build_task_bench(snapshot: dict) -> dict[str, str]:
    """Build task_id -> benchmark lookup from all snapshot sources."""
    task_bench = {}
    for key in ("completions", "estimations", "passes", "fails", "censored"):
        for session in snapshot.get(key, []):
            tid = session.get("task_id", "")
            bench = (
                tid.split("_")[0]
                if "_" in tid
                else tid.split("/")[0]
                if "/" in tid
                else ""
            )
            if "benchmark" in session:
                bench = session["benchmark"]
            if tid and bench:
                task_bench[tid] = bench
    return task_bench


def _load_cybench_first_blood() -> dict[str, float]:
    """Load CyBench first-blood competition times.

    Delegates to lib.data.load_cybench_first_blood() - the single source
    of truth for first-blood loading.
    """
    return load_cybench_first_blood()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Prepare runs DataFrames")
    parser.add_argument("--human-snapshot", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    with open(args.human_snapshot) as f:
        snapshot = json.load(f)

    registry = OutlierRegistry(KNOWN_OUTLIERS)
    task_bench = _build_task_bench(snapshot)
    fb_minutes = _load_cybench_first_blood()

    # Assert excluded sessions haven't leaked into censored/fails data.
    # EXCLUDED_SESSIONS filtering is applied in api.py to completions and
    # estimations, but censored observations are constructed separately.
    excluded_sids = set(EXCLUDED_SESSIONS.keys())
    for key in ("fails", "censored"):
        for session in snapshot.get(key, []):
            sid = session.get("session_id")
            if sid and sid in excluded_sids:
                raise ValueError(
                    f"Excluded session {sid} leaked into snapshot['{key}']: "
                    f"{EXCLUDED_SESSIONS[sid]}"
                )

    best_available_times = build_best_available_times(
        completions=snapshot["passes"],
        censored=snapshot["fails"] + snapshot["censored"],
        first_blood_minutes=fb_minutes,
        estimations=snapshot["estimations"],
        timing_corrections=TIMING_CORRECTIONS,
        task_bench=task_bench,
        excluded_task_ids=registry.excluded_task_ids,
    )

    # Load all model campaigns
    all_runs = []

    for cfg in CAMPAIGNS:
        runs = load_campaign_runs(
            cfg["eval_sets"], agent=cfg["agent"], alias=cfg["alias"]
        )
        if runs.empty:
            print(f"  {cfg['alias']}: no data, skipping")
            continue
        all_runs.append(runs)

    # Mode selection: enough campaign tasks → full (legacy + trendline);
    # sparse custom eval → horizon_only (current model P50 only).
    current_task_ids = set()
    for df in all_runs:
        current_task_ids.update(df["task_id"].astype(str))
    n_campaign_tasks = len(current_task_ids)
    include_trendline = n_campaign_tasks >= TRENDLINE_MIN_CAMPAIGN_TASKS
    mode = "full" if include_trendline else "horizon_only"
    campaign_aliases = sorted(
        {
            str(a)
            for df in all_runs
            if not df.empty and "alias" in df.columns
            for a in df["alias"].unique()
        }
    )

    if mode == "horizon_only":
        print(
            f"  mode=horizon_only: campaign has {n_campaign_tasks} task_id(s) "
            f"(<{TRENDLINE_MIN_CAMPAIGN_TASKS}); skipping legacy GPT anchors "
            "and trendline — will fit P50 for current model only"
        )
    else:
        print(
            f"  mode=full: campaign has {n_campaign_tasks} task_id(s) "
            f"(>={TRENDLINE_MIN_CAMPAIGN_TASKS}); loading legacy GPT with "
            "intersection filter for trendline anchors"
        )
        for cfg in LEGACY_MODELS:
            runs = load_legacy_runs(
                alias_filter=cfg["alias_filter"],
                agent=cfg["agent"],
                alias=cfg["alias"],
            )
            if runs.empty:
                continue
            before = len(runs)
            runs = runs[runs["task_id"].astype(str).isin(current_task_ids)]
            dropped = before - len(runs)
            if dropped:
                print(f"  {cfg['alias']}: dropped {dropped} legacy-only tasks")
            if not runs.empty:
                all_runs.append(runs)

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    mode_info = {
        "mode": mode,
        "include_trendline": include_trendline,
        "n_campaign_tasks": n_campaign_tasks,
        "trendline_min_campaign_tasks": TRENDLINE_MIN_CAMPAIGN_TASKS,
        "campaign_aliases": campaign_aliases,
    }
    with open(out / "horizon_mode.json", "w") as f:
        json.dump(mode_info, f, indent=2)
    print(f"  wrote horizon_mode.json: {mode_info}")

    bat_serializable = {
        tid: {"minutes": m, "source": s} for tid, (m, s) in best_available_times.items()
    }
    with open(out / "best_available_times.json", "w") as f:
        json.dump(bat_serializable, f, indent=2)

    # --- New pipeline tables: explicit difficulty sources ---

    # model_runs.parquet: evaluation results only, no difficulty column
    runs_concat = pd.concat(all_runs, ignore_index=True)
    model_runs_cols = [
        "task_id",
        "task_family",
        "agent",
        "alias",
        "score_binarized",
        "total_tokens",
    ]
    # Keep only columns that exist
    model_runs_cols = [c for c in model_runs_cols if c in runs_concat.columns]
    runs_concat[model_runs_cols].to_parquet(out / "model_runs.parquet")

    # task_difficulties.parquet: one row per task, one column per source
    model_estimates = load_model_time_estimates()

    # Build task_family lookup from the runs data
    task_fam = (
        runs_concat.drop_duplicates("task_id")
        .set_index("task_id")["task_family"]
        .to_dict()
    )

    task_diff = build_task_difficulties(
        best_available_times=best_available_times,
        snapshot=snapshot,
        first_blood_minutes=fb_minutes,
        timing_corrections=TIMING_CORRECTIONS,
        model_estimates=model_estimates,
        task_families=task_fam,
    )
    task_diff.to_parquet(out / "task_difficulties.parquet", index=False)

    print(f"\nSaved to {out}:")
    print(f"  model_runs.parquet: {len(runs_concat)} rows")
    print(f"  task_difficulties.parquet: {len(task_diff)} tasks")
    print(f"  best_available_times.json: {len(best_available_times)} tasks")


if __name__ == "__main__":
    main()
