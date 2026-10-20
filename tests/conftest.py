from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from movie_agent.config import Settings, ensure_dirs
from movie_agent.models import Job
from movie_agent.schema import Analysis, ImageVerdict, Work


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    s = Settings(
        discord_token="TEST-TOKEN-NOT-REAL",
        channel_id=123,
        claude_model="sonnet",
        data_dir=tmp_path / "movie-data",
    )
    ensure_dirs(s)
    return s


class FakeImage:
    def __init__(self, data: bytes = b"\xff\xd8\xff fake jpeg", ext: str = ".jpg"):
        self._data = data
        self.ext = ext
        self.size = len(data)

    async def read(self) -> bytes:
        return self._data


def make_job(n_images: int = 1, text: str = "", name: str = "小明", uid: int = 1,
             when: datetime | None = None, truncated: bool = False) -> Job:
    return Job(
        sources=[FakeImage() for _ in range(n_images)],
        text=text,
        uploader_name=name,
        uploader_id=uid,
        when=(when or datetime(2026, 10, 15, 12, 30, 45)).astimezone(),
        truncated=truncated,
    )


def found_work(title: str = "全面啟動") -> Work:
    return Work(
        found=True, title=title, original_title="Inception", year=2010, type="電影",
        scene="柯柏在旋轉的走廊裡和保鏢打鬥", characters=("亞瑟",), confidence="高",
        basis="走廊旋轉的場景與字幕對得上",
    )


def not_found_work() -> Work:
    return Work(
        found=False, title="", original_title="", year=None, type="",
        scene="", characters=(), confidence="", basis="畫面太暗，看不出線索",
    )


def found_analysis(title: str = "全面啟動", n: int = 1) -> Analysis:
    return Analysis(images=tuple(ImageVerdict(i, True, "") for i in range(1, n + 1)), work=found_work(title))


def text_only_analysis(title: str = "阿甘正傳") -> Analysis:
    return Analysis(images=(), work=found_work(title))


def non_screen_analysis(label: str = "一隻貓") -> Analysis:
    return Analysis(images=(ImageVerdict(1, False, label),), work=None)
