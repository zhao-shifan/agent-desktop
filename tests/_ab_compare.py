"""双引擎对照测试：同一输入，分别跑 legacy / official，逐条对比 SSE 事件序列。

用法：
  # 三种用例 × 双引擎 × (普通/审批) 一次跑完
  python tests/_ab_compare.py --suite --base http://127.0.0.1:8803/v1 --key test --model mock-glm

  # 单跑
  python tests/_ab_compare.py --engine legacy --out .dev-logs/ab-legacy.json

  # 对比两份报告
  python tests/_ab_compare.py --compare .dev-logs/ab-legacy.json .dev-logs/ab-official.json

  # 自检（不需要上游）
  python tests/_ab_compare.py --selftest

上游配置：默认读 agent_data/model_config.json，可被 --base/--key/--model 覆盖。
跑之前先 GET {base}/models 预检，连不上直接退出，不发起对话。
报告不写 Key，只记 base 和 model。
"""
import argparse
import json
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG_PATH = os.path.join(ROOT, "agent_data", "model_config.json")

DEFAULT_PROMPT = "现在几点了？顺便帮我算一下 1234*5678 等于多少。"


# ---------------------------------------------------------------- 配置
def load_cfg(args):
    cfg = {}
    try:
        with open(CFG_PATH, "rb") as f:
            cfg = json.loads(f.read().decode("utf-8"))
    except Exception:
        pass
    base = (args.base or cfg.get("baseUrl") or "").rstrip("/")
    key = args.key or cfg.get("apiKey") or ""
    model = args.model or cfg.get("model") or ""
    return base, key, model


def preflight(base, key, timeout=8):
    import urllib.error
    import urllib.request
    if not base:
        return False, "没有 baseUrl：请填 agent_data/model_config.json，或用 --base/--key/--model"
    req = urllib.request.Request(base + "/models", method="GET",
                                 headers={"Authorization": "Bearer " + (key or "EMPTY")})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return True, "上游可用（HTTP %s）" % r.status
    except urllib.error.HTTPError as e:
        return False, "上游返回 HTTP %s：%s" % (
            e.code, e.read()[:300].decode("utf-8", "replace"))
    except Exception as e:
        return False, "连不上上游 %s：%s" % (base, e)


# ---------------------------------------------------------------- 采集
def _disable_mcp():
    """对照测试屏蔽 MCP：避免 npx 拉起外部服务器，保证两边工具集一致。"""
    try:
        import agent_graph
        agent_graph._MCP_LC_LOADED["done"] = True
        agent_graph._MCP_LC_TOOLS.clear()
        agent_graph._MCP_LC_BY_NAME.clear()
    except Exception as e:
        print("[warn] 屏蔽 MCP 失败：%s" % e)


def run_engine(engine, base, key, model, prompt, approve=False, timeout=180, no_mcp=True):
    events = []
    t0 = time.time()

    def sse(obj):
        events.append({"t": round(time.time() - t0, 3), "e": obj})

    if no_mcp:
        _disable_mcp()

    cfg = {
        "base": base, "key": key, "model": model,
        "temperature": 0.3, "topP": None, "maxTokens": None,
        "systemPrompt": "你是测试助手。需要时间和算数时必须调用工具，不要口算。",
        "reasoning": "auto",
        "perm": {"workDir": "", "searchKey": "", "allowCommand": False},
        "sse": sse, "ping": lambda: None,
        "approveTools": bool(approve),
        "waitApproval": (lambda aid, t: True) if approve else None,
        "followups": False,
        "threadId": "ab-%s-%s" % (engine, uuid.uuid4().hex[:12]),
        "_stop": {"on": False},
    }
    messages = [{"role": "user", "content": prompt}]

    err = None
    final = ""
    try:
        if engine == "official":
            import agent_engine_official
            final = agent_engine_official.run_chat(cfg, messages) or ""
        else:
            import agent_graph
            final = agent_graph.run_chat(cfg, messages) or ""
    except Exception as e:
        import traceback
        traceback.print_exc()
        err = "%s: %s" % (type(e).__name__, e)

    return {
        "engine": engine,
        "base": base,
        "model": model,
        "approve": bool(approve),
        "prompt": prompt,
        "elapsed": round(time.time() - t0, 2),
        "events": events,
        "final": final,
        "error": err,
    }


# ---------------------------------------------------------------- 归一化
def kind_of(ev):
    e = ev.get("e") or {}
    if "choices" in e:
        d = (e.get("choices") or [{}])[0].get("delta") or {}
        if "reasoning_content" in d or "reasoning" in d:
            return "reasoning"
        if "content" in d:
            return "content"
        return "delta?"
    if "tool" in e:
        return "tool_" + str((e["tool"] or {}).get("status"))
    if "approval_request" in e:
        return "approval_request"
    if "thinking" in e:
        return "thinking"
    if "suggestions" in e:
        return "suggestions"
    return "other"


