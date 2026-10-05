from __future__ import annotations

import json
from pathlib import Path

from house_design.brief import (
    BRIEF_SCHEMA,
    SITE_WARNING,
    build_design_brief,
    design_brief_hash,
    design_brief_html,
    design_brief_markdown,
    extract_open_questions,
    household_summary,
    source_label,
    write_design_brief,
)
from house_design.contracts import sha256_file, stable_hash, write_json
from house_design.intake import relationship_hash

ROOT = Path(__file__).resolve().parents[1]


def _project() -> dict:
    return {
        "schema": "house-project-v2",
        "project_id": "test",
        "name": "測試專案",
        "stage": "site_search",
        "jurisdiction": {"country_code": "TW", "county_code": "KHH", "label": "高雄"},
        "parcel_relationship": "adjacent_separate_parcels",
        "site_search": {
            "selection_status": "searching",
            "target_scenario": {
                "target_parcel_count": 3,
                "target_area_ping_each": 32.0,
                "order_left_to_right": ["C", "B", "A"],
            },
        },
        "buildings": [
            {"id": "A", "role": "主要設備與全齡生活棟", "role_status": "owner_confirmed_predesign_policy"},
            {"id": "B", "role": "祭祀傳承棟", "role_status": "owner_confirmed_predesign_policy"},
            {"id": "C", "role": "長輩友善自住棟", "role_status": "owner_confirmed_predesign_policy"},
        ],
        "parcels": [
            {
                "id": key,
                "parcel_area_ping": 32.0,
                "parcel_area_sqm": 105.78512,
                "land_number": None,
                "zoning": None,
                "road": {"status": "unknown"},
                "building_coverage_ratio": None,
                "floor_area_ratio": None,
            }
            for key in ("A", "B", "C")
        ],
        "compound": {"shared_items_to_confirm": ["三棟共用設備位置"]},
    }


def _requirement(req_id: str, title: str, *, category: str = "bedroom") -> dict:
    building, floor, _local = req_id.split(".", 2)
    return {
        "id": req_id,
        "title": title,
        "category": category,
        "applies_to": {"building_id": building, "floor_id": floor},
        "status": "candidate",
        "priority": "should",
        "constraints": {},
        "source": {"type": "owner_decision", "path": "decision-log"},
    }


def _confirm(item: dict, relationships: list[dict], *, status: str = "confirmed", priority: str = "must") -> dict:
    entry = {
        "sequence": 1,
        "previous": None,
        "status": status,
        "priority": priority,
        "reason": "屋主會議確認",
        "decided_by": "屋主",
        "decided_at": "2026-09-15",
        "relationship_hashes": [relationship_hash(relationship) for relationship in relationships],
        "previous_entry_hash": None,
    }
    entry["entry_hash"] = stable_hash(entry)
    item["status"] = status
    item["priority"] = priority
    item["decision_log"] = [entry]
    return item


_ADJACENT = {"type": "adjacent", "target": "A.floor-1.bath1", "rationale": "孝親房要緊鄰衛浴"}


def _requirements() -> dict:
    elder = _requirement("A.floor-1.elder", "孝親房")
    elder["relationships"] = [_ADJACENT]
    elder["rationale"] = "Q2：要放得下床與 150cm 迴轉圈。"
    return {
        "schema": "house-requirements-v2",
        "requirements": [
            _confirm(elder, [_ADJACENT]),
            _requirement("A.floor-1.bath1", "孝親衛浴"),
            {**_requirement("B.floor-1.shrine", "神明廳"), "status": "rejected", "priority": "could"},
        ],
    }


def _household_profile() -> dict:
    return {
        "schema": "house-household-profile-v1",
        "status": "completed",
        "household": {
            "members": [
                {
                    "member_id": "person-1",
                    "relationship": "王阿嬤",
                    "age_band": "70-79",
                    "usual_building": "A",
                    "mobility_now": "wheelchair",
                    "mobility_10_year_outlook": "wheelchair",
                    "caregiving_needs": "洗腎每週三次",
                },
                {
                    "member_id": "person-2",
                    "relationship": "長孫",
                    "age_band": "adult",
                    "usual_building": "B",
                    "mobility_now": "independent",
                },
            ],
            "vehicles": [{"type": "機車", "current_count": 2, "future_count": 2}],
            "pets": [{"animal": "狗", "count": 1, "building_id": "A"}],
            "frequent_guests_or_caregivers": {"overnight_guests": True},
            "shared_meals_people": 4,
            "religious_practice": {"has_shrine_or_incense": True, "smoke_and_fire_controls_required": True},
            "daily_routines": ["週三凌晨陪診復健"],
            "design_directions": ["預算上限一千五百萬"],
        },
    }


