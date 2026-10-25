#!/usr/bin/env python3
"""提示词野心度静态诊断脚本。

基于《How to Be More Ambitious》的高度 / 深度 / 广度框架，对一段提示词做静态
模式检测，输出 JSON 或人读报告。广度（range）维度不做静态评分——跨行业借喻
是语义判断，正则匹配只会产生假精度，该维度需要由调用方模型来判断。

三个命令：
  diagnose      完整诊断，输出人读报告或 --json
  validate      按分数门槛做 CI 门禁，达标 exit 0，不达标 exit 1
  capabilities  列出全部检测器

纯 Python 标准库，无外部依赖。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Callable, Optional

VERSION = "1.0.0"
START_SCORE = 100
DEDUCTIONS = {"high": 20, "medium": 10, "low": 5}
MIN_LENGTH = 30

# ---------------------------------------------------------------- 信号词表

RE_RESULT_SIGNAL = re.compile(
    r"保证|永不|永远不|不再|直到|验收|确保|杜绝|零故障|不崩|不出错|一次通过|无崩溃"
)
RE_HAS_DIGIT = re.compile(r"\d")

# ------------------------------------------------------------ 检测器实现

TASK_VERB = re.compile(
    r"帮我|修复|修一下|修个|写一个|写一份|做个|做一份|整理|生成|改一下|排版|翻译|总结一下|填(进|入|到)"
)


def _check_task_verb(text: str) -> Optional[dict]:
    if RE_RESULT_SIGNAL.search(text):
        return None
    hits = [m.group(0) for m in TASK_VERB.finditer(text)]
    if not hits:
        return None
    return _finding(
        "task_verb", "altitude", "medium", hits,
        "通篇是任务级动词，描述的是要做的事，不是要发生的结果。先问「做完这件事之后我到底想发生什么」，把目标改写成可验收的结果",
    )


FORMAT_NOUN = re.compile(r"PPT|ppt|幻灯片|表格|报告|文档|周报|月报|汇报|邮件")
PURPOSE_WORD = re.compile(
    r"为什么|原因|目的|决定|判断|发现|机制|问题|资源|提前|更早"
)


def _check_format_purpose(text: str) -> Optional[dict]:
    hits = [m.group(0) for m in FORMAT_NOUN.finditer(text)]
    if not hits:
        return None
    if PURPOSE_WORD.search(text):
        return None
    return _finding(
        "format_purpose", "altitude", "low", hits,
        "出现形式名词但没写这个形式要达成什么。形式是为目的服务的，写明目的之后可以连形式一起换掉",
    )


VERIFY_WORD = re.compile(
    r"测试|验证|基准|benchmark|裁判|评审|复查|复核|审计|对拍|交叉|独立|外部"
)


def _check_no_verification(text: str) -> Optional[dict]:
    if VERIFY_WORD.search(text):
        return None
    return _finding(
        "no_verification", "depth", "high", [],
        "没有任何外部验证要求。模型自评自审只会讨好你，必须写明由什么外部标准裁决：真实终端跑测试、独立脚本挑刺、或第三方数据复核",
    )


RAW_DATA = re.compile(
    r"日志|原始数据|数据库|源数据|一手|埋点|源文件|原始记录|raw"
)


def _check_no_raw_data(text: str) -> Optional[dict]:
    if RAW_DATA.search(text):
        return None
    return _finding(
        "no_raw_data", "depth", "low", [],
        "没有要求从原始材料开始。顶尖专家从一手数据入手，补一句「基于原始数据，不要用已被消化的二手汇总」",
    )


VAGUE_WORD = re.compile(r"更好|更快|更清晰|尽量|尽可能|优化一下|提升一下|改进|加强")


def _check_vague_goal(text: str) -> Optional[dict]:
    hits = [m.group(0) for m in VAGUE_WORD.finditer(text)]
    if not hits:
        return None
    if RE_HAS_DIGIT.search(text):
        return None
    return _finding(
        "vague_goal", "depth", "medium", hits,
        "目标没有数字。离谱但明确的目标好过保守的形容词，把「更快」写成可测量的数值",
    )


ROLEPLAY = re.compile(r"扮演|你是(一个|一名|位|名)|act as|pretend", re.IGNORECASE)


def _check_roleplay(text: str) -> Optional[dict]:
    hits = [m.group(0) for m in ROLEPLAY.finditer(text)]
    if not hits:
        return None
    return _finding(
        "roleplay", "depth", "high", hits,
        "角色扮演只换说话腔调，不换工作方法。删掉「扮演 X」，改成要求使用 X 行业顶尖专家的工具、原始数据和方法做实事",
    )


def _check_too_thin(text: str) -> Optional[dict]:
    if len(text) >= MIN_LENGTH:
        return None
    return _finding(
        "too_thin", "general", "high", [f"长度 {len(text)} 字"],
        f"提示词不足 {MIN_LENGTH} 字，信息量不足以支撑野心版改写。补充背景、手头材料、约束和验收方式",
    )


# --------------------------------------------------------------- 基础设施

FINDING_CHECKS: list[Callable[[str], Optional[dict]]] = [
    _check_roleplay,
    _check_task_verb,
    _check_format_purpose,
    _check_no_verification,
    _check_no_raw_data,
    _check_vague_goal,
    _check_too_thin,
]

DETECTORS = [
    {"id": "roleplay", "dimension": "depth", "severity": "high", "kind": "finding",
     "description": "角色扮演式提示词：只换腔调不换方法"},
    {"id": "task_verb", "dimension": "altitude", "severity": "medium", "kind": "finding",
     "description": "任务级动词密集且无结果级信号：描述要做的事而非要发生的结果"},
    {"id": "format_purpose", "dimension": "altitude", "severity": "low", "kind": "finding",
     "description": "出现形式名词（PPT/表格/报告）但没有写形式要达成的目的"},
    {"id": "no_verification", "dimension": "depth", "severity": "high", "kind": "finding",
     "description": "缺失外部验证条款：没有测试、基准、独立裁判等要求"},
    {"id": "no_raw_data", "dimension": "depth", "severity": "low", "kind": "finding",
     "description": "没有要求从原始材料开始，全部基于二手信息"},
    {"id": "vague_goal", "dimension": "depth", "severity": "medium", "kind": "finding",
     "description": "目标是无数字的形容词（更好/尽量），不可测量"},
    {"id": "too_thin", "dimension": "general", "severity": "high", "kind": "finding",
     "description": f"提示词不足 {MIN_LENGTH} 字"},
    {"id": "result_signal", "dimension": "altitude", "severity": None, "kind": "signal",
     "description": "结果级信号（保证/永不/验收等）：存在时不触发 task_verb"},
]


def _finding(fid: str, dimension: str, severity: str,
             evidence: list[str], suggestion: str) -> dict:
    return {
        "id": fid,
        "severity": severity,
        "dimension": dimension,
        "evidence": evidence[:3],
        "suggestion": suggestion,
    }


def audit(prompt: str) -> dict:
    """对一段提示词执行全部检测，返回结构化诊断结果。"""
    findings = [f for f in (check(prompt) for check in FINDING_CHECKS) if f]
    score = max(0, START_SCORE - sum(DEDUCTIONS[f["severity"]] for f in findings))

    def dim_score(dim: str) -> int:
        sub = START_SCORE - sum(
            DEDUCTIONS[f["severity"]] for f in findings if f["dimension"] == dim
        )
        return max(0, sub)

    return {
        "score": score,
        "dimensions": {
            "altitude": dim_score("altitude"),
            "depth": dim_score("depth"),
            "range": None,
        },
        "findings": findings,
        "meta": {"version": VERSION, "length": len(prompt)},
    }


def report(result: dict) -> str:
    """把诊断结果渲染成人读文本。"""
    dims = result["dimensions"]
    range_txt = "需模型判断（静态脚本不评）" if dims["range"] is None else f"{dims['range']}/100"
    lines = [
        "提示词野心度诊断",
        f"长度: {result['meta']['length']} 字",
        f"总分: {result['score']}/100    "
        f"高度: {dims['altitude']}/100    "
        f"深度: {dims['depth']}/100    "
        f"广度: {range_txt}",
    ]
    if result["findings"]:
        lines.append("发现:")
        for f in result["findings"]:
            lines.append(f"[{f['severity']}][{f['dimension']}] {f['id']}")
            if f["evidence"]:
                lines.append(f"  证据: {'、'.join(f['evidence'])}")
            lines.append(f"  建议: {f['suggestion']}")
    else:
        lines.append("未发现问题。静态脚本只覆盖可匹配的模式，广度维度的跨行业借喻仍需人工判断。")
    return "\n".join(lines)


# ------------------------------------------------------------------ CLI

def _read_input(args: argparse.Namespace) -> str:
    if getattr(args, "file", None):
        with open(args.file, encoding="utf-8") as fh:
            return fh.read()
    if args.text:
        return args.text
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return ""


def cmd_diagnose(args: argparse.Namespace) -> int:
    text = _read_input(args)
    if not text.strip():
        print("错误: 输入为空。用法: audit.py diagnose \"提示词\" 或 --file 路径 或管道传入",
              file=sys.stderr)
        return 1
    result = audit(text)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(report(result))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    text = _read_input(args)
    if not text.strip():
        print("错误: 输入为空。", file=sys.stderr)
        return 1
    result = audit(text)
    ok = result["score"] >= args.min_score
    print(f"score={result['score']} min_score={args.min_score} "
          f"{'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def cmd_capabilities(args: argparse.Namespace) -> int:
    if args.json:
        print(json.dumps({"version": VERSION, "detectors": DETECTORS},
                         ensure_ascii=False, indent=2))
    else:
        print(f"audit.py v{VERSION} 检测器（{len(DETECTORS)} 个）:")
        for d in DETECTORS:
            sev = d["severity"] or "signal"
            print(f"  {d['id']:<18} {d['dimension']:<9} {sev:<7} {d['description']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="audit.py",
        description="提示词野心度静态诊断（高度/深度/广度框架）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_diag = sub.add_parser("diagnose", help="完整诊断，输出报告或 --json")
    p_diag.add_argument("text", nargs="?", help="待诊断的提示词文本")
    p_diag.add_argument("--file", help="从文件读取提示词")
    p_diag.add_argument("--json", action="store_true", help="输出 JSON")
    p_diag.set_defaults(func=cmd_diagnose)

    p_val = sub.add_parser("validate", help="按分数门槛做 CI 门禁")
    p_val.add_argument("text", nargs="?", help="待校验的提示词文本")
    p_val.add_argument("--file", help="从文件读取提示词")
    p_val.add_argument("--min-score", type=int, default=60, help="及格线（默认 60）")
    p_val.set_defaults(func=cmd_validate)

    p_cap = sub.add_parser("capabilities", help="列出全部检测器")
    p_cap.add_argument("--json", action="store_true", help="输出 JSON")
    p_cap.set_defaults(func=cmd_capabilities)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
