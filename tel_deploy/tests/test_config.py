import pytest
import yaml
from tel_deploy.config import load_config

VALID_CONFIG = {
    "hub": {"host": "127.0.0.1", "port": 9999},
    "node": {"id": "TEST_NODE", "seed": "test_seed_value"},
    "logging": {"level": "INFO", "file": None},
    "reconnect": {"enabled": True, "interval_seconds": 5, "max_attempts": 0},
}


def write_yaml(tmp_path, data):
    p = tmp_path / "tel.yaml"
    p.write_text(yaml.dump(data))
    return str(p)


def test_load_valid_config(tmp_path):
    path = write_yaml(tmp_path, VALID_CONFIG)
    cfg = load_config(path)
    assert cfg["hub"]["host"] == "127.0.0.1"
    assert cfg["hub"]["port"] == 9999
    assert cfg["node"]["id"] == "TEST_NODE"
    assert cfg["node"]["seed"] == "test_seed_value"


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(str(tmp_path / "nonexistent.yaml"))


def test_missing_hub_section_raises(tmp_path):
    data = {k: v for k, v in VALID_CONFIG.items() if k != "hub"}
    path = write_yaml(tmp_path, data)
    with pytest.raises(KeyError, match="hub"):
        load_config(path)


def test_missing_node_section_raises(tmp_path):
    data = {k: v for k, v in VALID_CONFIG.items() if k != "node"}
    path = write_yaml(tmp_path, data)
    with pytest.raises(KeyError, match="node"):
        load_config(path)


def test_missing_hub_host_raises(tmp_path):
    data = yaml.safe_load(yaml.dump(VALID_CONFIG))
    del data["hub"]["host"]
    path = write_yaml(tmp_path, data)
    with pytest.raises(KeyError, match="host"):
        load_config(path)


def test_missing_hub_port_raises(tmp_path):
    data = yaml.safe_load(yaml.dump(VALID_CONFIG))
    del data["hub"]["port"]
    path = write_yaml(tmp_path, data)
    with pytest.raises(KeyError, match="port"):
        load_config(path)


def test_missing_node_id_raises(tmp_path):
    data = yaml.safe_load(yaml.dump(VALID_CONFIG))
    del data["node"]["id"]
    path = write_yaml(tmp_path, data)
    with pytest.raises(KeyError, match="id"):
        load_config(path)


def test_seed_is_optional(tmp_path):
    data = yaml.safe_load(yaml.dump(VALID_CONFIG))
    del data["node"]["seed"]
    path = write_yaml(tmp_path, data)
    cfg = load_config(path)
    assert cfg["node"]["seed"] is None


def test_env_override_hub_host(tmp_path, monkeypatch):
    path = write_yaml(tmp_path, VALID_CONFIG)
    monkeypatch.setenv("TEL_HUB_HOST", "10.0.0.1")
    cfg = load_config(path)
    assert cfg["hub"]["host"] == "10.0.0.1"


def test_env_override_hub_port(tmp_path, monkeypatch):
    path = write_yaml(tmp_path, VALID_CONFIG)
    monkeypatch.setenv("TEL_HUB_PORT", "8888")
    cfg = load_config(path)
    assert cfg["hub"]["port"] == 8888


def test_env_override_node_id(tmp_path, monkeypatch):
    path = write_yaml(tmp_path, VALID_CONFIG)
    monkeypatch.setenv("TEL_NODE_ID", "SPIDER")
    cfg = load_config(path)
    assert cfg["node"]["id"] == "SPIDER"


def test_env_override_node_seed(tmp_path, monkeypatch):
    path = write_yaml(tmp_path, VALID_CONFIG)
    monkeypatch.setenv("TEL_NODE_SEED", "env_seed_override")
    cfg = load_config(path)
    assert cfg["node"]["seed"] == "env_seed_override"


def test_malformed_yaml_raises(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text(":::invalid yaml:::\n\t\tbad")
    with pytest.raises(Exception):
        load_config(str(p))


def test_empty_yaml_raises(tmp_path):
    p = tmp_path / "empty.yaml"
    p.write_text("")
    with pytest.raises(ValueError, match="empty or malformed"):
        load_config(str(p))
