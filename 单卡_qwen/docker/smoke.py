"""Starter API acceptance using the actual SDK. Further business tests are in the plan."""
import argparse
import json
import os
import time
from pathlib import Path

from openai import APIStatusError, OpenAI


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args()
    key = Path(os.environ["TEST_API_KEY_FILE"]).read_text().strip()
    base = os.environ["TEST_BASE_URL"]
    model = os.environ["TEST_MODEL"]
    client = OpenAI(base_url=base, api_key=key, timeout=120.0, max_retries=0)
    extra = {"chat_template_kwargs": {"enable_thinking": False}}
    messages = [{"role": "user", "content": "19乘23等于多少？只输出整数，不要解释。"}]
    checks = []

    def check(condition, name):
        if not condition:
            raise AssertionError(name)
        checks.append(name)

    for i in range(args.repeat):
        result = client.chat.completions.create(
            model=model, messages=messages, max_tokens=128, temperature=0, extra_body=extra
        )
        check((result.choices[0].message.content or "").strip() == "437", f"answer_{i}")
        check(result.usage is not None and result.usage.completion_tokens > 0, f"usage_{i}")

    start = time.perf_counter()
    content, usage, finish, first = [], None, None, None
    stream = client.chat.completions.create(
        model=model, messages=messages, max_tokens=128, temperature=0, extra_body=extra,
        stream=True, stream_options={"include_usage": True},
    )
    with stream:
        for chunk in stream:
            if chunk.usage:
                usage = chunk.usage.model_dump()
            for choice in chunk.choices:
                if choice.delta.content:
                    if first is None:
                        first = time.perf_counter()
                    content.append(choice.delta.content)
                if choice.finish_reason:
                    finish = choice.finish_reason
    check("".join(content).strip() == "437", "stream_answer")
    check(usage is not None and usage["completion_tokens"] > 0, "stream_final_usage")
    check(finish == "stop", "stream_finished")

    wrong = OpenAI(base_url=base, api_key="invalid-smoke-key", timeout=30, max_retries=0)
    try:
        wrong.chat.completions.create(model=model, messages=messages, max_tokens=8, extra_body=extra)
    except APIStatusError as exc:
        check(exc.status_code in (401, 403), "authentication")
    else:
        raise AssertionError("Invalid API key accepted")

    tools = [{"type": "function", "function": {
        "name": "get_temperature", "description": "查询城市当前摄氏温度",
        "parameters": {"type": "object", "properties": {"city": {"type": "string"}},
                       "required": ["city"], "additionalProperties": False},
    }}]
    tool_messages = [{"role": "user", "content": "请调用 get_temperature 查询杭州的温度，再告诉我温度数字。"}]
    response = client.chat.completions.create(
        model=model, messages=tool_messages, tools=tools, tool_choice="auto",
        max_tokens=512, temperature=0, extra_body=extra,
    )
    message = response.choices[0].message
    calls = message.tool_calls or []
    check(len(calls) == 1 and calls[0].function.name == "get_temperature", "tool_name")
    arguments = json.loads(calls[0].function.arguments)
    check("杭州" in arguments.get("city", "") or "hangzhou" in arguments.get("city", "").lower(), "tool_arguments")
    # Send only standard Chat Completions assistant fields back to the service.
    tool_messages += [{"role": "assistant", "content": message.content,
                       "tool_calls": [call.model_dump() for call in calls]},
                      {"role": "tool", "tool_call_id": calls[0].id,
                       "content": '{"city":"杭州","temperature_c":17}'}]
    final = client.chat.completions.create(
        model=model, messages=tool_messages, tools=tools, tool_choice="none",
        max_tokens=128, temperature=0, extra_body=extra,
    )
    check("17" in (final.choices[0].message.content or ""), "tool_roundtrip")
    print(json.dumps({"base_url": base, "model": model, "passed": checks,
                      "stream_content_ttft_s": first - start, "stream_usage": usage}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
