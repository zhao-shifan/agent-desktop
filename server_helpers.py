# -*- coding: utf-8 -*-
"""小凡智能体 · server 与 agent_graph 共用的上下文裁剪工具。"""


def _est_len(msgs):
    """粗略估算消息列表总字符数（Qwen-Agent trim_history 的轻量版）。"""
    total = 0
    for m in msgs:
        total += len(str(m.get("content") or ""))
        for tc in (m.get("tool_calls") or []):
            total += len(str((tc.get("function") or {}).get("arguments") or ""))
    return total


def trim_history(msgs, budget=120000):
    """上下文预算裁剪：超预算时压缩较早的 tool 结果与历史正文（保留 system）。
    参考 Qwen-Agent 的 trim_history：近几轮逐字保留，老消息摘要化，防上下文爆炸。"""
    if _est_len(msgs) <= budget:
        return msgs
    keep_recent = 8          # 最近 8 条逐字保留
    n = len(msgs)
    out = []
    for i, m in enumerate(msgs):
        role = m.get("role")
        if role == "system" or i >= n - keep_recent:
            out.append(m)
            continue
        c = str(m.get("content") or "")
        if role == "tool":
            out.append({**m, "content": "（历史工具结果已省略）" if c else c})
        elif len(c) > 600:
            out.append({**m, "content": c[:600] + "…（历史消息已截断）"})
        else:
            out.append(m)
    return out
