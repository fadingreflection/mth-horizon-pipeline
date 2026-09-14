"""Eval-set ID constants for model evaluation campaigns.

Each dict maps benchmark name to a list of Hawk/Inspect eval-set IDs.
Multiple IDs per benchmark means retry passes — results.load_campaign_runs
processes them in order, with later results overriding earlier per task_id.

Custom / local campaigns live here. Paper campaign dicts are omitted so that
prepare_runs imports only what this checkout actually runs.
"""

# ---------------------------------------------------------------------------
# Small Qwen — local custom campaign (cybergym only)
# Logs: data/eval_logs/eval-set-my-custom-model/*.eval
# ---------------------------------------------------------------------------
SMALL_QWEN_EVAL_SETS = {
    "cybergym": [
        "eval-set-my-custom-model",
    ],
}
