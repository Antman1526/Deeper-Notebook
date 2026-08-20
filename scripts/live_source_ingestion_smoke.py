#!/usr/bin/env python3
"""Live source-ingestion smoke for a running native Deeper Notebook app.

This is intentionally outside pytest's normal suite. It talks to a real
running API process and proves the path that fixture browser tests cannot:
create source -> worker finishes -> extracted text is readable from the API.
Optionally, it can also create a source-chat session and stream one answer.
"""

from __future__ import annotations

import argparse
import http.server
import json
import os
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

DEFAULT_TEXT = (
    "Deeper Notebook live ingestion smoke marker {marker}. "
    "This source proves native API ingestion, extraction, embedding, and "
    "source detail retrieval are wired together."
)


@dataclass(frozen=True)
class ApiResponse:
    status: int
    data: Any
    text: str


class SmokeFailure(RuntimeError):
    pass


def build_api_url(base_url: str, path: str, api_prefix: str = "/api") -> str:
    base = base_url.rstrip("/")
    clean_path = "/" + path.lstrip("/")
    clean_prefix = api_prefix.rstrip("/")
    base_path = urlsplit(base).path.rstrip("/")
    if clean_path.startswith(clean_prefix + "/") or base_path.endswith(clean_prefix):
        return base + clean_path
    return base + clean_prefix + clean_path


def request_json(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    token: str | None = None,
    timeout: float = 30,
) -> ApiResponse:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = Request(url, data=body, headers=headers, method=method.upper())
    try:
        with urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            return ApiResponse(
                status=resp.status,
                data=json.loads(text) if text else None,
                text=text,
            )
    except HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        raise SmokeFailure(
            f"{method} {url} failed with HTTP {exc.code}: {text}"
        ) from exc
    except URLError as exc:
        raise SmokeFailure(f"{method} {url} failed: {exc}") from exc


def request_multipart(
    url: str,
    *,
    fields: dict[str, str],
    files: dict[str, tuple[str, bytes, str]],
    token: str | None = None,
    timeout: float = 30,
) -> ApiResponse:
    boundary = f"----dn-smoke-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(
                    "utf-8"
                ),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )
    for name, (filename, content, content_type) in files.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                (
                    f'Content-Disposition: form-data; name="{name}"; '
                    f'filename="{filename}"\r\n'
                ).encode("utf-8"),
                f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
                content,
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    headers = {
        "Accept": "application/json",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(url, data=b"".join(chunks), headers=headers, method="POST")
    try:
        with urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            return ApiResponse(
                status=resp.status,
                data=json.loads(text) if text else None,
                text=text,
            )
    except HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        raise SmokeFailure(f"POST {url} failed with HTTP {exc.code}: {text}") from exc
    except URLError as exc:
        raise SmokeFailure(f"POST {url} failed: {exc}") from exc


def source_is_processing(status: str | None) -> bool:
    return status in {"new", "queued", "running", "unknown"}


def source_is_ready(
    detail: dict[str, Any],
    marker: str,
    *,
    require_embedding: bool = True,
) -> bool:
    full_text = str(detail.get("full_text") or "")
    if marker not in full_text:
        return False
    if require_embedding and detail.get("embedded") is False:
        return False
    quality = detail.get("extraction_quality")
    return quality not in {"pending", "no_text"}


def create_text_source(args: argparse.Namespace, marker: str) -> dict[str, Any]:
    content = args.content or DEFAULT_TEXT.format(marker=marker)
    payload = {
        "type": "text",
        "title": args.title or f"Live ingestion smoke {marker}",
        "content": content,
        "topics": ["smoke", "source-ingestion"],
        "provenance": {
            "origin": "live_source_ingestion_smoke",
            "marker": marker,
        },
        "source_type": "text",
        "embed": not args.skip_embedding,
        "delete_source": False,
        "async_processing": True,
    }
    if args.notebook_id:
        payload["notebook_id"] = args.notebook_id
        payload["notebooks"] = [args.notebook_id]
    response = request_json(
        "POST",
        build_api_url(args.base_url, "/sources/json", args.api_prefix),
        payload=payload,
        token=args.token,
        timeout=args.request_timeout,
    )
    if not isinstance(response.data, dict) or not response.data.get("id"):
        raise SmokeFailure(
            f"Create source returned unexpected payload: {response.text}"
        )
    return response.data


def source_form_fields(
    args: argparse.Namespace,
    *,
    source_type: str,
    title: str,
    marker: str,
    url: str | None = None,
) -> dict[str, str]:
    fields = {
        "type": source_type,
        "title": title,
        "topics": json.dumps(["smoke", "source-ingestion"]),
        "provenance": json.dumps(
            {
                "origin": "live_source_ingestion_smoke",
                "marker": marker,
                "source_kind": source_type,
            }
        ),
        "source_type": source_type,
        "embed": "false" if args.skip_embedding else "true",
        "delete_source": "false",
        "async_processing": "true",
    }
    if args.notebook_id:
        fields["notebook_id"] = args.notebook_id
        fields["notebooks"] = json.dumps([args.notebook_id])
    if url:
        fields["url"] = url
    return fields


def create_upload_source(args: argparse.Namespace, marker: str) -> dict[str, Any]:
    if args.upload_file:
        upload_path = args.upload_file
        content = upload_path.read_bytes()
        filename = upload_path.name
    else:
        filename = f"onp-live-smoke-{marker}.txt"
        content = (
            f"Deeper Notebook upload smoke marker {marker}. "
            "This proves multipart upload ingestion, extraction, embedding, "
            "and source detail retrieval are wired together."
        ).encode("utf-8")
    response = request_multipart(
        build_api_url(args.base_url, "/sources", args.api_prefix),
        fields=source_form_fields(
            args,
            source_type="upload",
            title=args.title or f"Live upload smoke {marker}",
            marker=marker,
        ),
        files={"file": (filename, content, "text/plain")},
        token=args.token,
        timeout=args.request_timeout,
    )
    if not isinstance(response.data, dict) or not response.data.get("id"):
        raise SmokeFailure(
            f"Create upload source returned unexpected payload: {response.text}"
        )
    return response.data


def create_link_source(
    args: argparse.Namespace, marker: str, url: str
) -> dict[str, Any]:
    payload = {
        "type": "link",
        "title": args.title or f"Live link smoke {marker}",
        "url": url,
        "topics": ["smoke", "source-ingestion"],
        "provenance": {
            "origin": "live_source_ingestion_smoke",
            "marker": marker,
            "source_kind": "link",
        },
        "source_type": "link",
        "embed": not args.skip_embedding,
        "delete_source": False,
        "async_processing": True,
    }
    if args.notebook_id:
        payload["notebook_id"] = args.notebook_id
        payload["notebooks"] = [args.notebook_id]
    response = request_json(
        "POST",
        build_api_url(args.base_url, "/sources/json", args.api_prefix),
        payload=payload,
        token=args.token,
        timeout=args.request_timeout,
    )
    if not isinstance(response.data, dict) or not response.data.get("id"):
        raise SmokeFailure(
            f"Create link source returned unexpected payload: {response.text}"
        )
    return response.data


def start_marker_http_server(
    marker: str,
) -> tuple[http.server.ThreadingHTTPServer, str]:
    class MarkerHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = (
                "<!doctype html><html><body>"
                f"<h1>Deeper Notebook link smoke {marker}</h1>"
                f"<p>The unique ingestion marker is {marker}.</p>"
                "</body></html>"
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *_args: Any) -> None:
            return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), MarkerHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    return server, f"http://127.0.0.1:{port}/smoke-{marker}.html"


