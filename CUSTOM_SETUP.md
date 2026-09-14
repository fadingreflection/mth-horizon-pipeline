# Custom horizon pipeline notes

Snapshot of `cyber-task-horizons-data` with local customizations for time-horizon (P50) on custom Inspect `.eval` logs.

## Included
- Code/config for custom campaign + `horizon_only` mode
- Runbook (`CUSTOM_EVAL_PIPELINE*`)
- `data/eval_logs/eval-set-my-custom-model/`
- `analysis/figures/data_horizon/`

## Excluded
- Upstream Git LFS `data/human/eval_logs/**` session archives
- Other paper `data/eval_logs/eval-set-*`
- `.venv`, files >45MB

## Quick start
```bash
uv sync
export PYTHONPATH="$PWD"
FORCE_PREPARE=1 FORCE_TRENDLINE=0 ./run_custom_pipeline.sh
```
