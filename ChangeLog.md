# ChangeLog

## v0.1.0（2026-10-31）

首个可用版本，核心功能对齐 [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent)。

- 重写为 `zenagent` 包：Agent、Model、Environment 三个组件，只保留 `bash` 一个工具
- 线性消息历史与 `query → execute → observe` 循环，异常驱动控制流
- 提交协议 `echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT`，步数、费用、墙钟时间与连续格式错误限制
- 交互模式 human / confirm / yolo，斜杠命令、命令白名单、Ctrl+C 插话、结束前追加任务
- 本地与 Docker 两种执行环境，超时终止整个进程组
- OpenAI 兼容模型接口，自动重试，按 token 计费
- YAML 配置与 `a.b.c=value` 命令行覆盖，轨迹 JSON 每步落盘
- 确定性模型与 10 个单元测试
- 早期的 read / list / edit 三工具原型（`main.py`、`file.py`）保留作参考
