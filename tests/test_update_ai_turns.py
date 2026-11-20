import pytest

from iasp_tooling.scripts.update_ai_turns import main


@pytest.mark.parametrize("original", [b'{"ai_disclosure":', b"[]", b"\xff"])
def test_update_preserves_invalid_sidecar(tmp_path, capsys, original):
    article = tmp_path / "article.md"
    article.touch()
    sidecar = article.with_suffix(".ai.json")
    sidecar.write_bytes(original)

    assert main([str(article), "--inc", "1"]) == 1
    assert str(sidecar) in capsys.readouterr().err
    assert sidecar.read_bytes() == original
