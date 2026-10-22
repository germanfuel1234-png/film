"""Guardado no destructivo de fotogramas en RAW/DNG + verificación SHA-256.

Principios (ver ESPECIFICACIONES_PROYECTO.md §3 y §5):
- Nunca se guarda JPEG como salida final.
- El original capturado por la cámara no se sobrescribe: la corrección de
  alineación (dx, dy, ángulo, encuadre) se guarda aparte, como metadata
  reaplicable — "originales conservados" en palabras del prototipo.
- Al exportar el proyecto se genera un manifiesto con hash SHA-256 por
  archivo ("copia verificada SHA-256").
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from ..hardware.camera_base import CapturedFrame
from ..vision.stabilization import AlignmentResult


class ProjectStorage:
    """Maneja el layout de archivos de un proyecto en disco:

        <project_dir>/
            raw/            fotogramas originales, uno por frame_index
            corrections/    parámetros de alineación por frame_index (.json)
            manifest.json   índice + hash SHA-256 de cada archivo exportado
    """

    def __init__(self, project_dir: Path | str) -> None:
        self.project_dir = Path(project_dir)
        self.raw_dir = self.project_dir / "raw"
        self.corrections_dir = self.project_dir / "corrections"
        self.manifest_path = self.project_dir / "manifest.json"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.corrections_dir.mkdir(parents=True, exist_ok=True)

    def next_frame_index(self) -> int:
        """Siguiente índice de fotograma a usar: continúa después del
        último ya guardado en disco (busca el `frame_NNNNN` más alto en
        `raw/`). Es lo que evita que "Abrir / reanudar" un proyecto con
        fotogramas ya guardados vuelva a numerar desde 0 y los pise."""
        max_index = -1
        for path in self.raw_dir.iterdir():
            if not path.is_file() or not path.name.startswith("frame_"):
                continue
            digits = path.name[len("frame_") :].split(".")[0]
            if digits.isdigit():
                max_index = max(max_index, int(digits))
        return max_index + 1

    def save_frame(self, captured: CapturedFrame) -> Path:
        """Guarda el buffer original tal cual llega de la cámara, sin tocarlo."""
        filename = f"frame_{captured.frame_index:05d}{captured.file_extension}"
        out_path = self.raw_dir / filename
        out_path.write_bytes(captured.raw_bytes)
        return out_path

    def save_correction(self, frame_index: int, alignment: AlignmentResult, reference_box: dict) -> Path:
        """Guarda la transformación de alineación aplicada a ese fotograma,
        de forma no destructiva (el RAW original en raw/ no se modifica)."""
        out_path = self.corrections_dir / f"frame_{frame_index:05d}.json"
        payload = {
            "frame_index": frame_index,
            "alignment": asdict(alignment),
            "reference_box": reference_box,
        }
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return out_path

    @staticmethod
    def _sha256_of(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def export_manifest(self) -> dict:
        """Genera (y persiste) el manifiesto SHA-256 de todos los RAW del
        proyecto — equivalente a "Exportar proyecto · copia verificada
        SHA-256" en la pestaña "Escaneo" del prototipo."""
        entries = []
        for raw_file in sorted(self.raw_dir.iterdir()):
            if not raw_file.is_file():
                continue
            entries.append(
                {
                    "file": raw_file.name,
                    "sha256": self._sha256_of(raw_file),
                    "size_bytes": raw_file.stat().st_size,
                }
            )
        manifest = {"project_dir": str(self.project_dir), "frame_count": len(entries), "files": entries}
        self.manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest

    def verify_manifest(self) -> list[str]:
        """Recalcula los hashes y devuelve la lista de archivos que no
        coinciden con el manifiesto guardado (idealmente vacía)."""
        if not self.manifest_path.exists():
            raise FileNotFoundError(f"No existe manifiesto en {self.manifest_path}; corré export_manifest() primero.")
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        mismatches = []
        for entry in manifest["files"]:
            path = self.raw_dir / entry["file"]
            if not path.exists() or self._sha256_of(path) != entry["sha256"]:
                mismatches.append(entry["file"])
        return mismatches
