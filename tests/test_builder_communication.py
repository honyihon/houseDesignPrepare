"""Focused source, blank-reply and private-record safety checks; no browsers or scenes."""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import re
from pathlib import Path

import pytest

from house_design.builder_communication import INDEX, OUT, PLAN, build, validate
from house_design.contracts import ContractError, stable_hash
from house_design.project_next_steps import CONTROLS, REGISTER, REQUIREMENTS, keyed
from scripts.export_builder_communication import forms, index_html, init_records, render

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT/name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def report():
    return build(ROOT)


def inputs():
    return copy.deepcopy(read(PLAN)), keyed(read(INDEX)["work_items"], "tasks")


def records(text):
    return list(csv.DictReader(io.StringIO(text.lstrip("\ufeff"))))


def test_build_is_preparation_without_writing_requirements_or_scenes(report):
    names = [REQUIREMENTS, REGISTER, CONTROLS, "structured/candidates/kaohsiung-house-options-3d.html"]
    before = {n: (ROOT/n).read_bytes() for n in names}
    assert build(ROOT)["report_hash"] == report["report_hash"]
    assert before == {n: (ROOT/n).read_bytes() for n in names}
    assert report["summary"] == {"stages": 6, "questions": 22, "a_interfaces": 11, "quote_packages": 12,
        "first_meeting_questions": 5, "formal_requirement_statuses": {"candidate": 66},
        "formal_register_statuses": {"unknown": 105}}
    assert report["protected_controls_unchanged"] == 149
    for field in ["contractual_responsibilities_agreed", "formal_requirements_or_register_written", "design_or_primary_3d_changed", "adopted"]:
        assert report[field] is False
    assert report["builder_responses_received"] == report["actual_conditions_received_here"] == 0
    assert report["professional_approval"] == "unknown" and report["browser_qa"] == "not-run"


def test_builder_questions_are_linked_to_existing_formal_sources(report):
    refs = {t["id"]: t for t in report["task_references"]}
    assert {t for q in report["plan"]["questions"] for t in q["task_ids"]} <= set(refs)
    for task in refs.values():
        assert all(r["status"] == "candidate" for r in task["requirement_references"])
        assert all(r["status"] == "unknown" for r in task["register_references"])
    assert all(path in report["source_hashes"] for t in refs.values() for path in t["source_documents"])


def test_builder_brief_uses_latest_shared_laundry_direction_and_keeps_host_and_kitchen_choice_open(report):
    plan = report["plan"]
    assert "三棟1F共用一組" in plan["shared_brief"] and "C2F暫不用但保空間" in plan["shared_brief"]
    questions = {q["id"]: q for q in plan["questions"]}
    assert "全棟僅一台既有2F" not in questions["BC-10"]["ask"]
    assert "機位與日後使用空間保留" in questions["BC-10"]["ask"]
    assert "上層須留洗衣機位" in questions["BC-06"]["ask"] and "2.232㎡尚未接受" in questions["BC-06"]["ask"]
    assert "合法污水終端" in questions["BC-14"]["ask"]
    assert "原機暫不用、保空間不放固定櫃" in questions["BC-17"]["ask"]
    assert len(questions) == 22 and not report["adopted"]


def test_a_scope_is_separate_but_early_interfaces_are_joint_and_unagreed(report):
    p = report["plan"]
    assert "B／C" in p["owner_direction"]["scope_boundary"]
    assert "不是" in p["owner_direction"]["scope_boundary"]
    assert any("預埋" in s["timing"] and "A設計師" in s["participants"] for s in p["stages"])
    rows = records(forms(p)["a-interface-matrix.csv"])
    assert len(rows) == 11
    assert all(all(r[k] == "" for k in ["已議定設計方", "已議定施工方", "已議定供料方", "保固銜接約定",
        "核對狀態", "建商確認", "設計師確認", "屋主確認"]) for r in rows)
    text = json.dumps(p["a_interfaces"], ensure_ascii=False)
    assert all(word in text for word in ["防水", "排水", "天花", "新風", "MDF", "補強", "保固"])


def test_all_response_money_dates_and_approvals_start_empty(report):
    files = forms(report["plan"])
    assert len(files) == 7
    for row in records(files["builder-replies.csv"]):
        assert row["問題ID"] and row["應交資料"]
        assert all(row[k] == "" for k in ["回覆狀態", "建商回覆", "依據文件", "回覆期限", "屋主選擇", "專業審查狀態", "施工圖發行"])
    for row in records(files["same-scope-quotes.csv"]):
        assert all(row[k] == "" for k in ["數量單位", "取消折抵", "同範圍總額", "工期及付款條件", "屋主選擇"])
    for name in ["meeting-decisions.csv", "change-log.csv", "inspection-log.csv", "drawing-register.csv"]:
        assert all(v == "" for row in records(files[name]) for v in row.values())


