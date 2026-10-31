#!/usr/bin/env python3
"""zen-agent: 使用 OpenAI 原生 Function Calling 的最小编码 Agent。

核心流程：用户问题 -> 调用 LLM（带 tools）-> 执行 tool_calls
-> 用 role=tool 回填结果 -> 再次调用 LLM -> 最终答案。
"""

import json
import os

from openai import OpenAI

from file import TOOL_REGISTRY, TOOL_SCHEMAS

YOU_COLOR = "\u001b[94m"
ASSISTANT_COLOR = "\u001b[93m"
RESET_COLOR = "\u001b[0m"

SYSTEM_PROMPT = (
    "You are a coding assistant whose goal is to help solve coding tasks. "
    "You can read files, list directories, and edit files through the provided tools. "
    "When a request needs multiple independent tool calls, emit them together in one "
    "response. After receiving all tool results, continue the task or answer clearly."
)


def execute_tool(name: str, arguments_json: str) -> dict:
    """解析模型给出的参数并执行对应工具；错误也作为观察结果返回模型。"""
    try:
        arguments = json.loads(arguments_json or "{}")
        if not isinstance(arguments, dict):
            raise ValueError("工具参数必须是 JSON object")
        function = TOOL_REGISTRY.get(name)
        if function is None:
            raise ValueError(f"未知工具: {name}")
        return function(**arguments)
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def execute_llm_call(client: OpenAI, model: str, messages: list[dict]):
    """调用一次模型，返回原始 message 对象（可能包含 tool_calls）。"""
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=TOOL_SCHEMAS,
        tool_choice="auto",
    )
    return response.choices[0].message


def run_coding_agent_loop(client: OpenAI, model: str, max_steps: int = 8):
    conversation: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]


    while True:

        try:
            user_input = input(f"{YOU_COLOR}You{RESET_COLOR}: ")
        except (KeyboardInterrupt, EOFError):
            print()
            break

        user_input = user_input.strip()
        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit"}:
            break

        conversation.append({"role": "user", "content": user_input})

        iter_num = 0

        for _ in range(max_steps):
            iter_num += 1
            print(f"第{iter_num}轮调用")

            message = execute_llm_call(client, model, conversation)
            tool_calls = message.tool_calls or []
            print(f"  [cotent] {message.content}")
            print(f"  [toolcall] {tool_calls}")

            # 保存 assistant 消息（含 tool_calls），供下一轮请求引用。
            assistant_msg: dict = {
                "role": "assistant",
                "content": message.content or "",
            }
            if tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    }
                    for call in tool_calls
                ]
            conversation.append(assistant_msg)

            if not tool_calls:
                print(f"{ASSISTANT_COLOR}Assistant{RESET_COLOR}: {message.content}")
                break

            # 执行每个工具调用，用 role=tool + tool_call_id 精确回填结果。
            for call in tool_calls:
                name = call.function.name
                result = execute_tool(name, call.function.arguments)
                print(f"  [tool] {name}({call.function.arguments}) -> {result}")
                conversation.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })
        else:
            print(f"{ASSISTANT_COLOR}Assistant{RESET_COLOR}: 达到最大步数 {max_steps}，已停止。")


def main():
    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("请先设置环境变量 DEEPSEEK_API_KEY 或 OPENAI_API_KEY")

    client = OpenAI(
        api_key=api_key,
        base_url=os.getenv("OPENAI_BASE_URL") or "https://api.deepseek.com",
    )
    model = os.getenv("OPENAI_MODEL", "deepseek-v4-flash")
    run_coding_agent_loop(client, model)


if __name__ == "__main__":
    main()
