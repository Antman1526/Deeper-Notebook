"""v0.8.103 — seam tests: config -> resolution -> routing -> a real HTTP call.

WHY THIS FILE EXISTS

Three catastrophic defects shipped while every unit test passed, because each
one lived in the *composition* rather than in any single unit:

  1. Auto-route hard-failed (v0.8.100). `pick_provider` is a correct pure
     function with passing tests. `_measured_local_chat_model_id` works as
     designed. Compose them on an install with no benchmark history and every
     chat turn died with "No model available — neither local nor cloud" while a
     perfectly valid `default_chat_model` sat unused.

  2. MLX models registered under a name no server would answer to (v0.8.97).
     `mlx_lm.server` keys its loaded model on the exact `--model` string it was
     launched with and 404s anything else; registration stored a prettified
     display name. The model row was valid, the credential was valid, the server
     was healthy — and no turn could ever complete.

  3. A `default_chat_model` pointing at a legacy env-migration artifact — a row
     literally named `default_model`. Structurally valid, so nothing static can
     reject it. Only the model server can.

Every one of those is invisible to a unit test that mocks the layer below it.
They are visible the moment something drives the whole chain against a server
that behaves like a real one.

WHAT MAKES THE FAKE SERVER USEFUL

`_ProtocolFaithfulModelServer` is not a stub that says yes. It reproduces the
one upstream behaviour that turns a wire-id mismatch from silent into loud:
**404 on any `model` value it was not launched with**, exactly as mlx_lm does.
Verified live against a real mlx_lm server during the v0.8.97 investigation:

    model="/…/MLX/PocketAiHub__Qwen3.8-27B-MLX-6bit"  -> 200, generates
    model="PocketAiHub/Qwen3.8-27B-MLX-6bit"          -> 404 Repository Not Found

A fake that answered every request would pass all four tests below while
catching none of the three bugs. That fidelity is the entire point.

These tests deliberately do NOT mock provision, the router, the model manager,
or httpx. The only fake is the process at the far end of the socket.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
import pytest_asyncio

from deeper_notebook.ai.models import DefaultModels, Model, model_manager
from deeper_notebook.domain.credential import Credential

pytestmark = pytest.mark.integration_surreal

# The wire id the fake server will accept. Deliberately shaped like a real MLX
# launch reference — a filesystem path — because that is the shape that broke:
# the prettified "vendor/model" display name is what got registered instead.
WIRE_MODEL_ID = "/models/MLX/vendor__Model-7B-MLX-6bit"
PRETTIFIED_DISPLAY_NAME = "vendor/Model-7B-MLX-6bit"
REPLY_TEXT = "seam-test-reply"


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # noqa: D102 - silence per-request stderr noise
        return

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path.rstrip("/").endswith("/models"):
            self._json(200, {"object": "list", "data": [{"id": WIRE_MODEL_ID}]})
            return
        self._json(404, {"error": {"message": "not found"}})

    def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler API
        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            self._json(400, {"error": {"message": "malformed body"}})
            return
        self.server.seen_models.append(payload.get("model"))  # type: ignore[attr-defined]

        # THE fidelity that matters: an unknown model id is a hard 404, not a
        # best-effort completion. This is what turns a wire-id mismatch from a
        # silent no-op into an error a test can see.
        if payload.get("model") != WIRE_MODEL_ID:
            self._json(
                404,
                {
                    "error": {
                        "message": f"Repository Not Found for model {payload.get('model')!r}"
                    }
                },
            )
            return

        self._json(
            200,
            {
                "id": "chatcmpl-seam",
                "object": "chat.completion",
                "created": 0,
                "model": WIRE_MODEL_ID,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": REPLY_TEXT},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            },
        )


@pytest.fixture(scope="module")
def model_server():
    """A real socket speaking the OpenAI protocol, with mlx_lm's 404 semantics."""
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    server.seen_models = []  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _base_url(server: HTTPServer) -> str:
    host, port = server.server_address[0], server.server_address[1]
    return f"http://{host}:{port}/v1"