def wait_for_source(
    args: argparse.Namespace, source_id: str, marker: str
) -> dict[str, Any]:
    deadline = time.monotonic() + args.timeout
    last_status: dict[str, Any] | None = None
    while True:
        status_resp = request_json(
            "GET",
            build_api_url(
                args.base_url,
                f"/sources/{quote(source_id, safe=':')}/status",
                args.api_prefix,
            ),
            token=args.token,
            timeout=args.request_timeout,
        )
        last_status = status_resp.data if isinstance(status_resp.data, dict) else {}
        status = last_status.get("status")
        if status == "failed":
            raise SmokeFailure(f"Source processing failed: {json.dumps(last_status)}")

        detail = request_json(
            "GET",
            build_api_url(
                args.base_url, f"/sources/{quote(source_id, safe=':')}", args.api_prefix
            ),
            token=args.token,
            timeout=args.request_timeout,
        ).data
        if isinstance(detail, dict) and source_is_ready(
            detail,
            marker,
            require_embedding=not args.skip_embedding,
        ):
            return detail

        if not source_is_processing(status) and time.monotonic() >= deadline:
            break
        if time.monotonic() >= deadline:
            break
        time.sleep(args.poll_interval)

    raise SmokeFailure(
        "Timed out waiting for source readiness. "
        f"last_status={json.dumps(last_status, sort_keys=True)}"
    )


