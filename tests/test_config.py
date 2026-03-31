import tempfile
import os

import pytest
import yaml

from campsite_monitor.config import load_config


def _write_yaml(tmp_path, data):
    path = os.path.join(tmp_path, "config.yaml")
    with open(path, "w") as f:
        yaml.dump(data, f)
    return path


def test_load_valid_config(tmp_path):
    data = {
        "recgov": [{"id": "233116", "name": "Kirk Creek"}],
        "reserveca": [{"place_id": "661", "name": "Julia Pfeiffer Burns SP"}],
    }
    path = _write_yaml(str(tmp_path), data)
    cfg = load_config(path)
    assert len(cfg["recgov"]) == 1
    assert cfg["recgov"][0]["id"] == "233116"
    assert cfg["recgov"][0]["name"] == "Kirk Creek"
    assert len(cfg["reserveca"]) == 1
    assert cfg["reserveca"][0]["place_id"] == "661"
    assert cfg["reserveca"][0]["name"] == "Julia Pfeiffer Burns SP"


def test_missing_file_exits():
    with pytest.raises(SystemExit):
        load_config("/nonexistent/path/config.yaml")


def test_missing_recgov_id(tmp_path):
    data = {"recgov": [{"name": "No ID"}]}
    path = _write_yaml(str(tmp_path), data)
    with pytest.raises(SystemExit):
        load_config(path)


def test_missing_reserveca_place_id(tmp_path):
    data = {"reserveca": [{"name": "No Place ID"}]}
    path = _write_yaml(str(tmp_path), data)
    with pytest.raises(SystemExit):
        load_config(path)


def test_empty_config(tmp_path):
    path = _write_yaml(str(tmp_path), {})
    cfg = load_config(path)
    assert cfg["recgov"] == []
    assert cfg["reserveca"] == []


def test_facility_ids_override(tmp_path):
    data = {
        "reserveca": [
            {"place_id": "690", "name": "Big Sur", "facility_ids": [767, 768]}
        ]
    }
    path = _write_yaml(str(tmp_path), data)
    cfg = load_config(path)
    assert cfg["reserveca"][0]["facility_ids"] == ["767", "768"]


def test_filters_parsed(tmp_path):
    filters = {"site_types": ["Campsite", "Tent Campsite"]}
    data = {
        "reserveca": [
            {"place_id": "690", "name": "Big Sur", "filters": filters}
        ]
    }
    path = _write_yaml(str(tmp_path), data)
    cfg = load_config(path)
    assert cfg["reserveca"][0]["filters"] == filters


def test_ids_converted_to_string(tmp_path):
    data = {
        "recgov": [{"id": 233116, "name": "Kirk Creek"}],
        "reserveca": [{"place_id": 661, "name": "Julia Pfeiffer Burns SP"}],
    }
    path = _write_yaml(str(tmp_path), data)
    cfg = load_config(path)
    assert cfg["recgov"][0]["id"] == "233116"
    assert isinstance(cfg["recgov"][0]["id"], str)
    assert cfg["reserveca"][0]["place_id"] == "661"
    assert isinstance(cfg["reserveca"][0]["place_id"], str)