def _delta(ev):
    return ((ev.get("e") or {}).get("choices") or [{}])[0].get("delta", {})


def per_tool_seq(report):
    """每个工具自己的事件子序列（并发执行时全局顺序不保证，按工具看才公平）。"""
    seq = {}
    for e in report.get("events") or []:
        t = (e.get("e") or {}).get("tool")
        if t and t.get("name"):
            seq.setdefault(t["name"], []).append(t.get("status"))
    return seq


def summarize(report):
    evs = report.get("events") or []
    kinds = [kind_of(e) for e in evs]
    seq = []
    for k in kinds:
        if k == "content" and seq and seq[-1] == "content":
            continue
        seq.append(k)
    tools = [((e.get("e") or {}).get("tool") or {}) for e in evs
             if "tool" in (e.get("e") or {})]
    running = [t.get("name") for t in tools if t.get("status") == "running"]
    done = [t.get("name") for t in tools if t.get("status") == "done"]
    denied = [t.get("name") for t in tools if t.get("status") == "denied"]
    content = "".join(_delta(e).get("content", "") for e in evs if "choices" in (e.get("e") or {}))
    reasoning = "".join((_delta(e).get("reasoning_content") or _delta(e).get("reasoning") or "")
                        for e in evs if "choices" in (e.get("e") or {}))
    return {
        "events_total": len(evs),
        "seq": seq,
        "tools_running": running,
        "tools_done": done,
        "tools_denied": denied,
        "previews": [str(t.get("preview") or "")[:60] for t in tools if t.get("status") == "done"],
        "content_len": len(content),
        "content_head": content[:120],
        "reasoning_len": len(reasoning),
        "reasoning_head": reasoning[:80],
        "final_len": len(report.get("final") or ""),
        "elapsed": report.get("elapsed"),
        "error": report.get("error"),
    }


# ---------------------------------------------------------------- 对比
def compare(path_a, path_b):
    with open(path_a, "rb") as f:
        a = json.loads(f.read().decode("utf-8"))
    with open(path_b, "rb") as f:
        b = json.loads(f.read().decode("utf-8"))
    sa, sb = summarize(a), summarize(b)

    print("=" * 62)
    print("对照：%s vs %s" % (a.get("engine"), b.get("engine")))
    print("模型：%s   输入：%s" % (a.get("model"), a.get("prompt")))
    print("=" * 62)

    rows = [
        ("事件总数", sa["events_total"], sb["events_total"]),
        ("事件序列", " → ".join(sa["seq"]), " → ".join(sb["seq"])),
        ("调用工具(running)", sa["tools_running"], sb["tools_running"]),
        ("完成工具(done)", sa["tools_done"], sb["tools_done"]),
        ("拒绝工具(denied)", sa["tools_denied"], sb["tools_denied"]),
        ("工具预览", sa["previews"], sb["previews"]),
        ("正文长度", sa["content_len"], sb["content_len"]),
        ("思考输出长度", sa["reasoning_len"], sb["reasoning_len"]),
        ("最终输出长度", sa["final_len"], sb["final_len"]),
        ("耗时(s)", sa["elapsed"], sb["elapsed"]),
        ("错误", sa["error"], sb["error"]),
    ]
    for name, va, vb in rows:
        same = va == vb
        print("\n【%s】%s" % (name, "一致" if same else "不一致"))
        print("   legacy  : %s" % str(va)[:400])
        print("   official: %s" % str(vb)[:400])

    print("\n" + "-" * 62)
    print("正文开头：")
    print("   legacy  : %s" % sa["content_head"].replace("\n", " "))
    print("   official: %s" % sb["content_head"].replace("\n", " "))

    seq_ok = sa["seq"] == sb["seq"]
    per_a, per_b = per_tool_seq(a), per_tool_seq(b)
    per_ok = per_a == per_b
    parallel_note = ""
    if not seq_ok and per_ok and len(per_a) > 1:
        parallel_note = "（并发交错，逐工具子序列一致，可接受）"
        seq_ok = True
    tools_ok = sa["tools_running"] == sb["tools_running"]
    err_ok = not (sa["error"] or sb["error"])
    print("\n结论：")
    print("   事件序列 %s%s" % ("对齐" if seq_ok else "有差异", parallel_note))
    print("   逐工具子序列 %s" % ("对齐" if per_ok else "有差异"))
    print("   工具调用 %s" % ("对齐" if tools_ok else "有差异"))
    print("   异常 %s" % ("无" if err_ok else "存在"))
    return 0 if (seq_ok and tools_ok and err_ok) else 1


# ---------------------------------------------------------------- 用例矩阵
CASES = {
    "chat": "用一句话介绍一下你自己，不要调用任何工具。",
    "single": "现在几点了？请用工具查，不要猜。",
    "multi": "帮我查一下现在几点，并计算 1234*5678 是多少，两个都要用工具，不要口算。",
}