def maybe_run_source_chat(
    args: argparse.Namespace,
    source_id: str,
    marker: str,
) -> dict[str, Any] | None:
    if not args.chat_question:
        return None

    session = request_json(
        "POST",
        build_api_url(
            args.base_url,
            f"/sources/{quote(source_id, safe=':')}/chat/sessions",
            args.api_prefix,
        ),
        payload={
            "source_id": source_id.removeprefix("source:"),
            "title": f"Smoke chat {marker}",
        },
        token=args.token,
        timeout=args.request_timeout,
    ).data
    if not isinstance(session, dict) or not session.get("id"):
        raise SmokeFailure(
            f"Create source-chat session returned unexpected payload: {session}"
        )

    stream_url = build_api_url(
        args.base_url,
        f"/sources/{quote(source_id, safe=':')}/chat/sessions/"
        f"{quote(str(session['id']), safe=':')}/messages",
        args.api_prefix,
    )
    req = Request(
        stream_url,
        data=json.dumps({"message": args.chat_question}).encode("utf-8"),
        headers={
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {args.token}"} if args.token else {}),
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=args.chat_timeout) as resp:
            buffer = ""
            saw_answer = False
            started = time.monotonic()
            while time.monotonic() - started < args.chat_timeout:
                chunk = resp.readline()
                if not chunk:
                    break
                line = chunk.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                buffer += line + "\n"
                if (
                    "ai_message_delta" in line
                    or '"type":"done"' in line
                    or '"type": "done"' in line
                ):
                    saw_answer = True
                if '"type":"done"' in line or '"type": "done"' in line:
                    break
            if not saw_answer:
                raise SmokeFailure(
                    f"Source chat stream produced no answer events:\n{buffer[-2000:]}"
                )
            return {"session_id": session["id"], "stream_observed": True}
    except HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        raise SmokeFailure(f"Source chat failed with HTTP {exc.code}: {text}") from exc
    except URLError as exc:
        raise SmokeFailure(f"Source chat failed: {exc}") from exc


def delete_source(args: argparse.Namespace, source_id: str) -> None:
    request_json(
        "DELETE",
        build_api_url(
            args.base_url, f"/sources/{quote(source_id, safe=':')}", args.api_prefix
        ),
        token=args.token,
        timeout=args.request_timeout,
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("DEEPER_NOTEBOOK_API_BASE_URL", "http://127.0.0.1:5055"),
        help="Running native API base URL. Default: %(default)s",
    )
    parser.add_argument("--api-prefix", default="/api")
    parser.add_argument("--token", default=os.environ.get("DEEPER_NOTEBOOK_API_TOKEN"))
    parser.add_argument(
        "--notebook-id", default=os.environ.get("DEEPER_NOTEBOOK_SMOKE_NOTEBOOK_ID")
    )
    parser.add_argument("--title")
    parser.add_argument("--content")
    parser.add_argument(
        "--source-kind",
        choices=("text", "upload", "link", "all"),
        default="text",
        help="Source lane to prove. Use 'all' for text, upload, and link.",
    )
    parser.add_argument(
        "--upload-file",
        type=lambda value: Path(value).expanduser(),
        help="Optional file to use for upload smoke. Defaults to generated text.",
    )
    parser.add_argument(
        "--link-url",
        help="Optional URL to use for link smoke. Defaults to a temporary local page.",
    )
    parser.add_argument(
        "--skip-embedding",
        action="store_true",
        help="Verify extraction only. Use when the native app has no embedding model configured.",
    )
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--poll-interval", type=float, default=2)
    parser.add_argument("--request-timeout", type=float, default=30)
    parser.add_argument("--chat-question")
    parser.add_argument("--chat-timeout", type=float, default=90)
    parser.add_argument("--keep-source", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    marker = f"onp-smoke-{uuid.uuid4().hex[:10]}"
    source_ids: list[str] = []
    local_server: http.server.ThreadingHTTPServer | None = None
    try:
        source_kinds = (
            ["text", "upload", "link"]
            if args.source_kind == "all"
            else [args.source_kind]
        )
        results: list[dict[str, Any]] = []
        for source_kind in source_kinds:
            if source_kind == "text":
                created = create_text_source(args, marker)
            elif source_kind == "upload":
                created = create_upload_source(args, marker)
            else:
                link_url = args.link_url
                if not link_url:
                    local_server, link_url = start_marker_http_server(marker)
                created = create_link_source(args, marker, link_url)

            source_id = str(created["id"])
            source_ids.append(source_id)
            detail = wait_for_source(args, source_id, marker)
            chat = maybe_run_source_chat(args, source_id, marker)
            results.append(
                {
                    "source_kind": source_kind,
                    "source_id": source_id,
                    "embedded": detail.get("embedded"),
                    "extracted_char_count": detail.get("extracted_char_count"),
                    "extraction_quality": detail.get("extraction_quality"),
                    "chat": chat,
                }
            )

        result = {
            "ok": True,
            "marker": marker,
            "sources": results,
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except SmokeFailure as exc:
        print(f"live source ingestion smoke failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if local_server is not None:
            local_server.shutdown()
        if not args.keep_source:
            for source_id in source_ids:
                try:
                    delete_source(args, source_id)
                except SmokeFailure as exc:
                    print(
                        f"warning: cleanup failed for {source_id}: {exc}",
                        file=sys.stderr,
                    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
