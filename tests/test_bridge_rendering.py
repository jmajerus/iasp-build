import shutil
import subprocess

import pytest

from iasp_tooling.paths import TOOLING_ROOT


@pytest.mark.skipif(shutil.which("pandoc") is None, reason="Pandoc is required for the Lua filter")
def test_unframed_bridge_keeps_page_breaks():
    result = subprocess.run(
        [
            "pandoc", "-f", "markdown", "-t", "latex",
            "--lua-filter", str(TOOLING_ROOT / "lua" / "iasp-semantics.lua"),
        ],
        input=(
            "::: {.bridge}\nA framed bridge.\n:::\n\n"
            "::: {.bridge .unframed .pre-pagebreak .post-pagebreak}\n"
            "A long bridge without a frame.\n:::\n"
        ),
        text=True,
        capture_output=True,
        check=True,
    )
    assert result.stdout.count(r"\begin{bridgeheadblock}") == 1
    assert result.stdout.count(r"\end{bridgeheadblock}") == 1
    before, content, after = result.stdout.split(r"\clearpage")
    assert "A framed bridge." in before
    assert "A long bridge without a frame." in content
    assert not after.strip()
