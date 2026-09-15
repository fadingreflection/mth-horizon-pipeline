# Инструкция по запуску бенчмарков и расчету горизонта (Inspect Evals + CyberGym)

Данный документ содержит актуальные инструкции по запуску бенчмарков CyberGym для различных моделей (обычные модели через API/OpenRouter и GigaChat через прокси) и по мгновенному расчету метрик **P50/P80 горизонта**.

---

## 1. Запуск стандартных моделей (OpenRouter, OpenAI, Claude)

Для запуска стандартных моделей с нативным вызовом функций (function calling) прокси не требуется. Интеграция выполняется напрямую через `inspect eval`.

### Переменные окружения
Убедитесь, что нужные API ключи добавлены в `.env` файл в корне `/home/fedotova/inspect_evals`:
```env
OPENROUTER_API_KEY=sk-or-v1-...
OPENAI_API_KEY=sk-...
```

### Пример запуска
```bash
cd /home/fedotova/inspect_evals

# Запуск одной задачи (например, cybergym_arvo_1065) через OpenRouter:
inspect eval src/inspect_evals/cybergym \
  --model openrouter/anthropic/claude-3.5-sonnet \
  --time-limit 1200 \
  --max-connections 1 \
  -T eval_names='["cybergym_arvo_1065"]'
```

---

## 2. Запуск пайплайна GigaChat (GigaChat Ultra 3.5 через `gpt2giga`)

Для работы с GigaChat Ultra 3.5 используется локальный прокси-сервер `gpt2giga`, транслирующий вызовы моделей и функций.

### Шаг 1. Проверка и запуск прокси `gpt2giga`
Проверьте, работает ли прокси на порту 8090:
```bash
curl -s http://127.0.0.1:8090/health
```
Если прокси не запущен, стартуйте его:
```bash
cd /opt/gpt2giga && /opt/gpt2giga/venv/bin/gpt2giga &
```

### Шаг 2. Запуск прогона бенчмарка
В корне `/home/fedotova/inspect_evals` подготовлен автоматический скрипт `run_eval.sh`:
```bash
cd /home/fedotova/inspect_evals
./run_eval.sh
```

### Особенности интеграции GigaChat:
1. **Системный промпт (`src/inspect_evals/cybergym/react_solver.py`):** содержит явное требование не выводить сырые XML-теги в текст или блоки мыслей (reasoning).
2. **Патч Inspect AI (`inspect_ai/agent/_react.py`):** встроен автоматический fallback-парсер XML (`_extract_xml_tool_calls_from_message`). Если GigaChat помещает вызовы функций в формат `<invoke name="...">`, они перехватываются и переводятся в исполняемые вызовы `bash` и `python`.

---

## 3. Быстрый расчет горизонта (P50/P80)

Для расчета горизонта на основе сохраненных `.eval` логов используется утилита `compute_horizon.py`.

### Запуск расчета
```bash
/home/fedotova/mth-horizon-pipeline/.venv/bin/python3 /home/fedotova/inspect_evals/compute_horizon.py
```

### Опциональные параметры
- `--logs-dir`: путь к каталогу с логами (по умолчанию `/home/fedotova/inspect_evals/logs`).
- `--alias`: имя модели для отображения в отчете (по умолчанию `"GigaChat Ultra 3.5"`).

Пример запуска для произвольного каталога:
```bash
/home/fedotova/mth-horizon-pipeline/.venv/bin/python3 /home/fedotova/inspect_evals/compute_horizon.py \
  --logs-dir /home/fedotova/inspect_evals/logs \
  --alias "Claude 3.5 Sonnet"
```

### Как происходит расчет:
1. Скрипт сканирует `.eval` файлы и извлекает бинаризованные оценки задач (`reproduced == 1` или `new_vulnerability == 1`).
2. По каждой уникальной задаче CyberGym берется наилучший результат среди всех прогонов (`max score`).
3. На основе длительности решения людьми из `task_difficulties.parquet` строится IRT-логистическая регрессия (METR) с регуляризацией.
4. Выводится итоговая таблица результатов по задачам и расчитанные значения **P50** и **P80** горизонта.