@pytest_asyncio.fixture
async def local_credential(clean_namespace, model_server):
    # `clean_namespace` (tests/integration/conftest.py) depends on the
    # session-scoped `surreal_db`, which mints the throwaway namespace and runs
    # migrations — without it the pool connects with namespace/database unset
    # and every call dies in the driver with "params.0: Input should be a valid
    # string". Depending on `clean_namespace` rather than `surreal_db` directly
    # also closes the connection pool between tests: pytest-asyncio gives each
    # test its own event loop, and the pooled WebSocket is loop-bound, so the
    # second test in this file otherwise fails with "got Future attached to a
    # different loop". Both failures were observed here before this line.
    credential = Credential(
        name="Seam Test (local)",
        provider="openai_compatible",
        modalities=["language"],
        base_url=_base_url(model_server),
        api_key=None,
    )
    await credential.save()
    yield credential
    try:
        await credential.delete()
    except Exception:  # pragma: no cover - teardown best effort
        pass


async def _make_model(name: str, credential: Credential) -> Model:
    model = Model(
        name=name,
        provider="openai_compatible",
        type="language",
        credential=credential.id,
    )
    await model.save()
    return model


async def _set_chat_default(model_id: str | None, **extra) -> None:
    # No cache to invalidate: model_manager.get_defaults() calls
    # DefaultModels.get_instance(), which reads the singleton row from the DB on
    # every call. Writing the row is sufficient for the next resolution to see it.
    defaults = await model_manager.get_defaults()
    payload = defaults.model_dump()
    payload["default_chat_model"] = model_id
    payload.update(extra)
    await DefaultModels(**payload).update()


@pytest.mark.asyncio
async def test_a_chat_turn_completes_against_a_real_socket(
    local_credential, model_server
):
    """The whole chain: defaults -> model row -> credential -> HTTP -> parsed reply.

    Nothing below provision is mocked. If resolution, base_url plumbing, the
    adapter, or response parsing breaks, this fails — none of which a unit test
    with a mocked provider can observe.
    """
    from deeper_notebook.ai.provision import provision_langchain_chat_model

    model = await _make_model(WIRE_MODEL_ID, local_credential)
    await _set_chat_default(model.id)

    chat = await provision_langchain_chat_model("hello")
    result = await chat.ainvoke("hello")

    assert REPLY_TEXT in str(getattr(result, "content", result))
    assert model_server.seen_models  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_registering_a_prettified_name_fails_loudly_not_silently(
    local_credential, model_server
):
    """The v0.8.97 MLX defect, reproduced at the seam.

    A model row registered under a display name the server does not accept is
    structurally perfect — valid row, valid credential, healthy server — and can
    never answer. The registered name IS the wire `model` field, so the only
    thing that can catch a mismatch is a server that rejects unknown ids.
    """
    from deeper_notebook.ai.provision import provision_langchain_chat_model

    model = await _make_model(PRETTIFIED_DISPLAY_NAME, local_credential)
    await _set_chat_default(model.id)

    chat = await provision_langchain_chat_model("hello")
    with pytest.raises(Exception) as excinfo:
        await chat.ainvoke("hello")

    # The failure must name the rejected model, not surface as a timeout or a
    # generic "no model available" — that difference is the whole bug report.
    message = str(excinfo.value)
    assert (
        "404" in message
        or "Repository Not Found" in message
        or "not found" in message.lower()
    )


@pytest.mark.asyncio
async def test_auto_route_with_no_benchmark_history_still_answers(
    local_credential, model_server
):
    """The v0.8.100 defect at the seam.

    Auto-route ON, no benchmark history (so no measured local candidate), and no
    cloud credential. Before the fix, `pick_provider` received two Nones and
    raised its step-5 "impossible state" on every turn while this very default
    sat configured and usable.
    """
    from deeper_notebook.ai.provision import provision_langchain_chat_model

    model = await _make_model(WIRE_MODEL_ID, local_credential)
    await _set_chat_default(model.id, auto_route_enabled=True, auto_route_cloud=None)

    chat = await provision_langchain_chat_model("hello")
    result = await chat.ainvoke("hello")

    assert REPLY_TEXT in str(getattr(result, "content", result))


@pytest.mark.asyncio
async def test_a_dangling_chat_default_is_reported_not_silently_ignored(
    local_credential,
):
    """A default pointing at a deleted row must resolve to None, not explode.

    This is the shape of the `default_model` env-migration artifact: the id is
    well-formed, so nothing static rejects it. `get_default_model` is expected to
    catch the lookup failure and return None (logging which setting is at
    fault) rather than raising an unhandled error out of the chat path.
    """
    model = await _make_model(WIRE_MODEL_ID, local_credential)
    model_id = model.id
    await model.delete()
    await _set_chat_default(model_id)

    resolved = await model_manager.get_default_model("chat")
    assert resolved is None