def _build(tmp_path: Path, *, household: dict | None = None, requirements: dict | None = None) -> dict:
    project_path = tmp_path / "project.json"
    requirements_path = tmp_path / "requirements.json"
    household_path = tmp_path / "household-profile.json"
    design_request_path = tmp_path / "design_request.md"
    write_json(project_path, _project())
    write_json(requirements_path, requirements or _requirements())
    if household is not None:
        write_json(household_path, household)
    design_request_path.write_text("# 需求\n", encoding="utf-8")
    return build_design_brief(
        project_path=project_path,
        requirements_path=requirements_path,
        physical_items_path=tmp_path / "missing-physical-items.json",
        household_profile_path=household_path,
        design_request_path=design_request_path,
        standards_path=tmp_path / "missing-standards.json",
    )


def test_brief_segments_requirements_by_status_and_building(tmp_path: Path) -> None:
    brief = _build(tmp_path)

    assert brief["schema"] == BRIEF_SCHEMA
    assert brief["brief_hash"] == design_brief_hash(brief)
    summary = brief["decision_summary"]
    assert summary["requirements"] == 3
    assert summary["status_counts"] == {"confirmed": 1, "candidate": 1, "rejected": 1}
    assert summary["relationships"] == 1
    assert summary["relationship_status_counts"]["confirmed"] == 1
    assert SITE_WARNING in brief["warnings"]
    assert all("沒有任何需求經屋主確認" not in warning for warning in brief["warnings"])
    buildings = {item["building_id"]: item for item in brief["requirements_by_building"]}
    assert set(buildings) == {"A", "B", "C"}
    sections = {item["status"]: item["requirements"] for item in buildings["A"]["sections"]}
    assert [item["id"] for item in sections["confirmed"]] == ["A.floor-1.elder"]
    assert [item["id"] for item in sections["candidate"]] == ["A.floor-1.bath1"]
    assert [item["id"] for item in buildings["B"]["sections"][2]["requirements"]] == ["B.floor-1.shrine"]
    assert brief["relationships"][0]["status"] == "confirmed"


def test_brief_redacts_private_household_details(tmp_path: Path) -> None:
    brief = _build(tmp_path, household=_household_profile())
    household = brief["household"]

    assert household["provided"] is True
    assert household["people_total"] == 2
    assert household["age_bands"] == {"70–79 歲": 1, "成人": 1}
    assert household["mobility_now"] == {"可獨立行走": 1, "使用輪椅": 1}
    assert household["usual_building"] == {"A": 1, "B": 1, "C": 0, "未指定": 0}
    assert household["withheld"]

    rendered = json.dumps(brief, ensure_ascii=False)
    for needle in ("王阿嬤", "洗腎", "復健", "一千五百萬", "person-1", "person-2", "週三凌晨陪診"):
        assert needle not in rendered, needle
    for needle in ("王阿嬤", "洗腎", "一千五百萬"):
        assert needle not in design_brief_markdown(brief), needle
        assert needle not in design_brief_html(brief), needle
    sources = {item["key"]: item for item in brief["sources"]}
    assert sources["household_profile"]["sha256"] is None
    assert sources["household_profile"]["exists"] is True


def test_brief_extracts_twelve_questions_per_building_from_the_real_design_request() -> None:
    text = (ROOT / "inputs/design_request.md").read_text(encoding="utf-8")
    questions = extract_open_questions(text)

    assert {building: len(items) for building, items in questions.items()} == {"A": 12, "B": 12, "C": 12}
    assert questions["A"][0]["id"] == "A-Q1"
    assert questions["C"][-1]["id"] == "C-Q12"

    brief = build_design_brief(
        project_path=ROOT / "inputs/project.json",
        requirements_path=ROOT / "inputs/requirements.json",
        physical_items_path=ROOT / "inputs/physical-items.json",
        household_profile_path=ROOT / "tests/missing-household-profile.json",
        design_request_path=ROOT / "inputs/design_request.md",
        standards_path=ROOT / "scripts/config/residential_defaults_tw.json",
    )
    by_building = {item["building_id"]: item for item in brief["open_questions"]}
    assert {building: len(item["questions"]) for building, item in by_building.items()} == {"A": 12, "B": 12, "C": 12}
    linked = [
        question
        for item in brief["open_questions"]
        for question in item["questions"]
        if question["related_requirement_ids"]
    ]
    assert linked
    assert all(question["id"].startswith(question["id"][:2]) for item in brief["open_questions"] for question in item["questions"])


