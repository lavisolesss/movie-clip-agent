from __future__ import annotations

import pytest

from movie_agent.bot import classify


@pytest.mark.parametrize(
    "types, text, expected",
    [
        (["image/png"], "", "images"),
        (["image/png", "video/mp4"], "台詞", "images"),  # 有圖片就用圖片，影片略過
        (["image/heic"], "", "images"),  # 交給後面回覆「格式不支援」
        (["video/mp4"], "", "video"),
        (["video/mp4"], "這段出自哪裡", "video"),
        ([], "人生就像一盒巧克力", "text"),
        ([], "嗯", "ignore"),  # 太短，不查
        ([], "   ", "ignore"),
        (["application/pdf"], "幫我查這個", "ignore"),
        ([], "", "ignore"),
    ],
)
def test_classify(types, text, expected):
    assert classify(types, text) == expected
