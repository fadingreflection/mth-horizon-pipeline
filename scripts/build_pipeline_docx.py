#!/usr/bin/env python3
"""Convert pipeline instruction markdown to .docx (stdlib only)."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

REPO = Path(__file__).resolve().parents[1]
MD_PATH = REPO / "CUSTOM_EVAL_PIPELINE_FULL.md"
OUT_PATH = REPO / "CUSTOM_EVAL_PIPELINE.docx"

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

INSPECT_EVALS_INTRO = """# Полная инструкция: inspect_evals → time horizon (P50)

Репозитории:
- **inspect_evals** — запуск модели на CyberGym, получение `.eval` логов
- **cyber-task-horizons-data** — ingest логов, IRT logistic regression, P50 и trendline

Базовый путь: `/home/afedotova/mth_pipeline`

---

## Часть I. inspect_evals: подготовка и запуск CyberGym

### I.1. Установка окружения

Рекомендуется Python 3.11–3.12.

```bash
cd /home/afedotova/mth_pipeline/inspect_evals
uv sync
source .venv/bin/activate
```

Альтернатива без активации venv: префикс `uv run` перед каждой командой `inspect`.

### I.2. Данные CyberGym (tasks)

Eval читает задачи из каталога `src/inspect_evals/cybergym/tasks`.

**Вариант A — symlink на локальный датасет (рекомендуется):**

```bash
ln -s /path/to/cybergym_data/data \\
  /home/afedotova/mth_pipeline/inspect_evals/src/inspect_evals/cybergym/tasks
```

В текущем checkout symlink указывает на локальный набор (11 ARVO-задач). Проверка:

```bash
ls src/inspect_evals/cybergym/tasks/arvo/1065/description.txt
```

**Вариант B — скачать с Hugging Face** (полный датасет ~236 GB; для подмножества укажите `eval_names`).

### I.3. API-ключи провайдера модели

Для OpenRouter (пример DeepSeek V4 Flash):

```bash
export OPENROUTER_API_KEY="sk-or-..."
```

Для OpenAI: `OPENAI_API_KEY`. Inspect подхватывает стандартные переменные провайдера.

### I.4. Запуск eval на CyberGym

Формат sample id: `cybergym_arvo_1065 (level1)` — в CLI без скобок: `cybergym_arvo_1065`.

**Базовый пример (react_solver по умолчанию):**

```bash
cd /home/afedotova/mth_pipeline/inspect_evals
source .venv/bin/activate

inspect eval inspect_evals/cybergym \\
  --model openrouter/deepseek/deepseek-v4-flash \\
  --max-samples 1 \\
  --time-limit 1200 \\
  -T eval_names='["cybergym_arvo_1065"]'
```

Параметры:
- `--time-limit 1200` — wall-clock лимит **20 минут** на sample (секунды); по истечении sample завершается без успеха
- `--max-samples 1` — один sample за прогон (удобно для отладки)
- `-T eval_names='[...]'` — список задач (JSON-массив в кавычках)

**7 задач с human baseline (локальный symlink, 6 из них в headline IRT):**

```bash
inspect eval inspect_evals/cybergym \\
  --model openrouter/deepseek/deepseek-v4-flash \\
  --time-limit 1200 \\
  --max-samples 1 \\
  -T eval_names='["cybergym_arvo_1065","cybergym_arvo_781","cybergym_arvo_18140","cybergym_arvo_3848","cybergym_arvo_55146","cybergym_arvo_56515","cybergym_arvo_64574"]'
```

**Отключить react-агента** (baseline без поиска уязвимости):

```bash
inspect eval inspect_evals/cybergym \\
  --model openai/gpt-4.1 \\
  --limit 1 \\
  --solver None
```

По умолчанию используется `react_solver` (ReAct + bash/python, до 3 попыток).

### I.5. Где лежат `.eval` логи

После прогона:

```text
inspect_evals/logs/<timestamp>_<model>_<task>.eval
```

Лог — gzip/ZIP-архив с JSON-трейсами Inspect AI (может быть zstd-сжатие).

### I.6. Быстрая проверка лога

