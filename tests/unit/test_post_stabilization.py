"""Pruebas del botón "Aplicar mejora" (core/post_stabilization.py) contra
las fotos reales del cliente — confirma que la mejora efectivamente reduce
la variación de rotación entre fotogramas (el reclamo original: la
secuencia "giraba" un poco entre cuadros)."""

import shutil
from pathlib import Path

import cv2
import pytest

from src.core.post_stabilization import apply_improvement
from src.storage.raw_dng_writer import ProjectStorage
from src.vision.perforation_detection import SearchZone
from src.vision.stabilization import ReferenceBox

REAL_FRAMES = Path(__file__).resolve().parents[2] / "assets" / "real_frames"
TOP_ZONE = SearchZone(x0=380, y0=0, x1=1600, y1=150)
BOTTOM_ZONE = SearchZone(x0=380, y0=1015, x1=1600, y1=1080)
REFERENCE_BOX = ReferenceBox(x0=700, y0=250, x1=1360, y1=1020)


@pytest.fixture
def project_storage_with_real_frames(tmp_path):
    storage = ProjectStorage(tmp_path / "proyecto")
    files = sorted(REAL_FRAMES.glob("*.JPG"))[:10]
    assert files, "Faltan las fotos reales en assets/real_frames/"
    for f in files:
        shutil.copy(f, storage.raw_dir / f.name.replace("_MG_", "frame_"))
    return storage


@pytest.fixture
def project_storage_with_all_real_frames(tmp_path):
    storage = ProjectStorage(tmp_path / "proyecto_completo")
    files = sorted(REAL_FRAMES.glob("*.JPG"))
    assert len(files) >= 30, "Se esperaban las 36 fotos reales en assets/real_frames/"
    for f in files:
        shutil.copy(f, storage.raw_dir / f.name.replace("_MG_", "frame_"))
    return storage


def test_apply_improvement_keeps_rotation_bounded_on_all_36_real_frames(project_storage_with_all_real_frames):
    """El caso real que reportó el cliente: con el método de un solo par
    de perforaciones, el ángulo estimado sobre estas 36 fotos variaba
    entre -3.3° y +6.0° (se nota como "giro" al reproducir la secuencia).

    Evolución medida sobre este mismo material:
      - 1 par de perforaciones:            rango 9.3°
      - todas las perforaciones + RANSAC:  rango 1.39°
      - + refinamiento ECC (actual):       rango 0.18°
    El umbral de 0.5° deja margen de variación pero falla si alguien
    rompe el refinamiento ECC y volvemos al nivel anterior.
    """
    results = apply_improvement(project_storage_with_all_real_frames, TOP_ZONE, BOTTOM_ZONE, REFERENCE_BOX)
    assert len(results) >= 30
    assert all(r.error is None for r in results)

    angles = [r.alignment.angle_deg for r in results if r.alignment is not None]
    assert max(angles) - min(angles) < 0.5
    assert max(abs(a) for a in angles) < 0.5


def test_improved_frames_are_more_consistent_than_raw_crops(project_storage_with_all_real_frames):
    """Verificación visual objetiva: al PROMEDIAR todos los fotogramas, si
    están bien alineados entre sí los bordes del cuadro (estructura fija
    del celuloide) salen nítidos; si hay bamboleo salen borroneados. El
    promedio de los fotogramas mejorados tiene que ser medible más nítido
    que el de los recortes sin estabilizar."""
    import numpy as np

    storage = project_storage_with_all_real_frames
    results = apply_improvement(storage, TOP_ZONE, BOTTOM_ZONE, REFERENCE_BOX)

    improved = [cv2.imread(str(r.output_path)) for r in results if r.output_path is not None]
    raw_crops = [
        cv2.imread(str(p))[REFERENCE_BOX.y0 : REFERENCE_BOX.y1, REFERENCE_BOX.x0 : REFERENCE_BOX.x1]
        for p in sorted(storage.raw_dir.iterdir())
    ]

    def average_sharpness(images):
        avg = np.mean([im.astype(np.float32) for im in images], axis=0).astype(np.uint8)
        return cv2.Laplacian(cv2.cvtColor(avg, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var()

    assert average_sharpness(improved) > average_sharpness(raw_crops) * 1.2


def test_apply_improvement_processes_every_frame_without_errors(project_storage_with_real_frames):
    results = apply_improvement(project_storage_with_real_frames, TOP_ZONE, BOTTOM_ZONE, REFERENCE_BOX)
    assert len(results) == 10
    assert all(r.error is None for r in results)
    assert all(r.output_path is not None and r.output_path.exists() for r in results)


def test_apply_improvement_keeps_rotation_bounded(project_storage_with_real_frames):
    """La queja original del cliente: la secuencia final giraba un poco
    entre fotogramas. El registro robusto (todas las perforaciones +
    RANSAC, en vez de un único par) tiene que mantener el ángulo estimado
    en un rango mucho más chico que el método de un solo par (que llegaba
    a variar entre -3.3° y +6.0° sobre este mismo material)."""
    results = apply_improvement(project_storage_with_real_frames, TOP_ZONE, BOTTOM_ZONE, REFERENCE_BOX)
    angles = [r.alignment.angle_deg for r in results if r.alignment is not None]
    assert angles
    assert max(angles) - min(angles) < 3.0


def test_apply_improvement_does_not_modify_original_raw_files(project_storage_with_real_frames):
    original_sizes = {p.name: p.stat().st_size for p in project_storage_with_real_frames.raw_dir.iterdir()}
    apply_improvement(project_storage_with_real_frames, TOP_ZONE, BOTTOM_ZONE, REFERENCE_BOX)
    after_sizes = {p.name: p.stat().st_size for p in project_storage_with_real_frames.raw_dir.iterdir()}
    assert original_sizes == after_sizes


def test_apply_improvement_output_frames_have_reference_box_size(project_storage_with_real_frames):
    results = apply_improvement(project_storage_with_real_frames, TOP_ZONE, BOTTOM_ZONE, REFERENCE_BOX)
    for r in results:
        img = cv2.imread(str(r.output_path))
        assert img.shape[0] == REFERENCE_BOX.height
        assert img.shape[1] == REFERENCE_BOX.width


def test_apply_improvement_on_empty_project_returns_empty_list(tmp_path):
    storage = ProjectStorage(tmp_path / "proyecto_vacio")
    results = apply_improvement(storage, TOP_ZONE, BOTTOM_ZONE, REFERENCE_BOX)
    assert results == []
