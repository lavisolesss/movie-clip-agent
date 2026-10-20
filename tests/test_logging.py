from __future__ import annotations

import asyncio
import json
import logging

from conftest import found_analysis, make_job, non_screen_analysis
from movie_agent import logs
from movie_agent.analyzer import analyze
from movie_agent.ledger import Ledger
from movie_agent.models import ImageFile
from movie_agent.pipeline import process_job
from movie_agent.queueing import JobQueue

GOOD = json.dumps(
    {
        "total_cost_usd": 0.0123,
        "num_turns": 3,
        "structured_output": {
            "images": [{"index": 1, "is_screen": True, "label": None}],
            "work": {
                "found": True, "title": "全面啟動", "original_title": "Inception", "year": 2010,
                "type": "電影", "scene": "", "characters": [], "confidence": "中", "basis": "",
            },
        },
    },
    ensure_ascii=False,
)


def _messages(caplog):
    return [r.getMessage() for r in caplog.records]


def test_success_path_is_fully_logged(settings, caplog):
    caplog.set_level(logging.INFO)

    async def fake_analyze(images, text, s):
        return found_analysis(n=2)

    asyncio.run(process_job(make_job(n_images=2), settings, Ledger(settings.ledger_path), analyze_fn=fake_analyze))
    text = "\n".join(_messages(caplog))
    for needle in ("下載完成：2 張", "分析結果：找到 全面啟動（Inception，2010，電影），信心 高",
                   "已存截圖：screenshots/", "已寫入 Excel：1 列，當日已找到作品數 1"):
        assert needle in text


def test_non_screen_result_is_logged(settings, caplog):
    caplog.set_level(logging.INFO)

    async def fake_analyze(images, text, s):
        return non_screen_analysis("馬克杯")

    asyncio.run(process_job(make_job(), settings, Ledger(settings.ledger_path), analyze_fn=fake_analyze))
    assert "第 1 張不是影視畫面，是 馬克杯" in "\n".join(_messages(caplog))


def test_failure_reason_is_logged_and_cleanup_noted(settings, caplog):
    caplog.set_level(logging.INFO)

    async def boom(images, text, s):
        raise RuntimeError("something odd")

    asyncio.run(process_job(make_job(), settings, Ledger(settings.ledger_path), analyze_fn=boom))
    text = "\n".join(_messages(caplog))
    assert "處理訊息時發生未預期的錯誤" in text and "已刪除這一則已存的 0 張截圖" in text
    assert any(r.exc_info for r in caplog.records)  # 完整的錯誤堆疊也有記


def test_claude_call_is_logged_with_turns_and_cost(settings, caplog):
    caplog.set_level(logging.INFO)

    async def runner(inv):
        return 0, GOOD, ""

    asyncio.run(analyze([ImageFile(b"x", ".jpg")], "", settings, claude_bin="claude", runner=runner))
    text = "\n".join(_messages(caplog))
    assert "呼叫 claude -p（第 1/2 次，模型 sonnet，1 張截圖，沒有文字）" in text
    assert "claude -p 完成：耗時" in text and "3 輪" in text and "$0.0123" in text


def test_bad_claude_output_is_logged_as_warning(settings, caplog):
    caplog.set_level(logging.INFO)

    async def runner(inv):
        return 0, "not json", ""

    try:
        asyncio.run(analyze([ImageFile(b"x", ".jpg")], "", settings, claude_bin="claude", runner=runner))
    except Exception:
        pass
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 2 and "不合格" in warnings[0].getMessage()


def test_tag_filter_adds_job_tag():
    flt = logs.TagFilter()
    rec = logging.LogRecord("x", logging.INFO, "f", 1, "hello", None, None)
    flt.filter(rec)
    assert rec.tag == ""
    token = logs.job_tag.set(logs.tag_for(1234567890123456789))
    try:
        flt.filter(rec)
        assert rec.tag == "[#456789] "
    finally:
        logs.job_tag.reset(token)


def test_setup_logging_writes_file_and_terminal_with_tag(tmp_path, capsys):
    path = tmp_path / "agent.log"
    handlers = logs.setup_logging(path)
    try:
        token = logs.job_tag.set("#111222")
        logging.getLogger("movie_agent.test").info("收到：測試")
        logs.job_tag.reset(token)
        logging.getLogger("movie_agent.test").info("沒有編號")
        for h in handlers:
            h.flush()
        content = path.read_text(encoding="utf-8")
        assert "movie_agent.test: [#111222] 收到：測試" in content
        assert "movie_agent.test: 沒有編號" in content
        assert "[#111222] 收到：測試" in capsys.readouterr().out  # 終端機也有
    finally:
        for h in handlers:
            logging.getLogger().removeHandler(h)
            h.close()


def test_job_tag_follows_into_threads():
    """寫 Excel 在 asyncio.to_thread 裡面，那裡的 log 也要帶著編號。"""
    seen = []

    async def go():
        token = logs.job_tag.set("#777888")
        try:
            await asyncio.to_thread(lambda: seen.append(logs.job_tag.get()))
        finally:
            logs.job_tag.reset(token)

    asyncio.run(go())
    assert seen == ["#777888"]


def test_queue_exposes_running_and_waiting():
    async def scenario():
        q = JobQueue()
        seen = {}

        async def handler(job):
            seen["running"], seen["waiting"] = q.running, q.waiting

        q.submit(make_job(uid=1))
        q.submit(make_job(uid=2))
        assert (q.running, q.waiting) == (0, 2)
        worker = asyncio.create_task(q.run(handler))
        await q._queue.join()
        worker.cancel()
        return seen, q.running

    seen, after = asyncio.run(scenario())
    assert seen["running"] == 1 and after == 0


def test_token_never_appears_in_logs(settings, caplog):
    caplog.set_level(logging.DEBUG)

    async def fake_analyze(images, text, s):
        return found_analysis()

    asyncio.run(process_job(make_job(), settings, Ledger(settings.ledger_path), analyze_fn=fake_analyze))
    assert settings.discord_token not in "\n".join(_messages(caplog))
    assert settings.discord_token not in repr(settings)
