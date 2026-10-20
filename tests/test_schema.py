from __future__ import annotations

import json

import pytest

from movie_agent.schema import AnalysisError, parse_claude_output, validate_analysis


def _wrap(structured: object = None, result: object = None, **extra) -> str:
    outer = {"is_error": False, "type": "result", **extra}
    if structured is not None:
        outer["structured_output"] = structured
    if result is not None:
        outer["result"] = result
    return json.dumps(outer, ensure_ascii=False)


WORK = {
    "found": True, "title": "全面啟動", "original_title": "Inception", "year": 2010, "type": "電影",
    "scene": "柯柏在旋轉走廊打鬥", "characters": ["亞瑟"], "confidence": "高", "basis": "字幕與場景",
}
FOUND = {"images": [{"index": 1, "is_screen": True, "label": None}], "work": WORK}
NOT_SCREEN = {"images": [{"index": 1, "is_screen": False, "label": "一隻貓"}], "work": None}


def _copy(data):
    return json.loads(json.dumps(data, ensure_ascii=False))


def test_valid_found():
    a = parse_claude_output(_wrap(FOUND), 1, False)
    assert a.work and a.work.found and a.work.title == "全面啟動" and a.work.year == 2010
    assert a.work.type == "電影" and a.work.confidence == "高"
    assert a.images[0].is_screen


def test_valid_not_screen():
    a = parse_claude_output(_wrap(NOT_SCREEN), 1, False)
    assert a.work is None
    assert a.images[0].label == "一隻貓"


def test_text_only_query():
    a = validate_analysis({"images": [], "work": WORK}, 0, True)
    assert a.images == () and a.work.title == "全面啟動"


def test_text_only_requires_work():
    with pytest.raises(AnalysisError):
        validate_analysis({"images": [], "work": None}, 0, True)


def test_non_screen_image_with_text_still_needs_work():
    data = {"images": [{"index": 1, "is_screen": False, "label": "貓"}], "work": WORK}
    a = validate_analysis(data, 1, True)
    assert a.work.found and not a.images[0].is_screen


def test_not_found_drops_title_and_keeps_reason():
    data = _copy(FOUND)
    data["work"].update(found=False, title="亂猜的片名", year=1999, type="電影", basis="畫面太暗")
    w = validate_analysis(data, 1, False).work
    assert not w.found and w.title == "" and w.year is None and w.type == "" and w.confidence == ""
    assert w.basis == "畫面太暗"


def test_not_found_without_reason_gets_default():
    data = _copy(FOUND)
    data["work"].update(found=False, basis="")
    assert validate_analysis(data, 1, False).work.basis == "沒有足夠的線索"


def test_non_screen_without_label_gets_default():
    data = {"images": [{"index": 1, "is_screen": False, "label": None}], "work": None}
    assert validate_analysis(data, 1, False).images[0].label == "不明圖片"


def test_screen_label_is_ignored():
    data = _copy(FOUND)
    data["images"][0]["label"] = "電影畫面"
    assert validate_analysis(data, 1, False).images[0].label == ""


def test_year_string_and_null_are_accepted():
    data = _copy(FOUND)
    data["work"]["year"] = "2010"
    assert validate_analysis(data, 1, False).work.year == 2010
    data["work"]["year"] = None
    assert validate_analysis(data, 1, False).work.year is None


@pytest.mark.parametrize("bad", ["約 2010", "2010年", "N/A", True, 1500, 99999, 2010.5, float("inf"), float("nan"), [2010]])
def test_bad_years_are_rejected(bad):
    data = _copy(FOUND)
    data["work"]["year"] = bad
    with pytest.raises(AnalysisError):
        validate_analysis(data, 1, False)


def test_unknown_type_becomes_other():
    data = _copy(FOUND)
    data["work"]["type"] = "短片"
    assert validate_analysis(data, 1, False).work.type == "其他"


@pytest.mark.parametrize("bad", ["很高", "", None, 1, "high"])
def test_bad_confidence_is_rejected(bad):
    data = _copy(FOUND)
    data["work"]["confidence"] = bad
    with pytest.raises(AnalysisError):
        validate_analysis(data, 1, False)


def test_found_requires_title():
    data = _copy(FOUND)
    data["work"]["title"] = "   "
    with pytest.raises(AnalysisError):
        validate_analysis(data, 1, False)


def test_mixed_images():
    data = {
        "images": [
            {"index": 2, "is_screen": False, "label": "貓"},
            {"index": 1, "is_screen": True, "label": None},
        ],
        "work": WORK,
    }
    a = validate_analysis(data, 2, False)
    assert [p.index for p in a.images] == [1, 2]  # 依編號排序


@pytest.mark.parametrize(
    "data",
    [
        {"images": [], "work": None},  # 張數對不上
        {"images": [{"index": 1, "is_screen": True, "label": None}], "work": None},  # 有截圖卻沒有 work
        {"images": [{"index": 1, "is_screen": False, "label": "貓"}], "work": WORK},  # 沒東西可查卻有 work
        {"images": [{"index": 2, "is_screen": False, "label": "貓"}], "work": None},  # 編號不對
        {"images": [{"index": 1, "is_screen": "yes", "label": None}], "work": None},  # is_screen 不是布林
        {"images": "oops", "work": None},
        {"images": [{"index": 1, "is_screen": True, "label": None}], "work": {**WORK, "found": "yes"}},
        {"images": [{"index": 1, "is_screen": True, "label": None}], "work": {**WORK, "title": 5}},
        {"images": [{"index": 1, "is_screen": True, "label": None}], "work": {**WORK, "characters": "亞瑟"}},
    ],
)
def test_structure_errors(data):
    with pytest.raises(AnalysisError):
        validate_analysis(data, 1, False)


@pytest.mark.parametrize("raw", ["", "not json", "[1,2]", "null", "{", '{"is_error": true, "result": "boom"}'])
def test_outer_output_errors(raw):
    with pytest.raises(AnalysisError):
        parse_claude_output(raw, 1, False)


def test_fallback_to_result_text_with_code_fence():
    text = "```json\n" + json.dumps(FOUND, ensure_ascii=False) + "\n```"
    a = parse_claude_output(_wrap(result=text), 1, False)
    assert a.work.title == "全面啟動"


def test_fallback_finds_json_inside_prose():
    text = "好的，結果如下：" + json.dumps(NOT_SCREEN, ensure_ascii=False) + " 以上。"
    assert parse_claude_output(_wrap(result=text), 1, False).work is None


def test_no_structured_and_no_result():
    with pytest.raises(AnalysisError):
        parse_claude_output(_wrap(), 1, False)


def test_text_is_cleaned_and_truncated():
    data = _copy(FOUND)
    data["work"]["title"] = "全\n面\x00啟動" + "很長" * 50
    data["work"]["characters"] = ["  柯  柏 ", "", "x" * 100] + [f"角色{i}" for i in range(20)]
    w = validate_analysis(data, 1, False).work
    assert "\n" not in w.title and "\x00" not in w.title
    assert len(w.title) <= 40
    assert w.characters[0] == "柯 柏"
    assert all(len(c) <= 20 for c in w.characters) and len(w.characters) == 10
