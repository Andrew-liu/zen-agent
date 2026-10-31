# zen-agent

一个只依赖 `bash` 工具的极简软件工程 Agent，第一版功能对齐 [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent)。

## 安装与运行

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

export DEEPSEEK_API_KEY=sk-xxx        # 或 ZEN_API_KEY / OPENAI_API_KEY，也可写入 ~/.config/zen-agent/.env
zen -t "修复 foo.py 里的 bug"           # 默认 confirm 模式
zen -y -m gpt-4o -t "..."               # yolo 模式，指定模型
zen --environment-class docker -c mini.yaml -c environment.image=python:3.12 -t "..."
```

模型默认走 OpenAI 兼容接口：`OPENAI_BASE_URL`（默认 `https://api.deepseek.com`）、`ZEN_MODEL_NAME`（默认 `deepseek-v4-flash`）。

## 对齐范围（v0.1）

| 能力 | 状态 |
| --- | --- |
| 线性消息历史 + `query -> execute -> observe` 循环 | 已实现 |
| 仅 `bash` 一个工具，每条命令独立 subshell | 已实现 |
| 提交协议：`echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT` | 已实现 |
| 异常驱动控制流（Submitted / LimitsExceeded / TimeExceeded / FormatError） | 已实现 |
| 步数 / 费用 / 墙钟时间限制，连续格式错误退出 | 已实现 |
| Jinja2 模板（system / instance / observation / format_error） | 已实现 |
| 交互模式 human / confirm / yolo，`/y /c /u /m /h`，白名单，Ctrl+C 插话，退出前可追加任务 | 已实现 |
| Local 与 Docker 环境，超时杀进程组 | 已实现 |
| YAML 配置 + `a.b.c=v` 覆盖，递归合并 | 已实现 |
| 轨迹 JSON 每步落盘 | 已实现 |
| OpenAI 兼容模型 + 重试 + 按 token 计费 | 已实现 |
| 确定性模型（测试 / dry run） | 已实现 |

## 暂未实现（后续版本）

- 多模型后端：litellm / Anthropic / OpenRouter / Portkey，以及 text-based 和 Responses API 模式
- 提示缓存（Anthropic cache_control）
- SWE-bench 批量评测、`mini-extra` 工具集（inspector、config 向导）
- Singularity / Bubblewrap / Modal / SWE-ReX 环境
- Textual 轨迹浏览器、多模态内容

## 测试

```bash
pytest -q
```

## 旧版

`main.py` / `file.py` 是早期的 read/list/edit 三工具原型，保留作参考，新入口为 `zen` 或 `python -m zenagent`。

## 致谢

架构设计与默认提示模板（`zenagent/config/mini.yaml`）参考自 [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent)，原项目以 MIT 许可发布：Copyright (c) 2025 Kilian A. Lieret and Carlos E. Jimenez。
