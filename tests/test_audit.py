"""提示词野心度诊断脚本 audit.py 的测试，全离线、不访问网络。

Run with:  pytest tests/test_audit.py -v
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "scripts"))

import audit  # noqa: E402
from audit import audit as audit_prompt  # noqa: E402

AUDIT = ROOT / "scripts" / "audit.py"
SUBPROCESS_ENV = {**os.environ, "PYTHONUTF8": "1"}

# 一段不触发任何检测器的「干净」提示词
CLEAN_PROMPT = (
    "保证 API 网关在峰值 5000 QPS 下无崩溃。基于网关原始日志建立延迟基准，"
    "用独立脚本交叉验证结论。"
)

# 一段把多数检测器全部触发的「最差」提示词
WORST_PROMPT = "扮演专家，帮我做个优化PPT，尽量好"


def run_cli(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(AUDIT), *args],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=SUBPROCESS_ENV,
    )


class TestRoleplayDetector:
    def test_roleplay_word_triggers_high_finding(self) -> None:
        result = audit_prompt("请你扮演一个华尔街资深投资人，分析这家公司。")
        finding = next(f for f in result["findings"] if f["id"] == "roleplay")
        assert finding["severity"] == "high"
        assert finding["dimension"] == "depth"

    def test_persona_sentence_triggers_too(self) -> None:
        result = audit_prompt("你是一个资深数据科学家，帮我看看这份报表。")
        assert any(f["id"] == "roleplay" for f in result["findings"])

    def test_english_act_as_triggers(self) -> None:
        result = audit_prompt("Act as a senior database engineer and tune this query.")
        assert any(f["id"] == "roleplay" for f in result["findings"])

    def test_clean_prompt_does_not_trigger(self) -> None:
        assert all(f["id"] != "roleplay" for f in audit_prompt(CLEAN_PROMPT)["findings"])


class TestTaskVerbDetector:
    def test_task_verbs_without_result_signal_fire(self) -> None:
        result = audit_prompt("帮我修复登录页的报错，再整理一下报错日志的格式。")
        finding = next(f for f in result["findings"] if f["id"] == "task_verb")
        assert finding["severity"] == "medium"
        assert finding["dimension"] == "altitude"

    def test_result_signal_suppresses_task_verb(self) -> None:
        result = audit_prompt("帮我修复登录报错，保证登录功能从此不再出现 5xx。")
        assert all(f["id"] != "task_verb" for f in result["findings"])

    def test_no_task_verb_no_finding(self) -> None:
        assert all(f["id"] != "task_verb" for f in audit_prompt(CLEAN_PROMPT)["findings"])


class TestFormatPurposeDetector:
    def test_format_noun_without_purpose_fires_low(self) -> None:
        result = audit_prompt("帮我把这份销售数据做成一版季度汇报PPT，排版好看一点。")
        finding = next(f for f in result["findings"] if f["id"] == "format_purpose")
        assert finding["severity"] == "low"
        assert finding["dimension"] == "altitude"

    def test_purpose_word_suppresses_finding(self) -> None:
        result = audit_prompt("把销售数据做成PPT，目的在于让管理层更早发现渠道问题并调配资源。")
        assert all(f["id"] != "format_purpose" for f in result["findings"])

    def test_no_format_noun_no_finding(self) -> None:
        assert all(f["id"] != "format_purpose" for f in audit_prompt(CLEAN_PROMPT)["findings"])


class TestNoVerificationDetector:
    def test_missing_verification_fires_high(self) -> None:
        result = audit_prompt("帮我把这份销售数据做成一版季度汇报PPT，排版好看一点。")
        finding = next(f for f in result["findings"] if f["id"] == "no_verification")
        assert finding["severity"] == "high"
        assert finding["dimension"] == "depth"

    def test_verification_word_suppresses_finding(self) -> None:
        assert all(f["id"] != "no_verification" for f in audit_prompt(CLEAN_PROMPT)["findings"])


class TestNoRawDataDetector:
    def test_missing_raw_data_fires_low(self) -> None:
        result = audit_prompt("根据行业报告分析一下用户流失的原因，结论要经过独立验证。")
        finding = next(f for f in result["findings"] if f["id"] == "no_raw_data")
        assert finding["severity"] == "low"

    def test_raw_data_word_suppresses_finding(self) -> None:
        assert all(f["id"] != "no_raw_data" for f in audit_prompt(CLEAN_PROMPT)["findings"])


class TestVagueGoalDetector:
    def test_vague_words_without_numbers_fire(self) -> None:
        result = audit_prompt("帮我把网站加载提速，尽量更快，结论要经过独立基准验证。")
        finding = next(f for f in result["findings"] if f["id"] == "vague_goal")
        assert finding["severity"] == "medium"

    def test_digits_suppress_finding(self) -> None:
        result = audit_prompt("帮我把网站加载从 10 秒优化到 200 毫秒，用真实基准验证。")
        assert all(f["id"] != "vague_goal" for f in result["findings"])

    def test_suppression_prefers_miss_over_false_alarm(self) -> None:
        # 「半秒」这类中文数词不识别，宁可漏报也不把含数词的提示词误报为模糊目标
        result = audit_prompt("把加载时间尽量压到 0.5 秒以内，用真实基准验证结论。")
        assert all(f["id"] != "vague_goal" for f in result["findings"])


class TestTooThinDetector:
    def test_short_prompt_fires_high(self) -> None:
        result = audit_prompt("帮我写个标题")
        finding = next(f for f in result["findings"] if f["id"] == "too_thin")
        assert finding["severity"] == "high"

    def test_prompt_at_threshold_does_not_fire(self) -> None:
        long_prompt = "总结这份文档的要点" + "补" * 30
        assert all(f["id"] != "too_thin" for f in audit_prompt(long_prompt)["findings"])


class TestScoring:
    def test_clean_prompt_scores_full(self) -> None:
        result = audit_prompt(CLEAN_PROMPT)
        assert result["score"] == 100
        assert result["dimensions"]["altitude"] == 100
        assert result["dimensions"]["depth"] == 100

    def test_worst_case_prompt_scores_near_zero(self) -> None:
        result = audit_prompt(WORST_PROMPT)
        assert 0 <= result["score"] <= 15

    def test_range_is_always_none(self) -> None:
        assert audit_prompt(CLEAN_PROMPT)["dimensions"]["range"] is None
        assert audit_prompt(WORST_PROMPT)["dimensions"]["range"] is None

    def test_score_never_negative_and_findings_carry_meta(self) -> None:
        result = audit_prompt(WORST_PROMPT)
        assert result["score"] >= 0
        assert result["meta"]["length"] == len(WORST_PROMPT)
        assert result["meta"]["version"] == audit.VERSION

    def test_dimension_subscore_reflects_only_own_findings(self) -> None:
        result = audit_prompt("帮我整理这份表格")
        ids = {f["id"] for f in result["findings"]}
        altitude_fines = sum(
            audit.DEDUCTIONS[f["severity"]]
            for f in result["findings"]
            if f["dimension"] == "altitude"
        )
        assert result["dimensions"]["altitude"] == 100 - altitude_fines
        assert "task_verb" in ids


class TestOutputFormats:
    def test_json_structure_is_complete(self) -> None:
        result = audit_prompt(CLEAN_PROMPT)
        assert set(result) == {"score", "dimensions", "findings", "meta"}
        assert set(result["dimensions"]) == {"altitude", "depth", "range"}
        for f in result["findings"]:
            assert set(f) == {"id", "severity", "dimension", "evidence", "suggestion"}

    def test_human_report_contains_score_line(self) -> None:
        text = audit.report(audit_prompt(WORST_PROMPT))
        assert "提示词野心度诊断" in text
        assert "总分" in text
        assert "需模型判断" in text

    def test_report_without_findings_mentions_range_limit(self) -> None:
        text = audit.report(audit_prompt(CLEAN_PROMPT))
        assert "未发现问题" in text


class TestCLI:
    def test_diagnose_json_from_file(self, tmp_path: Path) -> None:
        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text(WORST_PROMPT, encoding="utf-8")
        proc = run_cli("diagnose", "--json", "--file", str(prompt_file))
        assert proc.returncode == 0
        data = json.loads(proc.stdout)
        assert data["score"] == audit_prompt(WORST_PROMPT)["score"]
        assert "findings" in data and "meta" in data

    def test_diagnose_accepts_stdin(self) -> None:
        proc = run_cli("diagnose", "--json", stdin=CLEAN_PROMPT)
        assert proc.returncode == 0
        assert json.loads(proc.stdout)["score"] == 100

    def test_diagnose_empty_input_exits_one(self) -> None:
        proc = run_cli("diagnose", stdin="")
        assert proc.returncode == 1
        assert "输入为空" in proc.stderr

    def test_validate_passes_above_threshold(self, tmp_path: Path) -> None:
        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text(CLEAN_PROMPT, encoding="utf-8")
        proc = run_cli("validate", "--min-score", "60", "--file", str(prompt_file))
        assert proc.returncode == 0
        assert "PASS" in proc.stdout

    def test_validate_fails_below_threshold(self, tmp_path: Path) -> None:
        prompt_file = tmp_path / "prompt.txt"
        prompt_file.write_text(WORST_PROMPT, encoding="utf-8")
        proc = run_cli("validate", "--min-score", "60", "--file", str(prompt_file))
        assert proc.returncode == 1
        assert "FAIL" in proc.stdout

    def test_validate_empty_input_exits_one(self) -> None:
        assert run_cli("validate", stdin="").returncode == 1

    def test_capabilities_json_lists_all_detectors(self) -> None:
        proc = run_cli("capabilities", "--json")
        assert proc.returncode == 0
        data = json.loads(proc.stdout)
        ids = {d["id"] for d in data["detectors"]}
        assert ids == {d["id"] for d in audit.DETECTORS}
        assert data["version"] == audit.VERSION

    def test_capabilities_human_output(self) -> None:
        proc = run_cli("capabilities")
        assert proc.returncode == 0
        assert "roleplay" in proc.stdout
        assert "no_verification" in proc.stdout

    def test_missing_file_exits_nonzero(self) -> None:
        proc = run_cli("diagnose", "--file", "no_such_file.txt")
        assert proc.returncode != 0


class TestMainInProcess:
    """直接调用 main()，让 CLI 分支计入覆盖率。"""

    def test_diagnose_human_report_via_main(self, capsys) -> None:
        assert audit.main(["diagnose", CLEAN_PROMPT]) == 0
        out = capsys.readouterr().out
        assert "提示词野心度诊断" in out
        assert "总分" in out

    def test_diagnose_json_via_main(self, capsys) -> None:
        assert audit.main(["diagnose", "--json", WORST_PROMPT]) == 0
        data = json.loads(capsys.readouterr().out)
        assert data["score"] == audit_prompt(WORST_PROMPT)["score"]

    def test_diagnose_reads_stdin_when_no_text(self, monkeypatch, capsys) -> None:
        monkeypatch.setattr(sys, "stdin", io.StringIO(CLEAN_PROMPT))
        assert audit.main(["diagnose", "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["score"] == 100

    def test_diagnose_empty_stdin_exits_one(self, monkeypatch, capsys) -> None:
        monkeypatch.setattr(sys, "stdin", io.StringIO(""))
        assert audit.main(["diagnose"]) == 1
        assert "输入为空" in capsys.readouterr().err

    def test_diagnose_reads_file(self, tmp_path: Path, capsys) -> None:
        prompt_file = tmp_path / "p.txt"
        prompt_file.write_text(WORST_PROMPT, encoding="utf-8")
        assert audit.main(["diagnose", "--json", "--file", str(prompt_file)]) == 0
        assert json.loads(capsys.readouterr().out)["score"] <= 15

    def test_validate_threshold_via_main(self, capsys) -> None:
        assert audit.main(["validate", "--min-score", "60", CLEAN_PROMPT]) == 0
        assert "PASS" in capsys.readouterr().out
        assert audit.main(["validate", "--min-score", "60", WORST_PROMPT]) == 1
        assert "FAIL" in capsys.readouterr().out

    def test_validate_empty_input_exits_one(self, monkeypatch) -> None:
        monkeypatch.setattr(sys, "stdin", io.StringIO(""))
        assert audit.main(["validate"]) == 1

    def test_capabilities_via_main_both_modes(self, capsys) -> None:
        assert audit.main(["capabilities"]) == 0
        assert "roleplay" in capsys.readouterr().out
        assert audit.main(["capabilities", "--json"]) == 0
        data = json.loads(capsys.readouterr().out)
        assert data["version"] == audit.VERSION


class TestDeterminism:
    def test_same_input_same_output(self) -> None:
        first = json.dumps(audit_prompt(WORST_PROMPT), ensure_ascii=False, sort_keys=True)
        second = json.dumps(audit_prompt(WORST_PROMPT), ensure_ascii=False, sort_keys=True)
        assert first == second

    def test_detector_registry_matches_checks(self) -> None:
        finding_ids = {d["id"] for d in audit.DETECTORS if d["kind"] == "finding"}
        assert len(finding_ids) == len(audit.FINDING_CHECKS)
