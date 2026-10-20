from __future__ import annotations

from conftest import found_analysis, found_work, non_screen_analysis, not_found_work
from movie_agent import config, replies
from movie_agent.schema import Analysis, ImageVerdict


def test_found_reply_has_every_required_part():
    text = replies.build_success("<@1>", found_analysis(), 1234, False)
    for needle in ("找到了：《全面啟動》（Inception，2010，電影）", "片段：柯柏在旋轉的走廊裡和保鏢打鬥",
                   "角色：亞瑟", "信心程度：高", "判斷依據：", "今天頻道裡已找到 1,234 部作品", "可能有誤"):
        assert needle in text


def test_not_found_reply():
    text = replies.build_success("<@1>", Analysis((ImageVerdict(1, True, ""),), not_found_work()), 3, False)
    assert "沒有找到確定的作品。" in text and "說明：畫面太暗，看不出線索" in text
    assert "找到了" not in text and "今天頻道裡已找到 3 部作品" in text


def test_non_screen_reply():
    text = replies.build_success("<@1>", non_screen_analysis("一隻貓"), 0, False)
    assert "你傳的不是影視畫面，是一隻貓。" in text and "今天頻道裡已找到 0 部作品" in text
    assert "信心程度" not in text


def test_mixed_reply_numbers_the_images():
    analysis = Analysis(
        images=(ImageVerdict(1, True, ""), ImageVerdict(2, False, "手機桌面")),
        work=found_work(),
    )
    text = replies.build_success("<@1>", analysis, 1, False)
    assert "截圖（第 1 張）找到了" in text and "第 2 張不是影視畫面，是手機桌面。" in text


def test_markdown_and_mentions_from_model_are_neutralised():
    text = replies.build_success("<@1>", found_analysis(title="@everyone **粗體** [x](http://evil.example)"), 1, False)
    assert "@everyone" not in text.replace("@​everyone", "")
    assert "**粗體**" not in text
    assert "\\[x]" in text  # [ 前面有跳脫符號，不會變成可點的連結


def test_reply_never_exceeds_discord_limit():
    long_label = "字" * 5000
    big = Analysis(images=tuple(ImageVerdict(i, False, long_label) for i in range(1, 6)), work=None)
    assert len(replies.build_success("<@1>", big, 0, False)) <= config.DISCORD_MESSAGE_MAX_CHARS