```bash
cd /home/afedotova/mth_pipeline/inspect_evals
source .venv/bin/activate

python - <<'PY'
from pathlib import Path
from inspect_ai.log import read_eval_log

p = sorted(Path("logs").glob("*.eval"))[-1]
log = read_eval_log(str(p))
print("file:", p.name)
print("model:", log.eval.model)
print("n_samples:", len(log.samples or []))
for s in log.samples or []:
    sc = None
    if s.scores:
        first = next(iter(s.scores.values()))
        sc = getattr(first, "value", first)
    print(f"  id={s.id} error={s.error is not None} score={sc}")
PY
```

Для CyberGym успех = `reproduced == 1` в dict-скоре. Sample с `error != null` в horizon-пайплайн не попадёт.

### I.7. Типичные проблемы Docker

Ошибка `all predefined address pools have been fully subnetted`:

```bash
docker network prune -f
# при необходимости удалить сети inspect*/cybergym*
```

Держите `--max-samples 1` при отладке. CyberGym поднимает несколько контейнеров на sample (solver, vulnerable, fixed).

---

## Часть II. cyber-task-horizons-data: от `.eval` к P50

"""


def _w(tag: str, text: str = "", **attrs) -> str:
    attr_s = "".join(f' {k}="{v}"' for k, v in attrs.items())
    if text:
        return f"<w:{tag}{attr_s}>{text}</w:{tag}>"
    return f"<w:{tag}{attr_s}/>"


def _run(text: str, *, bold: bool = False, code: bool = False, size: int | None = None) -> str:
    props = []
    if bold:
        props.append(_w("b"))
    if code:
        props.append(_w("rFonts", **{"w:ascii": "Courier New", "w:hAnsi": "Courier New"}))
        props.append(_w("sz", **{"w:val": "20"}))
    elif size:
        props.append(_w("sz", **{"w:val": str(size)}))
    rpr = f"<w:rPr>{''.join(props)}</w:rPr>" if props else ""
    return f"<w:r>{rpr}<w:t xml:space=\"preserve\">{escape(text)}</w:t></w:r>"


def _para(runs: str, style: str | None = None, shading: str | None = None) -> str:
    ppr_parts = []
    if style:
        ppr_parts.append(_w("pStyle", **{"w:val": style}))
    if shading:
        ppr_parts.append(
            f'<w:shd w:val="clear" w:color="auto" w:fill="{shading}"/>'
        )
    ppr = f"<w:pPr>{''.join(ppr_parts)}</w:pPr>" if ppr_parts else ""
    return f"<w:p>{ppr}{runs}</w:p>"


def _heading(text: str, level: int) -> str:
  style = f"Heading{min(level, 3)}"
  return _para(_run(text, bold=True), style=style)


def _parse_inline(text: str) -> str:
    parts: list[str] = []
    i = 0
    while i < len(text):
        if text[i : i + 2] == "**":
            j = text.find("**", i + 2)
            if j != -1:
                parts.append(_run(text[i + 2 : j], bold=True))
                i = j + 2
                continue
        if text[i] == "`":
            j = text.find("`", i + 1)
            if j != -1:
                parts.append(_run(text[i + 1 : j], code=True))
                i = j + 1
                continue
        j = i + 1
        while j < len(text):
            if text[j] == "`" or text[j : j + 2] == "**":
                break
            j += 1
        parts.append(_run(text[i:j]))
        i = j
    return "".join(parts) if parts else _run("")


def _table(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    ncols = max(len(r) for r in rows)
    tbl = [
        '<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/>'
        '<w:tblBorders>'
        '<w:top w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
        '<w:left w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
        '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
        '<w:right w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
        '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
        '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
        "</w:tblBorders></w:tblPr>"
    ]
    for ri, row in enumerate(rows):
        cells = []
        for ci in range(ncols):
            cell_text = row[ci] if ci < len(row) else ""
            cell_xml = (
                "<w:tc><w:tcPr><w:tcW w:w=\"2000\" w:type=\"dxa\"/></w:tcPr>"
                f"<w:p>{_parse_inline(cell_text.strip())}</w:p></w:tc>"
            )
            cells.append(cell_xml)
        tbl.append(f"<w:tr>{''.join(cells)}</w:tr>")
    tbl.append("</w:tbl>")
    return "".join(tbl)


def md_to_body(md: str) -> str:
    lines = md.splitlines()
    body: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]

        if line.strip() == "---":
            i += 1
            continue

        if line.startswith("```"):
            lang = line[3:].strip()
            i += 1
            code_lines: list[str] = []
            while i < len(lines) and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1
            if i < len(lines):
                i += 1
            block = "\n".join(code_lines)
            for cl in block.split("\n"):
                body.append(_para(_run(cl, code=True), shading="F2F2F2"))
            continue

        if line.startswith("|") and "|" in line[1:]:
            table_rows: list[list[str]] = []
            while i < len(lines) and lines[i].startswith("|"):
                row = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(set(c) <= {"-", ":"} for c in row):
                    table_rows.append(row)
                i += 1
            body.append(_table(table_rows))
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            body.append(_heading(title, level))
            i += 1
            continue

        m = re.match(r"^-\s+\[([ xX])\]\s+(.*)$", line)
        if m:
            mark = "☑" if m.group(1).lower() == "x" else "☐"
            body.append(_para(_run(f"{mark} ") + _parse_inline(m.group(2))))
            i += 1
            continue

        m = re.match(r"^-\s+(.*)$", line)
        if m:
            body.append(_para(_run("• ") + _parse_inline(m.group(1))))
            i += 1
            continue

        m = re.match(r"^(\d+)\.\s+(.*)$", line)
        if m:
            body.append(_para(_run(f"{m.group(1)}. ") + _parse_inline(m.group(2))))
            i += 1
            continue

        if line.strip() == "":
            i += 1
            continue

        body.append(_para(_parse_inline(line)))
        i += 1

    return "".join(body)


def build_docx(md_text: str, out_path: Path) -> None:
    body = md_to_body(md_text)
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{W_NS}" xmlns:r="{R_NS}">
  <w:body>
    {body}
    <w:sectPr>
      <w:pgSz w:w="11906" w:h="16838"/>
      <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/>
    </w:sectPr>
  </w:body>
</w:document>"""

    styles_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="{W_NS}">
  <w:style w:type="paragraph" w:styleId="Heading1" w:default="0">
    <w:name w:val="heading 1"/>
    <w:pPr><w:keepNext/><w:spacing w:before="480" w:after="120"/></w:pPr>
    <w:rPr><w:b/><w:sz w:val="32"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading2" w:default="0">
    <w:name w:val="heading 2"/>
    <w:pPr><w:keepNext/><w:spacing w:before="360" w:after="80"/></w:pPr>
    <w:rPr><w:b/><w:sz w:val="28"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading3" w:default="0">
    <w:name w:val="heading 3"/>
    <w:pPr><w:keepNext/><w:spacing w:before="240" w:after="60"/></w:pPr>
    <w:rPr><w:b/><w:sz w:val="24"/></w:rPr>
  </w:style>
