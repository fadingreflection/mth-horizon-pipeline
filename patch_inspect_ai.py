#!/usr/bin/env python3
"""
Скрипт патчинга inspect_ai/agent/_react.py для автоматического извлечения XML tool calls
из ответов GigaChat / LLM с поддержкой reasoning и text содержимого.
"""

import sys
from pathlib import Path

PATCH_MARKER = "_extract_xml_tool_calls_from_message"

PATCH_CODE = '''

def _extract_xml_tool_calls_from_message(msg: ChatMessageAssistant) -> list[ToolCall]:
    if not isinstance(msg, ChatMessageAssistant) or msg.tool_calls:
        return []

    texts = []
    if isinstance(msg.content, str):
        texts.append(msg.content)
    elif isinstance(msg.content, list):
        for part in msg.content:
            if isinstance(part, ContentReasoning):
                if part.reasoning:
                    texts.append(part.reasoning)
            elif isinstance(part, ContentText):
                if part.text:
                    texts.append(part.text)
            elif hasattr(part, "reasoning") and getattr(part, "reasoning", None):
                texts.append(getattr(part, "reasoning"))
            elif hasattr(part, "text") and getattr(part, "text", None):
                texts.append(getattr(part, "text"))

    full_text = "\\n".join(texts)
    if not full_text or "<invoke" not in full_text:
        return []

    tool_calls = []
    invokes = re.findall(r'<invoke\\s+name=["\\\']([^"\\\']+)["\\\'][^>]*>(.*?)</invoke>', full_text, re.DOTALL)
    for idx, (name, body) in enumerate(invokes):
        func_name = "bash" if name in ("shell", "terminal") else name
        args = {}
        params = re.findall(r'<parameter\\s+name=["\\\']([^"\\\']+)["\\\'][^>]*>(.*?)</parameter>', body, re.DOTALL)
        for p_name, p_val in params:
            args[p_name] = p_val.strip()

        if not args:
            cmd_match = re.search(r'<command>(.*?)</command>', body, re.DOTALL)
            ans_match = re.search(r'<answer>(.*?)</answer>', body, re.DOTALL)

            if cmd_match:
                args["command"] = cmd_match.group(1).strip()
            elif ans_match:
                if func_name == "submit":
                    args["answer"] = ans_match.group(1).strip()
                else:
                    args["command"] = ans_match.group(1).strip()
            elif body.strip():
                clean_body = re.sub(r'</?(?:command|answer|parameter)[^>]*>', '', body).strip()
                if not clean_body:
                    attr_match = re.search(
                        r'<(\\w+)\\s+[^>]*?(\\w+)=["\\\']([^"\\\']+)["\\\']',
                        body,
                        re.DOTALL,
                    )
                    if attr_match:
                        clean_body = attr_match.group(3).strip()
                if func_name == "submit":
                    args["answer"] = clean_body
                else:
                    args["command"] = clean_body

        tool_calls.append(
            ToolCall(
                id=f"call_xml_{idx}",
                type="function",
                function=func_name,
                arguments=args
            )
        )
    return tool_calls
'''

HOOK_CODE = '''            # no retry, we are done
            if output.message and not output.message.tool_calls:
                xml_calls = _extract_xml_tool_calls_from_message(output.message)
                if xml_calls:
                    output.message.tool_calls = xml_calls
'''

def main():
    import inspect_ai.agent._react as react_mod
    target_file = Path(react_mod.__file__)

    content = target_file.read_text(encoding="utf-8")

    if PATCH_MARKER in content:
        print(f"[OK] Патч inspect_ai уже применен ({target_file})")
        return

    # Добавляем функцию извлечения перед _model_generate
    if "def _model_generate(" not in content:
        print(f"[ERROR] Не найдена точка входа 'def _model_generate(' в {target_file}")
        sys.exit(1)

    content = content.replace("def _model_generate(", PATCH_CODE + "\ndef _model_generate(")

    old_hook_target = "            # no retry, we are done\n"
    if old_hook_target not in content:
        print(f"[ERROR] Не найден блок '# no retry, we are done' в {target_file}")
        sys.exit(1)

    content = content.replace(old_hook_target, HOOK_CODE)

    target_file.write_text(content, encoding="utf-8")
    print(f"[SUCCESS] Успешно пропатчен {target_file}")

if __name__ == "__main__":
    main()
