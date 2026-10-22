import json
from pathlib import Path

from src.core.app_config import AppConfig, DEFAULT_CONFIG_PATH, load_app_config


def test_default_config_matches_repo_file():
    """config/hardware_config.json (el que edita el cliente) tiene que
    poder cargarse y coincidir con sus propios valores de ejemplo."""
    cfg = load_app_config(DEFAULT_CONFIG_PATH)
    assert cfg.camera.type == "simulated"
    assert cfg.motor.mode == "simulated"
    assert cfg.motor.steps_per_frame == 1000
    assert cfg.calibration.film_format == "35mm"
    assert cfg.calibration.search_zone_left.x0 == 10
    assert cfg.calibration.reference_box.x1 == 680


def test_missing_file_falls_back_to_defaults(tmp_path):
    cfg = load_app_config(tmp_path / "no_existe.json")
    assert cfg == AppConfig()


def test_malformed_json_falls_back_to_defaults(tmp_path, capsys):
    bad_file = tmp_path / "hardware_config.json"
    bad_file.write_text("{ esto no es json valido", encoding="utf-8")

    cfg = load_app_config(bad_file)

    assert cfg == AppConfig()
    assert "No se pudo leer" in capsys.readouterr().out


def test_partial_override_keeps_other_defaults(tmp_path):
    """El cliente puede completar solo el puerto del motor y dejar el
    resto sin tocar: no debería romper nada."""
    partial = tmp_path / "hardware_config.json"
    partial.write_text(json.dumps({"motor": {"mode": "serial", "port": "/dev/ttyACM0"}}), encoding="utf-8")

    cfg = load_app_config(partial)

    assert cfg.motor.mode == "serial"
    assert cfg.motor.port == "/dev/ttyACM0"
    assert cfg.motor.baudrate == 115200  # default, no lo tocó
    assert cfg.camera.type == "simulated"  # default, no lo tocó