def suite(args):
    base, key, model = load_cfg(args)
    good, msg = preflight(base, key)
    print("[预检] " + msg)
    if not good:
        print("[预检] 上游不可用，已中止。")
        return 2

    outdir = os.path.dirname(os.path.abspath(args.out or ".dev-logs/x.json"))
    os.makedirs(outdir, exist_ok=True)
    results = []
    for cname, prompt in CASES.items():
        for approve in (False, True):
            tag = "%s-%s" % (cname, "approve" if approve else "plain")
            pair = {}
            for engine in ("legacy", "official"):
                print("\n[运行] %s / %s%s" % (tag, engine, " / approve" if approve else ""))
                rep = run_engine(engine, base, key, model, prompt,
                                 approve=approve, no_mcp=not args.keep_mcp)
                p = os.path.join(outdir, "ab-%s-%s.json" % (tag, engine))
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(rep, f, ensure_ascii=False, indent=1)
                pair[engine] = p
                print("        事件 %d 条，耗时 %.1fs，错误：%s"
                      % (len(rep["events"]), rep["elapsed"], rep["error"]))
            rc = compare(pair["legacy"], pair["official"])
            results.append((tag, rc))
    print("\n" + "#" * 62)
    print("汇总")
    for tag, rc in results:
        print("   %-16s %s" % (tag, "对齐" if rc == 0 else "有差异"))
    return 0 if all(rc == 0 for _, rc in results) else 1


# ---------------------------------------------------------------- 自检
SELF_A = {"engine": "legacy", "prompt": "p", "model": "m", "elapsed": 1.0,
          "final": "答案是 1", "error": None, "events": [
              {"e": {"tool": {"id": "1", "name": "get_time", "status": "running"}}},
              {"e": {"tool": {"id": "1", "name": "get_time", "status": "done", "preview": "12:00"}}},
              {"e": {"choices": [{"delta": {"content": "答案"}}]}},
              {"e": {"choices": [{"delta": {"content": "是 1"}}]}}]}
SELF_B = {"engine": "official", "prompt": "p", "model": "m", "elapsed": 0.9,
          "final": "答案是 1", "error": None, "events": [
              {"e": {"choices": [{"delta": {"reasoning_content": "想一下"}}]}},
              {"e": {"tool": {"id": "1", "name": "get_time", "status": "running"}}},
              {"e": {"tool": {"id": "1", "name": "get_time", "status": "done", "preview": "12:00"}}},
              {"e": {"choices": [{"delta": {"content": "答案是 1"}}]}}]}


def selftest():
    sa, sb = summarize(SELF_A), summarize(SELF_B)
    ok = 0
    bad = 0

    def ck(c, label):
        nonlocal ok, bad
        if c:
            ok += 1
            print("  PASS  " + label)
        else:
            bad += 1
            print("  FAIL  " + label)

    ck(sa["tools_running"] == ["get_time"], "summarize 提取 running 工具")
    ck(sa["content_len"] == len("答案是 1"), "summarize 拼接 content")
    ck(sa["seq"] == ["tool_running", "tool_done", "content"], "seq 压缩连续 content")
    ck(sb["seq"] == ["reasoning", "tool_running", "tool_done", "content"], "识别 reasoning 事件")
    ck(sb["reasoning_len"] == len("想一下"), "统计 reasoning 长度")
    print("\n自检：%d passed, %d failed" % (ok, bad))
    return 0 if bad == 0 else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=["legacy", "official"])
    ap.add_argument("--out")
    ap.add_argument("--compare", nargs=2)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--suite", action="store_true")
    ap.add_argument("--keep-mcp", action="store_true")
    ap.add_argument("--approve", action="store_true")
    ap.add_argument("--prompt", default=DEFAULT_PROMPT)
    ap.add_argument("--base")
    ap.add_argument("--key")
    ap.add_argument("--model")
    args = ap.parse_args()

    if args.selftest:
        return selftest()
    if args.suite:
        return suite(args)
    if args.compare:
        return compare(args.compare[0], args.compare[1])
    if not args.engine:
        ap.error("要么 --engine，要么 --suite，要么 --compare，要么 --selftest")

    base, key, model = load_cfg(args)
    good, msg = preflight(base, key)
    print("[预检] " + msg)
    if not good:
        print("[预检] 上游不可用，已中止（没有发起任何对话）。")
        return 2

    print("[运行] engine=%s model=%s approve=%s" % (args.engine, model, args.approve))
    report = run_engine(args.engine, base, key, model, args.prompt,
                        approve=args.approve, no_mcp=not args.keep_mcp)
    out = args.out or (".dev-logs/ab-%s.json" % args.engine)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print("[完成] %s 写入 %s（事件 %d 条，耗时 %.1fs，错误：%s）"
          % (args.engine, out, len(report["events"]), report["elapsed"], report["error"]))
    print("[摘要] " + json.dumps(summarize(report), ensure_ascii=False)[:600])
    return 0


if __name__ == "__main__":
    sys.exit(main())