</w:styles>"""

    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""

    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

    doc_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/_rels/document.xml.rels", doc_rels)
        zf.writestr("word/styles.xml", styles_xml)


def main() -> None:
    base_md = (REPO / "CUSTOM_EVAL_PIPELINE.md").read_text(encoding="utf-8")
    # Drop duplicate title block from base; Part II starts at "## 0."
    base_md = re.sub(
        r"^# Инструкция:.*?\n\n.*?\n\n.*?\n\n.*?\n\n---\n\n",
        "",
        base_md,
        count=1,
        flags=re.DOTALL,
    )
    # Renumber main sections for Part II flow
    base_md = base_md.replace("## 0. ", "## II.0. ")
    base_md = base_md.replace("## 1. ", "## II.1. ")
    base_md = base_md.replace("## 2. ", "## II.2. ")
    base_md = base_md.replace("## 3. ", "## II.3. ")
    base_md = base_md.replace("## 4. ", "## II.4. ")
    base_md = base_md.replace("## 5. ", "## II.5. ")
    base_md = base_md.replace("## 6. ", "## II.6. ")
    base_md = base_md.replace("## Приложение A.", "## Приложение A.")

    full_md = INSPECT_EVALS_INTRO + base_md
    MD_PATH.write_text(full_md, encoding="utf-8")
    build_docx(full_md, OUT_PATH)
    print(f"Wrote {OUT_PATH} ({OUT_PATH.stat().st_size // 1024} KB)")
    print(f"Source markdown: {MD_PATH}")


if __name__ == "__main__":
    main()
