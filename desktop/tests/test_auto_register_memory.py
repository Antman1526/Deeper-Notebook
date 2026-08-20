from pathlib import Path

from desktop.auto_register.memory import register_memory_credential
from desktop.config import Config


def test_register_memory_credential_posts_credential():
    created = []

    class FakeClient:
        def get(self, path):
            class R:
                status_code = 200
                text = ""

                def raise_for_status(self):
                    pass

                def json(self):
                    return []

            return R()

        def post(self, path, json=None):
            created.append((path, json))

            class R:
                status_code = 201
                text = ""

                def json(self):
                    return {"id": f"id-{json.get('name', '')}"}

            return R()

    cfg = Config(
        model_dir=Path("/tmp"),
        provider="none",
        default_model="",
        surreal_user="root",
        surreal_password="x" * 24,
    )
    register_memory_credential(FakeClient(), memory_port=8767, cfg=cfg)
    posted = [j for p, j in created if p == "/api/credentials"]
    assert any(j.get("name") == "Memory (local)" for j in posted)
    assert any(j.get("provider") == "openai_compatible" for j in posted)
