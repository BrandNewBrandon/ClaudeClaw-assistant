from __future__ import annotations

from pathlib import Path

from app.agent_manager import AgentManager


def test_create_agent_scaffolds_expected_files(tmp_path: Path) -> None:
    project_root = tmp_path
    agents_dir = project_root / "agents"
    manager = AgentManager(project_root=project_root, agents_dir=agents_dir)

    created = manager.create_agent("ops")

    assert created == agents_dir / "ops"
    assert (created / "AGENT.md").exists()
    assert (created / "USER.md").exists()
    assert (created / "MEMORY.md").exists()
    assert (created / "TOOLS.md").exists()
    assert (created / "agent.json").exists()
    assert (created / "memory" / "README.md").exists()
    assert (created / "sessions" / "README.md").exists()


def test_clone_rename_delete_restore_agent_flow(tmp_path: Path) -> None:
    project_root = tmp_path
    agents_dir = project_root / "agents"
    manager = AgentManager(project_root=project_root, agents_dir=agents_dir)

    manager.create_agent("ops")
    cloned = manager.clone_agent("ops", "ops-copy")
    assert cloned.exists()

    renamed = manager.rename_agent("ops-copy", "ops-lab")
    assert renamed.exists()
    assert not (agents_dir / "ops-copy").exists()

    archived = manager.delete_agent("ops-lab")
    assert archived.exists()
    assert archived.parent == project_root / "archived_agents"
    assert not (agents_dir / "ops-lab").exists()

    archived_name = archived.name
    restored = manager.restore_agent(archived_name, restored_name="ops-lab")
    assert restored.exists()
    assert restored == agents_dir / "ops-lab"
