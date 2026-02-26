import asyncio

from app.agent.ollama_client import ModelInfo
from app.control_plane.infra.config_store import ConfigStore
from app.control_plane.services.config_service import ConfigService
from app.control_plane.services.model_service import ModelService


class _FakeClient:
    async def list_models(self):
        return [
            ModelInfo(name="llama3.2", size=1024, modified_at="2026-01-01T00:00:00"),
            ModelInfo(name="mistral", size=2048, modified_at="2026-01-02T00:00:00"),
        ]


def test_list_models_detailed_marks_default(tmp_path):
    store = ConfigStore(tmp_path / "config" / "user_config.json")
    config = ConfigService(store)
    config.save_patch({"default_model": "mistral"})
    service = ModelService(config)
    service._client = lambda: _FakeClient()

    result = asyncio.run(service.list_models_detailed())

    assert len(result) == 2
    assert any(row["name"] == "mistral" and row["is_default"] for row in result)
    assert all(row["installed"] is True for row in result)

