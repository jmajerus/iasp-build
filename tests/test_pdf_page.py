"""Digital PDFs use one page size per profile, whichever target builds them."""

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
                "europe": {"order_file": "book-order.txt", "pdf_page": "a4"},
                "proof": {"order_file": "book-order.txt", "pdf_page": "6x9"},
                "bad": {"order_file": "book-order.txt", "pdf_page": "phone"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(build_book, "BUILD_PROFILES_FILE", path)
    monkeypatch.setattr(build_book, "PROFILE", None)
    return path


def _use(monkeypatch, name):
    monkeypatch.setattr(build_book, "PROFILE", build_book.load_build_profile(name))


def test_digital_pdf_defaults_to_letter_with_one_inch_margins(profiles, monkeypatch):
    _use(monkeypatch, "default")
    assert build_book.digital_pdf_geometry() == (
        "paperwidth=8.5in,paperheight=11in,margin=1in,twoside=false"
    )


def test_profile_can_choose_another_page(profiles, monkeypatch):
    _use(monkeypatch, "europe")
    assert "paperwidth=210mm,paperheight=297mm" in build_book.digital_pdf_geometry()
    _use(monkeypatch, "proof")
    assert "paperwidth=6in,paperheight=9in" in build_book.digital_pdf_geometry()


def test_unknown_page_stops_the_build(profiles, capsys):
    with pytest.raises(SystemExit):
        build_book.load_build_profile("bad")
    assert "pdf_page 'phone'" in capsys.readouterr().out


def test_pdf_and_pdf_screen_build_the_same_geometry(profiles, monkeypatch):
    # "pdf" passes no mode; it used to fall back to a different page size
    # than "pdf-screen" while writing the same file.
    _use(monkeypatch, "default")
    commands = []
    monkeypatch.setattr(build_book, "make_pdf_base_cmd", lambda *a, pdfmode=None, **k: commands.append(pdfmode) or ["pandoc"])
    for name in ("ensure_build_dir", "stage_cover_image", "run", "optimize_pdf", "update_page_count_cache"):
        monkeypatch.setattr(build_book, name, lambda *a, **k: None)
    build_book.build_pdf()
    build_book.build_pdf(pdfmode="screen")
    assert commands == ["screen", "screen"]
