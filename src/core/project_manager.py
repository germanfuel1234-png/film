"""Gestión del ciclo de vida de un proyecto: crear, listar, abrir/reanudar,
exportar — la sección "01 PROYECTO" de la pestaña "Escaneo" del prototipo.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..storage.raw_dng_writer import ProjectStorage

DEFAULT_PROJECTS_ROOT = Path.home() / "FILMS" / "projects"


@dataclass
class ProjectConfig:
    project_id: str
    name: str
    film_format: str
    created_at: str
    camera_type: str = "simulated"
    frames_saved: int = 0


class ProjectManager:
    def __init__(self, projects_root: Path | str = DEFAULT_PROJECTS_ROOT) -> None:
        # Path(...) NO expande "~" solo: sin expanduser(), un projects_root
        # tipo "~/FILMS/projects" (el default en config/hardware_config.json)
        # termina creando una carpeta literal llamada "~" en el directorio
        # actual en vez de guardar en el home real del usuario.
        self.projects_root = Path(projects_root).expanduser()
        self.projects_root.mkdir(parents=True, exist_ok=True)

    def _project_dir(self, project_id: str) -> Path:
        return self.projects_root / project_id

    def _config_path(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "project.json"

    def create_project(self, name: str, film_format: str, camera_type: str = "simulated") -> ProjectConfig:
        project_id = f"{datetime.now(timezone.utc):%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}"
        config = ProjectConfig(
            project_id=project_id,
            name=name,
            film_format=film_format,
            created_at=datetime.now(timezone.utc).isoformat(),
            camera_type=camera_type,
        )
        project_dir = self._project_dir(project_id)
        project_dir.mkdir(parents=True, exist_ok=True)
        self._config_path(project_id).write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
        ProjectStorage(project_dir)  # crea raw/ y corrections/
        return config

    def list_projects(self) -> list[ProjectConfig]:
        projects = []
        for config_path in sorted(self.projects_root.glob("*/project.json")):
            data = json.loads(config_path.read_text(encoding="utf-8"))
            projects.append(ProjectConfig(**data))
        return projects

    def open_project(self, project_id: str) -> ProjectConfig:
        config_path = self._config_path(project_id)
        if not config_path.exists():
            raise FileNotFoundError(f"No existe el proyecto {project_id} en {self.projects_root}")
        data = json.loads(config_path.read_text(encoding="utf-8"))
        return ProjectConfig(**data)

    def update_frames_saved(self, project_id: str, frames_saved: int) -> None:
        config = self.open_project(project_id)
        config.frames_saved = frames_saved
        self._config_path(project_id).write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")

    def storage_for(self, project_id: str) -> ProjectStorage:
        return ProjectStorage(self._project_dir(project_id))

    def export_project(self, project_id: str) -> dict:
        """"Exportar proyecto · copia verificada SHA-256" del prototipo."""
        return self.storage_for(project_id).export_manifest()
