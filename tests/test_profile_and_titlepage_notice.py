"""Tests for profile-conditional blocks and the titlepage-notice metadata key."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

CHECKOUT = Path(__file__).resolve().parents[1]
LUA_DIR = CHECKOUT / "iasp_tooling" / "lua"
PROFILE_FILTER = LUA_DIR / "profile_visibility.lua"
SEMANTICS_FILTER = LUA_DIR / "iasp-semantics.lua"
TOC_FILTER = LUA_DIR / "iasp-toc.lua"
NOTICE_FILTER = LUA_DIR / "titlepage_notice.lua"

requires_pandoc = pytest.mark.skipif(shutil.which("pandoc") is None, reason="Pandoc is required")

PROFILE_SOURCE = """\
# Intro

::: {.license .standalone-only}
## Standalone Heading

STANDALONE-BLOCK
:::

::: {.license .profile-only profiles="annex1 annex2"}
PROFILE-ANNEX-BLOCK
:::

::: {.profile-only profiles="default,annex3"}
MAIN-OR-ANNEX3-BLOCK
:::

Inline [STANDALONE-SPAN]{.standalone-only} and [ANNEX1-SPAN]{.profile-only profiles="annex1"}.

## Hidden Heading {.standalone-only}

ALWAYS-BLOCK
"""


def _pandoc(args: list[str], source: str, *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["pandoc", "--from=markdown", *args],
        input=source,
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )


def _render_with_profile(profile: str | None, lua_filter: Path = PROFILE_FILTER) -> tuple[str, str]:
    args = ["--to=html5"]
    if profile is not None:
        args += ["--metadata", f"build-profile={profile}"]
    args += ["--lua-filter", str(lua_filter)]
    result = _pandoc(args, PROFILE_SOURCE)
    assert result.returncode == 0, result.stderr
    return result.stdout, result.stderr


# ---------------------------------------------------------------------------
# Feature B: profile-conditional content
# ---------------------------------------------------------------------------


@requires_pandoc
@pytest.mark.parametrize("profile", [None, "default"])
def test_main_book_hides_standalone_and_annex_only_content(profile):
    html, _ = _render_with_profile(profile)
    assert "STANDALONE-BLOCK" not in html
    assert "Standalone Heading" not in html
    assert "PROFILE-ANNEX-BLOCK" not in html
    assert "STANDALONE-SPAN" not in html
    assert "ANNEX1-SPAN" not in html
    assert "Hidden Heading" not in html
    assert "MAIN-OR-ANNEX3-BLOCK" in html
    assert "ALWAYS-BLOCK" in html


@requires_pandoc
def test_annex_profile_shows_its_content_and_strips_control_markup():
    html, _ = _render_with_profile("annex1")
    assert "STANDALONE-BLOCK" in html
    assert "Standalone Heading" in html
    assert "PROFILE-ANNEX-BLOCK" in html
    assert "STANDALONE-SPAN" in html
    assert "ANNEX1-SPAN" in html
    assert "Hidden Heading" in html
    assert "MAIN-OR-ANNEX3-BLOCK" not in html
    # Control classes and the profiles attribute never reach the output,
    # but ordinary classes such as .license survive.
    assert "profile-only" not in html
    assert "standalone-only" not in html
    assert "profiles=" not in html
    assert 'class="license"' in html


@requires_pandoc
def test_profile_list_accepts_commas_and_other_profiles():
    html, _ = _render_with_profile("annex3")
    assert "MAIN-OR-ANNEX3-BLOCK" in html
    assert "PROFILE-ANNEX-BLOCK" not in html
    assert "ANNEX1-SPAN" not in html
    assert "STANDALONE-BLOCK" in html


@requires_pandoc
def test_profile_only_without_profiles_attribute_warns_and_renders():
    result = _pandoc(
        ["--to=html5", "--lua-filter", str(PROFILE_FILTER)],
        "::: {.profile-only}\nKEPT\n:::\n",
    )
    assert result.returncode == 0, result.stderr
    assert "KEPT" in result.stdout
    assert "profiles=" in result.stderr


@requires_pandoc
def test_documents_without_profile_markup_are_unchanged():
    source = "# Title\n\n::: {.note}\nText [span]{.x}\n:::\n"
    plain = _pandoc(["--to=native"], source)
    filtered = _pandoc(
        ["--to=native", "--metadata", "build-profile=annex1", "--lua-filter", str(PROFILE_FILTER)],
        source,
    )
    assert plain.returncode == 0 and filtered.returncode == 0
    assert plain.stdout == filtered.stdout


@requires_pandoc
def test_semantics_filter_applies_profile_visibility_to_included_content(tmp_path):
    (tmp_path / "included.md").write_text(
        "::: {.standalone-only}\nINCLUDED-STANDALONE\n:::\n\nINCLUDED-ALWAYS\n",
        encoding="utf-8",
    )
    source = '::: {.include path="included.md"}\n:::\n'
    for profile, expect_hidden in (("default", True), ("annex2", False)):
        result = _pandoc(
            [
                "--to=html5",
                "--metadata",
                f"build-profile={profile}",
                "--lua-filter",
                str(SEMANTICS_FILTER),
            ],
            source,
            cwd=tmp_path,
        )
        assert result.returncode == 0, result.stderr
        assert "INCLUDED-ALWAYS" in result.stdout
        assert ("INCLUDED-STANDALONE" in result.stdout) is not expect_hidden


@requires_pandoc
def test_toc_filter_drops_headings_hidden_for_profile():
    def headings(profile: str) -> list[str]:
        result = _pandoc(
            ["--to=json", "--metadata", f"build-profile={profile}", "--lua-filter", str(TOC_FILTER)],
            PROFILE_SOURCE,
        )
        assert result.returncode == 0, result.stderr
        doc = json.loads(result.stdout)
        found = []

        def walk(blocks):
            for block in blocks:
                if block["t"] == "Header":
                    found.append(json.dumps(block["c"][2]))
                elif block["t"] == "Div":
                    walk(block["c"][1])

        walk(doc["blocks"])
        return found

    default_text = " ".join(headings("default"))
    annex_text = " ".join(headings("annex1"))
    assert "Standalone" not in default_text and "Hidden" not in default_text
    assert "Standalone" in annex_text and "Hidden" in annex_text


@requires_pandoc
def test_generate_toc_passes_active_profile_to_pandoc(tmp_path, monkeypatch):
    from iasp_tooling.scripts import generate_toc

    doc = tmp_path / "doc.md"
    doc.write_text(PROFILE_SOURCE, encoding="utf-8")

    monkeypatch.setattr(generate_toc, "BUILD_PROFILE", "default")
    default_headings: list = []
    generate_toc.collect_headings(generate_toc.run_pandoc_json(doc)["blocks"], default_headings)

    monkeypatch.setattr(generate_toc, "BUILD_PROFILE", "annex2")
    annex_headings: list = []
    generate_toc.collect_headings(generate_toc.run_pandoc_json(doc)["blocks"], annex_headings)

    def titles(items):
        return [generate_toc.stringify_inlines(h["c"][2]) for h in items]

    assert "Standalone Heading" not in titles(default_headings)
    assert "Standalone Heading" in titles(annex_headings)
    assert generate_toc._parse_args(["--profile", "annex2"]).profile == "annex2"
    assert generate_toc._parse_args([]).profile is None


# ---------------------------------------------------------------------------
# Feature A: titlepage-notice
# ---------------------------------------------------------------------------


def _render_notice(tmp_path: Path, metadata: str, target: str) -> str:
    meta_file = tmp_path / "meta.yaml"
    meta_file.write_text(metadata, encoding="utf-8")
    writer = "latex" if target == "latex" else "html5"
    result = _pandoc(
        [
            f"--to={writer}",
            "--wrap=none",
            "--metadata-file",
            str(meta_file),
            "--metadata",
            f"iasp-titlepage-notice-target={target}",
            "--lua-filter",
            str(NOTICE_FILTER),
        ],
        "",
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


RIGHTS = 'rights: "© 2026 Example. CC BY-NC 4.0."\n'
NOTICE = (
    "titlepage-notice: |\n"
    "  Licensed under [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/).\n"
)


@requires_pandoc
def test_notice_absent_renders_nothing(tmp_path):
    assert _render_notice(tmp_path, RIGHTS, "latex") == ""
    assert _render_notice(tmp_path, RIGHTS, "epub") == ""


@requires_pandoc
def test_notice_markdown_renders_links(tmp_path):
    latex = _render_notice(tmp_path, RIGHTS + NOTICE, "latex")
    assert r"\href{https://creativecommons.org/licenses/by-nc/4.0/}{CC BY-NC 4.0}" in latex
    html = _render_notice(tmp_path, RIGHTS + NOTICE, "epub")
    assert '<a href="https://creativecommons.org/licenses/by-nc/4.0/">CC BY-NC 4.0</a>' in html


@requires_pandoc
@pytest.mark.parametrize(
    "switch",
    ["titlepage-notice: rights\n", "titlepage-notice: true\n", "titlepage-rights: true\n"],
)
def test_notice_rights_alias(tmp_path, switch):
    latex = _render_notice(tmp_path, RIGHTS + switch, "latex")
    assert "© 2026 Example. CC BY-NC 4.0." in latex
    # pandoc's EPUB title page already prints `rights`; don't duplicate it.
    assert _render_notice(tmp_path, RIGHTS + switch, "epub") == ""


@requires_pandoc
def test_notice_false_disables(tmp_path):
    assert _render_notice(tmp_path, RIGHTS + "titlepage-notice: false\ntitlepage-rights: true\n", "latex") == ""


def test_latex_header_appends_notice_to_title_block():
    from iasp_tooling import build_book

    header = build_book.titlepage_notice_latex_header(r"Text \href{https://x.org}{x}")
    assert r"\long\def\iasptitlepagenotice{%" in header
    assert r"Text \href{https://x.org}{x}%" in header
    assert r"\AtBeginDocument{\g@addto@macro\@date{" in header
    assert header.count("{") == header.count("}")


def test_xhtml_insertion_targets_titlepage_section():
    from iasp_tooling import build_book

    page = (
        '<body><section epub:type="titlepage" class="titlepage">\n'
        '  <h1 class="title">T</h1>\n</section>\n<section id="other"></section></body>'
    )
    patched = build_book.insert_titlepage_notice_xhtml(page, "<p>N</p>")
    assert patched is not None
    head, tail = patched.split('<section id="other">')
    assert '<div class="titlepage-notice">\n<p>N</p>\n</div>\n</section>' in head
    assert "titlepage-notice" not in tail
    assert build_book.insert_titlepage_notice_xhtml("<body></body>", "<p>N</p>") is None


# ---------------------------------------------------------------------------
# End-to-end: EPUB builds for the main book and an annex profile
# ---------------------------------------------------------------------------


def _write_project(root: Path) -> None:
    (root / "chapters").mkdir(parents=True)
    (root / "annexes" / "annex1").mkdir(parents=True)
    (root / "iasp-config.yaml").write_text("toc:\n  enabled: false\n", encoding="utf-8")
    (root / "metadata.yaml").write_text('title: "Main"\nlang: en-US\n' + RIGHTS, encoding="utf-8")
    (root / "annexes" / "annex1" / "annex1-metadata.yaml").write_text(
        'title: "Annex One"\nlang: en-US\nbibliography: []\n' + RIGHTS + NOTICE, encoding="utf-8"
    )
    (root / "build-profiles.json").write_text(
        json.dumps(
            {
                "default": {"order_file": "book-order.txt", "metadata": ["metadata.yaml"]},
                "annex1": {
                    "order_file": "annexes/annex1/book-order.txt",
                    "metadata": ["annexes/annex1/annex1-metadata.yaml"],
                    "output_basename": "annex1",
                },
            }
        ),
        encoding="utf-8",
    )
    (root / "chapters" / "ch1.md").write_text("# Chapter\n\nBody.\n", encoding="utf-8")
    (root / "annexes" / "annex1" / "intro.md").write_text(
        "# Annex Intro\n\n::: {.license .standalone-only}\nLICENSE-MARKER\n:::\n\nAnnex body.\n",
        encoding="utf-8",
    )
    (root / "book-order.txt").write_text("chapters/ch1.md\nannexes/annex1/intro.md\n", encoding="utf-8")
    (root / "annexes" / "annex1" / "book-order.txt").write_text("annexes/annex1/intro.md\n", encoding="utf-8")


def _build(root: Path, profile: str) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(CHECKOUT)
    env["SKIP_EPUBCHECK"] = "1"
    env.pop("IASP_CONFIG_PATH", None)
    env.pop("BUILD_PROFILE", None)
    result = subprocess.run(
        [sys.executable, "-m", "iasp_tooling.cli", "--project-root", str(root), "--profile", profile, "epub"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _epub_text(path: Path) -> tuple[str, str]:
    with ZipFile(path) as zf:
        title_page = next(n for n in zf.namelist() if n.endswith("title_page.xhtml"))
        body = "".join(
            zf.read(n).decode("utf-8")
            for n in zf.namelist()
            if n.endswith(".xhtml") and not n.endswith("title_page.xhtml")
        )
        return zf.read(title_page).decode("utf-8"), body


@requires_pandoc
def test_epub_builds_for_main_book_and_annex(tmp_path):
    root = tmp_path / "project"
    _write_project(root)

    _build(root, "default")
    title_page, body = _epub_text(root / "build" / "manuscript.epub")
    assert "titlepage-notice" not in title_page
    assert "LICENSE-MARKER" not in body
    assert "Annex body." in body

    _build(root, "annex1")
    title_page, body = _epub_text(root / "build" / "annexes" / "annex1.epub")
    assert '<div class="titlepage-notice">' in title_page
    assert 'href="https://creativecommons.org/licenses/by-nc/4.0/"' in title_page
    assert "LICENSE-MARKER" in body


@requires_pandoc
@pytest.mark.parametrize("target", ["latex", "html"])
def test_notice_rights_alias_keeps_links_and_formatting(tmp_path, target):
    metadata = (
        'rights: "*© 2026* Example. [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)."\n'
        "titlepage-notice: rights\n"
    )
    if target == "latex":
        latex = _render_notice(tmp_path, metadata, "latex")
        assert r"\href{https://creativecommons.org/licenses/by-nc/4.0/}{CC BY-NC 4.0}" in latex
        assert r"\emph{© 2026}" in latex
    else:
        # The EPUB target skips the rights alias; rendering it as plain HTML
        # (any non-epub target) shows the AST is preserved there too.
        html = _render_notice(tmp_path, metadata, "html")
        assert '<a href="https://creativecommons.org/licenses/by-nc/4.0/">CC BY-NC 4.0</a>' in html
        assert "<em>© 2026</em>" in html


def test_article_pdf_runs_profile_filter_before_other_filters(tmp_path, monkeypatch):
    from iasp_tooling import build_book

    source = tmp_path / "article.md"
    source.write_text("# Article\n\nBody.\n", encoding="utf-8")
    captured: list[list[str]] = []

    class Stop(Exception):
        pass

    def fake_run(cmd):
        captured.append(cmd)
        raise Stop

    monkeypatch.setattr(build_book, "run", fake_run)
    monkeypatch.setattr(build_book, "ensure_build_dir", lambda: None)
    monkeypatch.setattr(build_book, "verify_citations", lambda inputs: None)
    with pytest.raises(Stop):
        build_book.build_article_pdf(source, str(tmp_path / "out.pdf"))

    filters = [captured[0][i + 1] for i, arg in enumerate(captured[0]) if arg == "--lua-filter"]
    assert filters, captured[0]
    assert Path(filters[0]).name == "profile_visibility.lua"
