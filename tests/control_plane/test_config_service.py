from app.control_plane.infra.config_store import ConfigStore
from app.control_plane.services.config_service import ConfigService


def test_config_env_overrides_local(monkeypatch, tmp_path):
    store = ConfigStore(tmp_path / "config" / "user_config.json")
    store.save({"default_model": "local-model"})
    monkeypatch.setenv("OLLAMA_CHAT_MODEL", "env-model")

    service = ConfigService(store)
    effective = service.load()

    assert effective.values.default_model == "env-model"
    assert effective.sources["default_model"] == "env"


def test_config_patch_persists(tmp_path):
    store = ConfigStore(tmp_path / "config" / "user_config.json")
    service = ConfigService(store)
    service.save_patch({"default_model": "llama3.1", "configured": True})
    loaded = service.load()
    assert loaded.values.default_model == "llama3.1"
    assert loaded.values.configured is True

