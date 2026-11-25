"""A build profile can fix the PDF mode used by targets that name none."""

from __future__ import annotations

import json

import pytest

from iasp_tooling import build_book


@pytest.fixture
def profiles(tmp_path, monkeypatch):
    path = tmp_path / "build-profiles.json"
    path.write_text(
        json.dumps(
            {
                "default": {"order_file": "book-order.txt"},
                "annex": {"order_file": "annex-order.txt", "pdf_mode": "screen"},
                "kdp": {"order_file": "book-order.txt", "pdf_mode": "print"},
                "bad": {"order_file": "book-order.txt", "pdf_mode": "a4"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(build_book, "BUILD_PROFILES_FILE", path)
    monkeypatch.setattr(build_book, "PROFILE", None)
    return path


def test_pdf_mode_is_read_from_profile(profiles):
    assert build_book.load_build_profile("annex").pdf_mode == "screen"
    assert build_book.load_build_profile("kdp").pdf_mode == "print"
    assert build_book.load_build_profile("default").pdf_mode is None


def test_invalid_pdf_mode_stops_the_build(profiles, capsys):
    with pytest.raises(SystemExit):
        build_book.load_build_profile("bad")
    assert "pdf_mode 'a4'" in capsys.readouterr().out


def test_target_without_mode_uses_profile_mode(profiles, monkeypatch):
    monkeypatch.setattr(build_book, "PROFILE", build_book.load_build_profile("annex"))
    assert build_book.resolve_pdfmode(None) == "screen"


def test_explicit_target_mode_wins_over_profile(profiles, monkeypatch):
    monkeypatch.setattr(build_book, "PROFILE", build_book.load_build_profile("annex"))
    assert build_book.resolve_pdfmode("print") == "print"


def test_profile_without_mode_keeps_letter(profiles, monkeypatch):
    monkeypatch.setattr(build_book, "PROFILE", build_book.load_build_profile("default"))
    assert build_book.resolve_pdfmode(None) is None
