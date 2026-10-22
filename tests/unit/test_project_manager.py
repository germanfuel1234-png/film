from pathlib import Path

from src.core.project_manager import ProjectManager


def test_projects_root_expands_tilde(monkeypatch, tmp_path):
    """Regresión: Path("~/FILMS/projects") NO expande el "~" solo — sin
    expanduser(), termina creando una carpeta literal llamada "~" en el
    directorio actual en vez de guardar en el home real del usuario."""
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    manager = ProjectManager(projects_root="~/FILMS/projects")

    assert manager.projects_root == fake_home / "FILMS" / "projects"
    assert manager.projects_root.exists()
    assert not (Path.cwd() / "~").exists()
