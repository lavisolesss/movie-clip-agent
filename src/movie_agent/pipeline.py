"""處理一則訊息的完整流程：下載 → 查詢 → 存截圖 → 建檔 → 組回覆（docs/architecture.md 第 4 節）。

這裡不碰 Discord，只回傳「成功或失敗」加「要回覆的文字」，所以可以不連 Discord 就測試。
任何一步失敗都走同一條路：刪掉這一則已存的截圖、Excel 不新增列、回覆失敗訊息。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from movie_agent import config, replies
from movie_agent.analyzer import analyze
from movie_agent.config import Settings
from movie_agent.ledger import (
    RESULT_FOUND,
    RESULT_NOT_FOUND,
    RESULT_NOT_SCREEN,
    Ledger,
    LedgerBusyError,
    LedgerError,
    LedgerRow,
)
from movie_agent.models import ImageFile, Job
from movie_agent.schema import Analysis, AnalysisError, clean_text
from movie_agent.storage import StorageError, delete_files, relative_to_data_dir, save_image

log = logging.getLogger("movie_agent.pipeline")

AnalyzeFn = Callable[[list[ImageFile], str, Settings], Awaitable[Analysis]]


@dataclass(frozen=True)
class Outcome:
    ok: bool
    text: str


def query_type(n_images: int, has_text: bool) -> str:
    if n_images and has_text:
        return "截圖+文字"
    return "截圖" if n_images else "文字"


async def process_job(
    job: Job,
    settings: Settings,
    ledger: Ledger,
    analyze_fn: AnalyzeFn = analyze,
) -> Outcome:
    saved: list[Path] = []
    mention = f"<@{job.uploader_id}>"
    when = job.when.astimezone().replace(tzinfo=None)  # 本機時間，Excel 不收帶時區的時間
    text = clean_text(job.text, config.TEXT_MAX_CHARS)
    try:
        images = [ImageFile(data=await s.read(), ext=s.ext) for s in job.sources]
        if images:
            log.info("下載完成：%d 張，共 %.0f KB", len(images), sum(len(p.data) for p in images) / 1024)

        try:
            analysis = await analyze_fn(images, job.text, settings)
        except AnalysisError as exc:
            log.error("查詢失敗（上傳者 %s）：%s", job.uploader_id, exc)
            return Outcome(False, replies.FAIL_ANALYSIS)

        work = analysis.work
        for verdict in analysis.images:
            if not verdict.is_screen:
                log.info("分析結果：第 %d 張不是影視畫面，是 %s", verdict.index, verdict.label)
        if work is not None:
            if work.found:
                log.info(
                    "分析結果：找到 %s（%s，%s，%s），信心 %s",
                    work.title, work.original_title or "-", work.year or "年份不明", work.type, work.confidence,
                )
            else:
                log.info("分析結果：找不到作品，原因：%s", work.basis)

        rows: list[LedgerRow] = []
        screen_rel: list[str] = []
        non_screen_rows: list[LedgerRow] = []
        screen_name = work.title if work is not None and work.found else "未找到"
        for verdict, image in zip(analysis.images, images):
            if verdict.is_screen:
                path = save_image(image.data, image.ext, when, screen_name, settings.screenshots_dir)
                saved.append(path)
                screen_rel.append(relative_to_data_dir(path, settings.data_dir))
                log.info("已存截圖：%s", screen_rel[-1])
            else:
                path = save_image(
                    image.data, image.ext, when, f"不是影視畫面_{verdict.label}", settings.screenshots_dir
                )
                saved.append(path)
                rel = relative_to_data_dir(path, settings.data_dir)
                log.info("已存截圖：%s", rel)
                non_screen_rows.append(
                    LedgerRow(
                        when=when,
                        uploader=job.uploader_name,
                        query_type="截圖",
                        query_text="",
                        result=RESULT_NOT_SCREEN,
                        scene=verdict.label,
                        image_paths=[rel],
                    )
                )
        if work is not None:
            n_screens = sum(1 for v in analysis.images if v.is_screen)
            rows.append(
                LedgerRow(
                    when=when,
                    uploader=job.uploader_name,
                    query_type=query_type(n_screens, bool(text)),
                    query_text=text,
                    result=RESULT_FOUND if work.found else RESULT_NOT_FOUND,
                    title=work.title,
                    original_title=work.original_title,
                    year=work.year,
                    work_type=work.type,
                    scene=work.scene if work.found else work.basis,
                    confidence=work.confidence,
                    image_paths=screen_rel,
                )
            )
        rows += non_screen_rows

        try:
            total = await asyncio.to_thread(ledger.append, rows)
        except LedgerBusyError as exc:
            log.error("%s", exc)
            delete_files(saved)
            log.info("已刪除這一則已存的 %d 張截圖", len(saved))
            return Outcome(False, replies.FAIL_LEDGER)
        log.info("已寫入 Excel：%d 列，當日已找到作品數 %d", len(rows), total)

        reply = replies.build_success(mention, analysis, total, job.truncated)
        return Outcome(True, reply)

    except (LedgerError, StorageError) as exc:
        log.error("建檔失敗（上傳者 %s）：%s", job.uploader_id, exc)
        delete_files(saved)
        log.info("已刪除這一則已存的 %d 張截圖", len(saved))
        return Outcome(False, replies.FAIL_ANALYSIS)
    except Exception:
        log.exception("處理訊息時發生未預期的錯誤（上傳者 %s）", job.uploader_id)
        delete_files(saved)
        log.info("已刪除這一則已存的 %d 張截圖", len(saved))
        return Outcome(False, replies.FAIL_ANALYSIS)