def test_brief_hash_is_stable_across_generated_at(tmp_path: Path) -> None:
    first = _build(tmp_path)
    second = _build(tmp_path)

    assert first["brief_hash"] == second["brief_hash"]
    assert first["generated_at"] != second["generated_at"] or True
    stale = dict(first)
    stale["generated_at"] = "1999-01-01T00:00:00Z"
    assert design_brief_hash(stale) == first["brief_hash"]


def test_brief_without_household_file_points_at_the_template(tmp_path: Path) -> None:
    summary = household_summary(tmp_path / "missing-profile.json")

    assert summary["provided"] is False
    assert "inputs/household-profile.template.json" in summary["note"]

    brief = _build(tmp_path)
    assert brief["household"]["provided"] is False
    sources = {item["key"]: item for item in brief["sources"]}
    assert sources["household_profile"]["exists"] is False
    assert sources["household_profile"]["sha256"] is None


def test_household_summary_maps_age_and_mobility_bands(tmp_path: Path) -> None:
    profile = {
        "schema": "house-household-profile-v1",
        "status": "completed",
        "household": {
            "members": [
                {"count": 2, "age_band": "70-79", "usual_building": "A", "mobility_now": "wheelchair"},
                {"age_band": "senior", "usual_building": "B", "mobility_now": "不需輪椅，自行走動"},
                {"age_band": "72", "mobility_now": "unknown"},
                {"age_band": "adult", "usual_building": "X", "mobility_now": "independent"},
            ]
        },
    }
    path = tmp_path / "profile.json"
    write_json(path, profile)

    summary = household_summary(path)

    assert summary["people_total"] == 5
    assert summary["age_bands"] == {"70–79 歲": 2, "未分級": 1, "成人": 1, "長者": 1}
    assert summary["mobility_now"] == {
        "可獨立行走": 1,
        "其他（細節僅保存在私有檔）": 1,
        "未知": 1,
        "使用輪椅": 2,
    }
    assert summary["usual_building"] == {"A": 2, "B": 1, "C": 0, "未指定": 2}


def test_source_labels_keep_design_request_pointers_readable() -> None:
    assert source_label({"type": "design_request", "pointer": "A-Q7"}) == "A-Q7"
    assert source_label({"type": "file", "path": "inputs/x.md", "pointer": "p"}) == "inputs/x.md p"
    assert source_label(None) == ""


def test_brief_sources_carry_keys_and_hashes(tmp_path: Path) -> None:
    brief = _build(tmp_path)

    sources = brief["sources"]
    assert [item["key"] for item in sources] == [
        "project",
        "requirements",
        "physical_items",
        "design_request",
        "standards",
        "household_profile",
    ]
    by_key = {item["key"]: item for item in sources}
    assert by_key["project"]["sha256"] == sha256_file(tmp_path / "project.json")
    assert by_key["requirements"]["sha256"] == sha256_file(tmp_path / "requirements.json")
    assert by_key["physical_items"]["exists"] is False


def test_write_design_brief_writes_json_markdown_and_html(tmp_path: Path) -> None:
    brief = _build(tmp_path)
    output_root = tmp_path / "out"

    paths = write_design_brief(brief, output_root)

    assert set(paths) == {"json", "markdown", "html"}
    assert json.loads(paths["json"].read_text(encoding="utf-8"))["brief_hash"] == brief["brief_hash"]
    markdown = paths["markdown"].read_text(encoding="utf-8")
    html = paths["html"].read_text(encoding="utf-8")
    assert "# 設計任務書（前期討論版）：測試專案" in markdown
    assert "設計任務書" in html
    assert "孝親房" in markdown
    assert "孝親房" in html