@pytest.mark.parametrize("change", ["unknown-task", "unknown-stage", "unknown-building", "duplicate-question", "missing-hold", "reverse-stages", "auto-adopt", "actual-data"])
def test_bad_links_or_promoted_plan_is_rejected(change):
    p, tasks = inputs()
    if change == "unknown-task":
        p["questions"][0]["task_ids"] = ["MISSING"]
    elif change == "unknown-stage":
        p["questions"][0]["stage"] = "S99"
    elif change == "unknown-building":
        p["questions"][0]["buildings"] = ["D"]
    elif change == "duplicate-question":
        p["questions"].append(p["questions"][0])
    elif change == "missing-hold":
        p["stages"][0]["hold"] = ""
    elif change == "reverse-stages":
        p["stages"].reverse()
    elif change == "auto-adopt":
        p["authority"] = "auto-adopt"
    else:
        p["owner_direction"]["actual_site_data_received"] = True
    with pytest.raises(ContractError):
        validate(p, tasks)


@pytest.mark.parametrize("ids", [["BC-99"], ["BC-22"], [f"BC-{i:02d}" for i in range(1, 7)]])
def test_first_meeting_keeps_five_initial_questions(ids):
    p, tasks = inputs()
    p["first_meeting"]["question_ids"] = ids
    with pytest.raises(ContractError):
        validate(p, tasks)


def test_private_record_creation_and_rerun_cannot_overwrite_answers(tmp_path, report):
    target = init_records(tmp_path, "inputs/private/meeting-001", report)
    reply = target/"builder-replies.csv"
    reply.write_text("owner recorded a real reply", encoding="utf-8")
    basis = (target/"basis-review.json").read_bytes()
    with pytest.raises(FileExistsError):
        init_records(tmp_path, "inputs/private/meeting-001", report)
    assert reply.read_text(encoding="utf-8") == "owner recorded a real reply"
    assert (target/"basis-review.json").read_bytes() == basis
    assert json.loads(basis)["report_hash"] == report["report_hash"]
    assert {p.name for p in target.iterdir()} == set(forms(report["plan"])) | {"basis-review.json", "RECORDS.md"}


@pytest.mark.parametrize("path", ["structured/new", "inputs/private", "inputs/private/../public", "/tmp/records", "inputs\\private\\new"])
def test_records_must_stay_in_a_new_private_directory(tmp_path, report, path):
    with pytest.raises(ContractError):
        init_records(tmp_path, path, report)
    assert not list(tmp_path.iterdir())


def test_records_reject_symlink_out_of_private(tmp_path, report):
    external = tmp_path/"public"
    external.mkdir()
    private = tmp_path/"inputs/private"
    private.mkdir(parents=True)
    (private/"escape").symlink_to(external, target_is_directory=True)
    with pytest.raises(ContractError):
        init_records(tmp_path, "inputs/private/escape/new", report)
    assert not list(external.iterdir())


def test_source_and_artifact_bindings_and_links_are_current(report):
    assert report["report_hash"] == stable_hash({k: v for k, v in report.items() if k != "report_hash"})
    for name, digest in report["source_hashes"].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == digest
    files = render(report)
    assert len(files) == 12
    manifest = json.loads(files["artifact-manifest.json"])
    for name, digest in manifest["artifacts"].items():
        assert hashlib.sha256(files[name].encode()).hexdigest() == digest
    for name, content in files.items():
        assert (ROOT/OUT/name).read_bytes() == content.encode()
    for href in re.findall(r'href="([^"]+)"', files["index.html"]):
        if href.startswith("#"):
            assert 'id="'+href[1:]+'"' in files["index.html"]
        else:
            assert (ROOT/OUT/href).is_file()
    assert "<script" not in files["index.html"]


def test_current_check_detects_changed_templates_without_overwriting(tmp_path, monkeypatch, report):
    import scripts.export_builder_communication as exporter
    monkeypatch.setattr(exporter, "ROOT", tmp_path)
    monkeypatch.setattr(exporter, "build", lambda root: report)
    monkeypatch.setattr("sys.argv", ["export", "--check"])
    target = tmp_path/OUT
    target.mkdir(parents=True)
    (target/"index.html").write_text("outdated", encoding="utf-8")
    assert exporter.main() == 1
    assert (target/"index.html").read_text(encoding="utf-8") == "outdated"


def test_public_html_escapes_all_plan_text(report):
    changed = copy.deepcopy(report)
    changed["plan"]["stages"][0]["title"] = '<img onerror="alert(1)">'
    text = index_html(changed, list(forms(changed["plan"])))
    assert '<img onerror="alert(1)">' not in text and "&lt;img" in text
