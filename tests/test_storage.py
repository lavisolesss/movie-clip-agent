from __future__ import annotations

from datetime import datetime

import pytest

from movie_agent.storage import (
    StorageError,
    delete_files,
    relative_to_data_dir,
    sanitize_name,
    save_image,
)

WHEN = datetime(2026, 10, 15, 12, 30, 45)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("全面啟動", "全面啟動"),
        ("The Dark Knight", "The_Dark_Knight"),
        ("a/b\\c:d*e?f\"g<h>i|j", "a_b_c_d_e_f_g_h_i_j"),
        ("..\\..\\Windows\\evil", "Windows_evil"),
        ("../../etc/passwd", "etc_passwd"),
        ("C:\\x.jpg", "C_x_jpg"),
        ("", "未命名"),
        ("....", "未命名"),
        ("///", "未命名"),
        ("CON", "_CON"),
        ("com1", "_com1"),
        ("星際大戰：曙光乍現", "星際大戰_曙光乍現"),  # 全形冒號（片名很常見）
        ("x" * 100, "x" * 40),
    ],
)
def test_sanitize_name(raw, expected):
    assert sanitize_name(raw) == expected


def test_save_image_basic_name(settings):
    p = save_image(b"abc", ".jpg", WHEN, "全面啟動", settings.screenshots_dir)
    assert p.name == "2026-10-15 12-30-45 全面啟動.jpg"
    assert p.read_bytes() == b"abc"
    assert relative_to_data_dir(p, settings.data_dir) == "screenshots/2026-10-15 12-30-45 全面啟動.jpg"


def test_same_second_collision_adds_suffix(settings):
    names = [save_image(b"x", ".jpg", WHEN, "全面啟動", settings.screenshots_dir).name for _ in range(3)]
    assert names == [
        "2026-10-15 12-30-45 全面啟動.jpg",
        "2026-10-15 12-30-45 全面啟動-2.jpg",
        "2026-10-15 12-30-45 全面啟動-3.jpg",
    ]


def test_collision_does_not_overwrite(settings):
    first = save_image(b"first", ".jpg", WHEN, "x", settings.screenshots_dir)
    save_image(b"second", ".jpg", WHEN, "x", settings.screenshots_dir)
    assert first.read_bytes() == b"first"


@pytest.mark.parametrize("evil", ["..\\..\\evil", "../../evil", "C:\\Windows\\evil", "a/b/c", "..", "x\x00y"])
def test_path_tricks_stay_inside_screenshots_dir(settings, evil):
    p = save_image(b"x", ".jpg", WHEN, evil, settings.screenshots_dir)
    assert p.resolve().parent == settings.screenshots_dir.resolve()
    # 截圖資料夾之外沒有多出任何檔案
    outside = [f for f in settings.data_dir.rglob("*") if f.is_file() and f.parent != settings.screenshots_dir]
    assert outside == []


def test_extension_whitelist(settings):
    with pytest.raises(StorageError):
        save_image(b"x", ".exe", WHEN, "x", settings.screenshots_dir)
    p = save_image(b"x", ".PNG", WHEN, "x", settings.screenshots_dir)
    assert p.suffix == ".png"


def test_delete_files(settings):
    p = save_image(b"x", ".jpg", WHEN, "x", settings.screenshots_dir)
    delete_files([p, settings.screenshots_dir / "not-there.jpg"])
    assert not p.exists()
