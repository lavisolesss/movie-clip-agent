"""回覆上傳者的文字（docs/architecture.md 第 10 節）。"""

from __future__ import annotations

import discord

from movie_agent import config
from movie_agent.schema import Analysis, Work

FAIL_ANALYSIS = "查詢失敗，請再傳一次"
FAIL_FORMAT = "這個圖片格式我讀不了（支援 JPG、PNG、WebP、GIF）。沒有記錄。"
FAIL_TOO_BIG = f"檔案太大（上限 {config.MAX_FILE_BYTES // (1024 * 1024)} MB），沒有記錄。"
FAIL_VIDEO = "目前不支援影片。請截一張最有特色的畫面（有字幕更好），或直接打出台詞再傳。沒有記錄。"
FAIL_LEDGER = "記錄檔現在寫不進去，這次沒有記錄。請稍後重傳。"
REJECT_QUEUE_FULL = "目前排隊的人太多，這則沒有收。請稍後再傳。"
REJECT_USER_LIMIT = f"你還有 {config.PER_USER_MAX} 則在查詢中，請等查完再傳。"


def _esc(text: str) -> str:
    """模型產生的文字放進回覆前，先把 Discord 的格式符號和 @ 提及處理掉。"""
    return discord.utils.escape_mentions(discord.utils.escape_markdown(text, ignore_links=False))


def _title_line(work: Work) -> str:
    extra = [p for p in (_esc(work.original_title), str(work.year) if work.year else "", work.type) if p]
    return f"《{_esc(work.title)}》" + (f"（{'，'.join(extra)}）" if extra else "")


def build_success(mention: str, analysis: Analysis, found_today: int, truncated: bool) -> str:
    multi = len(analysis.images) > 1
    screen_idx = [p.index for p in analysis.images if p.is_screen]
    non_screen = [p for p in analysis.images if not p.is_screen]

    lines = [mention]
    work = analysis.work
    if work is not None:
        prefix = f"截圖（第 {'、'.join(map(str, screen_idx))} 張）" if multi and screen_idx else ""
        if work.found:
            lines.append(f"{prefix}找到了：{_title_line(work)}")
            if work.scene:
                lines.append(f"片段：{_esc(work.scene)}")
            if work.characters:
                lines.append(f"角色：{'、'.join(_esc(c) for c in work.characters)}")
            lines.append(f"信心程度：{work.confidence}")
            if work.basis:
                lines.append(f"判斷依據：{_esc(work.basis)}")
        else:
            lines.append(f"{prefix}沒有找到確定的作品。")
            lines.append(f"說明：{_esc(work.basis)}")
            if work.scene:
                lines.append(f"畫面看起來是：{_esc(work.scene)}")
    for p in non_screen:
        if multi:
            lines.append(f"第 {p.index} 張不是影視畫面，是{_esc(p.label)}。")
        else:
            lines.append(f"你傳的不是影視畫面，是{_esc(p.label)}。")
    if non_screen:
        lines.append("不是影視畫面的圖片已存檔，沒有拿去查詢。")

    lines.append(f"今天頻道裡已找到 {found_today:,} 部作品（整個頻道今天的合計）")
    if work is not None and work.found:
        lines.append("（結果由 AI 判斷並上網查證，仍可能有誤）")
    if truncated:
        lines.append(f"一次最多處理 {config.MAX_IMAGES_PER_MESSAGE} 張，其餘沒有處理。")

    text = "\n".join(lines)
    limit = config.DISCORD_MESSAGE_MAX_CHARS - 10
    return text if len(text) <= limit else text[:limit] + "…"
