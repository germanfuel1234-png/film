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
REFERENCE_BOX = ReferenceBox(x0=700, y0=0, x1=1360, y1=1020)  # incluye perforaciones + banda sonora (pedido del cliente)


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


def test_output_is_level_in_absolute_terms_not_just_consistent(project_storage_with_all_real_frames):
    """El fotograma 0 de las fotos reales viene inclinado -0.241°. Si solo
    alineáramos todo contra él, la secuencia quedaría consistente entre
    cuadros pero TORCIDA para el ojo. Este test verifica el cero absoluto:
    tras corregir, la inclinación real del film (recta por las
    perforaciones) tiene que quedar prácticamente en 0."""
    import numpy as np

    from src.vision.perforation_detection import detect_perforations
    from src.vision.robust_registration import measure_absolute_tilt

    storage = project_storage_with_all_real_frames
    results = apply_improvement(storage, TOP_ZONE, BOTTOM_ZONE, REFERENCE_BOX)
    ok = [r for r in results if r.error is None and r.alignment is not None]

    original_tilt = results[0].reference_tilt_corrected_deg
    assert original_tilt is not None
    assert abs(original_tilt) > 0.1, "se esperaba que el fotograma 0 original estuviera inclinado"

    tilts = []
    for r in ok:
        img = cv2.imread(str(r.source_path))
        height, width = img.shape[:2]
        warped = cv2.warpAffine(
            img, r.alignment.matrix, (width, height), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE
        )
        tilt = measure_absolute_tilt(detect_perforations(warped, TOP_ZONE, BOTTOM_ZONE))
        if tilt is not None:
            tilts.append(tilt)

    assert tilts
    assert abs(float(np.mean(tilts))) < 0.05, "la secuencia corregida no quedó recta en términos absolutos"


