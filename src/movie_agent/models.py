"""在各模組之間傳遞的資料型別。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class ImageFile:
    """一張已經下載好的截圖。ext 是白名單內的副檔名，例如 ".jpg"。"""

    data: bytes
    ext: str


class ImageSource(Protocol):
    """一張還沒下載的截圖（Discord 的一個附件）。"""

    ext: str
    size: int

    async def read(self) -> bytes: ...


@dataclass
class Job:
    """一則訊息 = 一個查詢。一則訊息裡的多張截圖和文字，合起來找一部作品。"""

    sources: list[ImageSource]  # 可以是空的：只有文字（台詞）的查詢
    text: str  # 上傳者在訊息裡打的字（台詞或補充說明）。只當資料，見防護 2
    uploader_name: str
    uploader_id: int
    when: datetime  # 訊息送出的時間（本機時區）
    truncated: bool = False  # 超過張數上限，後面的截圖沒有處理
    ref: Any = None  # Discord 那一端用的（原訊息），pipeline 不使用
    message_id: int = 0  # 用來產生 log 裡的 [#編號]
    received_at: float = 0.0  # 收到的時間（time.monotonic），算排隊等了多久
