#!/usr/bin/env python3
"""
Скрипт быстрого расчета горизонта (P50/P80) по имеющимся .eval логам.

Использование:
  python compute_horizon.py [--logs-dir /path/to/logs] [--alias "GigaChat Ultra 3.5"]
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

REPO_PIPELINE = Path("/home/fedotova/mth-horizon-pipeline")
sys.path.insert(0, str(REPO_PIPELINE))
sys.path.insert(0, str(REPO_PIPELINE / "analysis"))

from horizon.wrangle.logistic import agent_regression
from lib.constants import DEFAULT_REGULARIZATION
from lib.corrections import compute_weights
from lib.results import _extract_scores_from_eval, _normalize_cybergym_task_id


def main():
    parser = argparse.ArgumentParser(description="Расчет P50/P80 горизонта по .eval логам")
    parser.add_argument(
        "--logs-dir",
        default="/home/fedotova/inspect_evals/logs",
        help="Каталог с .eval логами",
    )
    parser.add_argument(
        "--alias",
        default="GigaChat Ultra 3.5",
        help="Название модели для отчетов",
    )
    args = parser.parse_args()

    search_path = Path(args.logs_dir)
    if search_path.is_file():
        eval_files = [search_path]
    elif search_path.is_dir():
        eval_files = list(search_path.glob("**/*.eval"))
    else:
        eval_files = list(Path("/home/fedotova/inspect_evals").glob("**/*.eval"))

    if not eval_files:
        print(f"ОШИБКА: .eval файлы не найдены по пути {args.logs_dir}")
        sys.exit(1)

    task_scores: dict[str, float] = {}
    task_tokens: dict[str, int] = {}

    for ef in sorted(eval_files):
        if "cybergym" not in ef.name:
            continue
        entries = _extract_scores_from_eval(ef, "cybergym")
        for entry in entries:
            tid = _normalize_cybergym_task_id(str(entry["task_id"]))
            score = float(entry["score_binarized"])
            tokens = int(entry.get("total_tokens", 0))
            if tid not in task_scores:
                task_scores[tid] = score
                task_tokens[tid] = tokens
            else:
                task_scores[tid] = max(task_scores[tid], score)
                task_tokens[tid] = max(task_tokens[tid], tokens)

    if not task_scores:
        print("Не найдено завершенных результатов вычислений в логах.")
        sys.exit(0)

    rows = []
    for tid, score in task_scores.items():
        rows.append(
            {
                "task_id": tid,
                "task_family": "cybergym",
                "agent": args.alias,
                "alias": args.alias,
                "score_binarized": score,
                "total_tokens": task_tokens[tid],
            }
        )

    mr_df = pd.DataFrame(rows)

    diff_path = REPO_PIPELINE / "analysis/figures/data/task_difficulties.parquet"
    if not diff_path.exists():
        print(f"ОШИБКА: Файл сложностей {diff_path} не найден.")
        sys.exit(1)

    diff_orig = pd.read_parquet(diff_path)
    merged = mr_df.merge(
        diff_orig[["task_id", "best_available_minutes"]], on="task_id", how="left"
    )
    merged["human_minutes"] = merged["best_available_minutes"].astype(float)
    merged = compute_weights(merged)
    merged["agent"] = args.alias

    print("=" * 68)
    print(f"          РАСЧЕТ ГОРИЗОНТА: {args.alias.upper()}")
    print("=" * 68)

    merged["difficulty_hours"] = merged["human_minutes"] / 60.0
    sorted_df = merged.sort_values("human_minutes")

    print("\nТаблица результатов по задачам CyberGym:")
    print(
        f"{'Task ID':<12} | {'Status':<7} | {'Difficulty (min)':<18} | {'Difficulty (hrs)':<16} | {'Tokens':<10}"
    )
    print("-" * 72)
    for _, r in sorted_df.iterrows():
        status = "PASS (1)" if r["score_binarized"] == 1 else "FAIL (0)"
        print(
            f"{r['task_id']:<12} | {status:<7} | {r['human_minutes']:<18.1f} | {r['difficulty_hours']:<16.2f} | {r['total_tokens']:<10}"
        )

    pass_count = int(sum(merged["score_binarized"] == 1))
    fail_count = int(sum(merged["score_binarized"] == 0))
    n_tasks = len(merged)

    print("-" * 68)
    print(f" Модель                      : {args.alias}")
    print(f" Всеми оценено задач (n)    : {n_tasks}")
    print(f" Успешных решений (PASS)    : {pass_count}")
    print(f" Неуспешных решений (FAIL)  : {fail_count}")

    if pass_count > 0 and fail_count > 0:
        regression = agent_regression(
            x=merged["human_minutes"].values.astype(float),
            y=merged["score_binarized"].values.astype(int),
            weights=merged["invsqrt_task_weight"].values.astype(float),
            agent_name=args.alias,
            regularization=DEFAULT_REGULARIZATION,
            success_percents=[50, 80],
            confidence_level=0.95,
            include_empirical_rates=False,
        )
        res = regression.to_dict()
        p50 = float(res.get("p50", 0.0))
        p80 = float(res.get("p80", 0.0))
        print(f" P50 Horizon                 : {p50:.2f} минут ({p50/60:.2f} часов)")
        print(f" P80 Horizon                 : {p80:.2f} минут ({p80/60:.2f} часов)")
    elif pass_count == 0:
        print(" P50 Horizon                 : 0.00 минут (все задачи 0)")
        print(" P80 Horizon                 : 0.00 минут")
    else:
        print(" P50 Horizon                 : не ограничено (все задачи 1)")

    print("=" * 68)


if __name__ == "__main__":
    main()