def test_improved_frames_are_more_consistent_than_raw_crops(project_storage_with_all_real_frames):
    """Verificación visual objetiva: al PROMEDIAR todos los fotogramas, si
    están bien alineados entre sí los bordes del contenido (nubes,
    personaje) salen nítidos; si hay bamboleo salen borroneados.

    Se mide solo sobre el área de CONTENIDO (sin perforaciones ni banda
    sonora), aunque REFERENCE_BOX ahora las incluya: esa banda ya es
    bastante nítida incluso sin alinear (diluye la comparación), mientras
    que el contenido es justamente lo que se nota borroneado cuando hay
    bamboleo — es la parte que de verdad demuestra si la estabilización
    funciona."""
    import numpy as np

    storage = project_storage_with_all_real_frames
    results = apply_improvement(storage, TOP_ZONE, BOTTOM_ZONE, REFERENCE_BOX)

    # recorte de CONTENIDO dentro del fotograma mejorado (que ya viene con
    # perfs+banda sonora arriba): mismo rango que el REFERENCE_BOX anterior
    content_y0, content_y1 = 250, REFERENCE_BOX.y1

    def content_only(img):
        return img[content_y0:content_y1, :]

    improved = [content_only(cv2.imread(str(r.output_path))) for r in results if r.output_path is not None]
    raw_crops = [
        content_only(cv2.imread(str(p))[REFERENCE_BOX.y0 : REFERENCE_BOX.y1, REFERENCE_BOX.x0 : REFERENCE_BOX.x1])
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


def test_apply_improvement_with_rotation_swaps_output_dimensions(project_storage_with_real_frames):
    """Pedido del cliente: presentar cada fotograma en orientación de
    lectura normal (no "de costado" como lo capturó la cámara). Con
    rotation_deg=90 el ancho y alto del recorte final tienen que
    intercambiarse respecto del REFERENCE_BOX original."""
    results = apply_improvement(project_storage_with_real_frames, TOP_ZONE, BOTTOM_ZONE, REFERENCE_BOX, rotation_deg=90)
    ok = [r for r in results if r.output_path is not None]
    assert ok
    for r in ok:
        img = cv2.imread(str(r.output_path))
        assert img.shape[0] == REFERENCE_BOX.width
        assert img.shape[1] == REFERENCE_BOX.height


# --- pedido del cliente: resumible para películas enteras (fraccionar por
# tanda + retomar progreso si algo se corta a mitad de camino) ---


def test_second_run_skips_already_done_frames(project_storage_with_real_frames):
    """Si se vuelve a llamar sobre un proyecto ya mejorado (ej. se reabre
    el proyecto), los fotogramas ya resueltos no se vuelven a calcular:
    deben volver marcados already_done=True y sin tocar el archivo."""
    first = apply_improvement(project_storage_with_real_frames, TOP_ZONE, BOTTOM_ZONE, REFERENCE_BOX)
    ok_first = [r for r in first if r.error is None]
    assert ok_first and all(not r.already_done for r in ok_first)

    mtimes_before = {r.output_path: r.output_path.stat().st_mtime_ns for r in ok_first}

    second = apply_improvement(project_storage_with_real_frames, TOP_ZONE, BOTTOM_ZONE, REFERENCE_BOX)
    ok_second = [r for r in second if r.error is None]

    assert len(ok_second) == len(ok_first)
    assert all(r.already_done for r in ok_second)
    for r in ok_second:
        assert r.output_path.stat().st_mtime_ns == mtimes_before[r.output_path]  # no se reescribió


def test_max_frames_limits_new_frames_but_not_skips(project_storage_with_real_frames):
    """Fraccionar por tanda: solo procesa como máximo `max_frames`
    fotogramas NUEVOS por llamada; una segunda llamada retoma el resto."""
    first = apply_improvement(project_storage_with_real_frames, TOP_ZONE, BOTTOM_ZONE, REFERENCE_BOX, max_frames=3)
    new_in_first = [r for r in first if not r.already_done]
    assert len(new_in_first) == 3

    second = apply_improvement(project_storage_with_real_frames, TOP_ZONE, BOTTOM_ZONE, REFERENCE_BOX, max_frames=3)
    already_done_in_second = [r for r in second if r.already_done]
    new_in_second = [r for r in second if not r.already_done]
    assert len(already_done_in_second) == 3  # los 3 de la tanda anterior
    assert len(new_in_second) == 3  # la tanda siguiente

    # tercera tanda: quedaban 4 de los 10 fotogramas totales (3 + 3 ya hechos)
    third = apply_improvement(project_storage_with_real_frames, TOP_ZONE, BOTTOM_ZONE, REFERENCE_BOX, max_frames=100)
    assert len([r for r in third if r.already_done]) == 6
    assert len([r for r in third if not r.already_done]) == 4
    assert len(third) == 10


def test_should_stop_halts_before_next_new_frame(project_storage_with_real_frames):
    """Pedido del cliente: poder detener una corrida larga y que no se
    pierda lo ya guardado. should_stop se consulta ANTES de cada
    fotograma nuevo, nunca corta uno a mitad de camino."""
    processed_so_far = []

    def stop_after_two():
        return len(processed_so_far) >= 2

    results = apply_improvement(
        project_storage_with_real_frames,
        TOP_ZONE,
        BOTTOM_ZONE,
        REFERENCE_BOX,
        should_stop=stop_after_two,
        on_frame_processed=lambda r: processed_so_far.append(r) if not r.already_done else None,
    )
    new_results = [r for r in results if not r.already_done]
    assert len(new_results) == 2

    # retomar: la corrida siguiente completa el resto sin volver a tocar
    # los 2 primeros
    rest = apply_improvement(project_storage_with_real_frames, TOP_ZONE, BOTTOM_ZONE, REFERENCE_BOX)
    assert len([r for r in rest if r.already_done]) == 2
    assert len([r for r in rest if not r.already_done]) == 8


def test_on_frame_processed_callback_fires_for_every_frame_including_skips(project_storage_with_real_frames):
    apply_improvement(project_storage_with_real_frames, TOP_ZONE, BOTTOM_ZONE, REFERENCE_BOX)  # primera corrida

    seen = []
    apply_improvement(
        project_storage_with_real_frames,
        TOP_ZONE,
        BOTTOM_ZONE,
        REFERENCE_BOX,
        on_frame_processed=seen.append,
    )
    assert len(seen) == 10
    assert all(r.already_done for r in seen)


def test_interrupted_write_leaves_no_corrupt_final_file(project_storage_with_real_frames, monkeypatch):
    """Simula un corte de proceso a mitad del guardado de un fotograma:
    el archivo temporal queda huérfano, pero NUNCA debe existir un
    'frame_XXXXX_mejorado.png' corrupto con ese nombre final."""
    import src.core.post_stabilization as post_stabilization

    original_imwrite = cv2.imwrite
    call_count = {"n": 0}

    def flaky_imwrite(path, img):
        call_count["n"] += 1
        if call_count["n"] == 2:
            # escribe el temporal pero el proceso "se corta" antes del rename
            original_imwrite(path, img)
            raise RuntimeError("corte simulado a mitad de la escritura")
        return original_imwrite(path, img)

    monkeypatch.setattr(post_stabilization.cv2, "imwrite", flaky_imwrite)

    with pytest.raises(RuntimeError):
        apply_improvement(project_storage_with_real_frames, TOP_ZONE, BOTTOM_ZONE, REFERENCE_BOX)

    output_dir = project_storage_with_real_frames.project_dir / "mejorado"
    final_files = list(output_dir.glob("frame_*_mejorado.png"))
    tmp_files = list(output_dir.glob(".tmp_frame_*_mejorado.png"))
    assert len(final_files) == 1  # el primer fotograma sí llegó a completarse
    assert len(tmp_files) == 1  # el segundo quedó a medio camino, nunca se renombró

    # una corrida posterior limpia el huérfano y retoma desde ahí sin problema
    results = apply_improvement(project_storage_with_real_frames, TOP_ZONE, BOTTOM_ZONE, REFERENCE_BOX)
    ok = [r for r in results if r.error is None]
    assert len(ok) == 10
    assert not list(output_dir.glob(".tmp_frame_*_mejorado.png"))
