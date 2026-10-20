"""claude -p 的回覆格式，以及解析與驗證（docs/architecture.md 第 5 節）。

原則：任何不合格的輸出都丟出 AnalysisError，由呼叫端決定重試或回覆失敗，
不可以讓程式當掉，也不可以把不合格的結果寫進 Excel。
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass

from movie_agent import config


class AnalysisError(Exception):
    """分析失敗（呼叫失敗、逾時、輸出不合格）。訊息只寫進 log，不顯示給上傳者。"""


# 傳給 claude -p --json-schema 的格式
RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "images": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "is_screen": {"type": "boolean"},
                    "label": {"type": ["string", "null"]},
                },
                "required": ["index", "is_screen", "label"],
            },
        },
        "work": {
            "type": ["object", "null"],
            "properties": {
                "found": {"type": "boolean"},
                "title": {"type": ["string", "null"]},
                "original_title": {"type": ["string", "null"]},
                "year": {"type": ["integer", "null"]},
                "type": {"type": ["string", "null"], "enum": [*config.WORK_TYPES, None]},
                "scene": {"type": "string"},
                "characters": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "string", "enum": list(config.CONFIDENCE_LEVELS)},
                "basis": {"type": "string"},
            },
            "required": [
                "found", "title", "original_title", "year", "type",
                "scene", "characters", "confidence", "basis",
            ],
        },
    },
    "required": ["images", "work"],
}


@dataclass(frozen=True)
class ImageVerdict:
    index: int  # 從 1 開始
    is_screen: bool  # 是不是影視作品的畫面
    label: str  # 不是影視畫面時：它是什麼。是的話：空字串


@dataclass(frozen=True)
class Work:
    found: bool
    title: str  # 找不到時是空字串
    original_title: str
    year: int | None
    type: str  # WORK_TYPES 其中之一；找不到時是空字串
    scene: str  # 片段說明
    characters: tuple[str, ...]
    confidence: str  # 高、中、低；找不到時是空字串
    basis: str  # 判斷依據；找不到時是「為什麼找不到」


@dataclass(frozen=True)
class Analysis:
    images: tuple[ImageVerdict, ...]  # 依 index 排序
    work: Work | None  # 截圖加文字一起查出來的作品；沒有可以查的東西時是 None


def clean_text(value: str, max_chars: int) -> str:
    """去掉控制字元（換行變空白）、壓縮空白、前後去空白、截斷。"""
    out = []
    for ch in value:
        if unicodedata.category(ch) in ("Cc", "Cf", "Cs", "Co", "Cn"):
            out.append(" ")
        else:
            out.append(ch)
    text = re.sub(r"\s+", " ", "".join(out)).strip()
    return text[:max_chars].strip()


def _to_year(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise AnalysisError("work.year 是 true/false，不是年份")
    if isinstance(value, (int, float)):
        num = float(value)
    elif isinstance(value, str):
        text = value.strip()
        if not re.fullmatch(r"\d{4}", text):
            raise AnalysisError(f"work.year 不是年份：{text[:30]!r}")
        num = float(text)
    else:
        raise AnalysisError("work.year 不是年份")
    if not math.isfinite(num) or num != int(num):
        raise AnalysisError("work.year 不是整數")
    year = int(num)
    lo, hi = config.YEAR_RANGE
    if not lo <= year <= hi:
        raise AnalysisError(f"work.year 超出合理範圍 {lo}~{hi}：{year}")
    return year


def _opt_text(raw: dict, key: str, max_chars: int) -> str:
    value = raw.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise AnalysisError(f"work.{key} 不是文字")
    return clean_text(value, max_chars)


def _extract_json_text(text: object) -> dict:
    """結構化欄位不存在時的備案：從文字結果裡找出第一段 JSON。"""
    if not isinstance(text, str):
        raise AnalysisError("輸出裡沒有結構化結果，也沒有文字結果")
    body = text.strip()
    body = re.sub(r"^```(?:json)?\s*|\s*```$", "", body, flags=re.IGNORECASE)
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        start, end = body.find("{"), body.rfind("}")
        if start < 0 or end <= start:
            raise AnalysisError("文字結果裡找不到 JSON") from None
        try:
            data = json.loads(body[start : end + 1])
        except json.JSONDecodeError as exc:
            raise AnalysisError(f"文字結果不是合法 JSON：{exc}") from None
    if not isinstance(data, dict):
        raise AnalysisError("JSON 最外層不是物件")
    return data


def parse_claude_output(raw: str, n_images: int, has_text: bool) -> Analysis:
    if len(raw) > config.CLAUDE_OUTPUT_MAX_CHARS:
        raise AnalysisError("claude 的輸出太長")
    try:
        outer = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AnalysisError(f"claude 的外層輸出不是合法 JSON：{exc}") from None
    if not isinstance(outer, dict):
        raise AnalysisError("claude 的外層輸出不是 JSON 物件")
    if outer.get("is_error"):
        raise AnalysisError(f"claude 回報錯誤：{str(outer.get('result'))[:200]}")

    data = outer.get("structured_output")
    if not isinstance(data, dict):
        data = _extract_json_text(outer.get("result"))
    return validate_analysis(data, n_images, has_text)


def validate_analysis(data: dict, n_images: int, has_text: bool) -> Analysis:
    images_raw = data.get("images")
    if not isinstance(images_raw, list) or len(images_raw) != n_images:
        raise AnalysisError(f"images 的數量和截圖張數 {n_images} 對不上")

    verdicts: list[ImageVerdict] = []
    for item in images_raw:
        if not isinstance(item, dict):
            raise AnalysisError("images 裡有不是物件的項目")
        index = item.get("index")
        if isinstance(index, bool) or not isinstance(index, int):
            raise AnalysisError("images[].index 不是整數")
        is_screen = item.get("is_screen")
        if not isinstance(is_screen, bool):
            raise AnalysisError("images[].is_screen 不是 true/false")
        label_raw = item.get("label")
        if label_raw is not None and not isinstance(label_raw, str):
            raise AnalysisError("images[].label 不是文字")
        if is_screen:
            label = ""
        else:
            label = clean_text(label_raw or "", config.LABEL_MAX_CHARS) or "不明圖片"
        verdicts.append(ImageVerdict(index=index, is_screen=is_screen, label=label))

    if sorted(v.index for v in verdicts) != list(range(1, n_images + 1)):
        raise AnalysisError("images 的編號沒有剛好涵蓋 1 到張數")
    verdicts.sort(key=lambda v: v.index)

    # 有影視截圖、或有上傳者的文字，就有東西可以查，work 一定要有；兩者都沒有時 work 必須是 null
    work_raw = data.get("work")
    has_query = has_text or any(v.is_screen for v in verdicts)
    if has_query:
        if not isinstance(work_raw, dict):
            raise AnalysisError("有可以查的截圖或文字，但 work 不是物件")
        work = _validate_work(work_raw)
    else:
        if work_raw is not None:
            raise AnalysisError("沒有影視截圖也沒有文字，但 work 不是 null")
        work = None
    return Analysis(images=tuple(verdicts), work=work)


def _validate_work(raw: dict) -> Work:
    found = raw.get("found")
    if not isinstance(found, bool):
        raise AnalysisError("work.found 不是 true/false")

    scene = _opt_text(raw, "scene", config.SCENE_MAX_CHARS)
    basis = _opt_text(raw, "basis", config.BASIS_MAX_CHARS)

    characters_raw = raw.get("characters", [])
    if characters_raw is None:
        characters_raw = []
    if not isinstance(characters_raw, list):
        raise AnalysisError("work.characters 不是清單")
    characters: list[str] = []
    for item in characters_raw:
        if not isinstance(item, str):
            raise AnalysisError("work.characters 裡有不是文字的項目")
        cleaned = clean_text(item, config.CHARACTER_MAX_CHARS)
        if cleaned:
            characters.append(cleaned)
    characters = characters[: config.CHARACTER_MAX_ITEMS]

    if not found:
        # 找不到時，名稱、年份、類型、信心一律不採用，只留說明
        return Work(
            found=False, title="", original_title="", year=None, type="",
            scene=scene, characters=(), confidence="", basis=basis or "沒有足夠的線索",
        )

    title = _opt_text(raw, "title", config.TITLE_MAX_CHARS)
    if not title:
        raise AnalysisError("work.found 是 true，但 title 是空的")
    original_title = _opt_text(raw, "original_title", config.ORIGINAL_TITLE_MAX_CHARS)
    year = _to_year(raw.get("year"))

    work_type = raw.get("type")
    if work_type not in config.WORK_TYPES:
        if work_type is not None and not isinstance(work_type, str):
            raise AnalysisError("work.type 不是文字")
        work_type = "其他"  # 模型自創的類型一律歸到「其他」

    confidence = raw.get("confidence")
    if confidence not in config.CONFIDENCE_LEVELS:
        raise AnalysisError(f"work.confidence 必須是 高/中/低：{str(confidence)[:20]!r}")

    return Work(
        found=True, title=title, original_title=original_title, year=year, type=work_type,
        scene=scene, characters=tuple(characters), confidence=confidence, basis=basis,
    )
