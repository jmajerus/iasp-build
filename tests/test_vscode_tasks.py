from iasp_tooling.lib import vscode_tasks


def test_workspace_virtual_environment_for_generated_tasks(tmp_path, monkeypatch):
    monkeypatch.setattr(vscode_tasks, "ROOT", tmp_path)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "sync_builds_to_drive.py").touch()
    settings = {"outputs": [{"target": "pdf"}]}

    default_tasks = vscode_tasks._build_payload(settings)["tasks"]
    assert all(task["command"] == "python3" for task in default_tasks)

    tasks = vscode_tasks._build_payload({**settings, "use_workspace_venv": True})["tasks"]
    assert {task["label"] for task in tasks} == {"Build pdf", "Drive sync (latest build)"}
    for task in tasks:
        assert task["type"] == "process"
        assert task["command"] == "${workspaceFolder}/.venv/bin/python"
        assert task["windows"]["command"] == r"${workspaceFolder}\.venv\Scripts\python.exe"
    assert tasks[0]["options"]["env"] == {"BUILD_PROFILE": "${input:currentBuildProfile}"}
