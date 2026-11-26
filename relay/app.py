"""sayso relay: keyless. Serves the phone web app and forwards ciphertext between a broker and
its paired phone through mailboxes. It holds no keys and can't read, alter (undetected) or
approve anything; see PROTOCOL.html.

  uvicorn relay.app:app --host 0.0.0.0 --port $PORT
"""
from __future__ import annotations

from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .mailbox import MAX_BYTES, Mailboxes

STATIC = Path(__file__).parent / "static"
boxes = Mailboxes()

# The app may load only its own files and talk only to this relay.
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")


async def put(request: Request) -> Response:
    box, slot = request.path_params["box"], request.path_params["slot"]
    if not boxes.valid(box, slot):
        return Response(status_code=404)
    body = await request.body()
    if len(body) > MAX_BYTES:
        return Response("too large", status_code=413)
    try:
        seq = boxes.put(box, slot, body)
    except ValueError as e:
        return Response(str(e), status_code=503)
    return JSONResponse({"seq": seq})


async def get(request: Request) -> Response:
    box, slot = request.path_params["box"], request.path_params["slot"]
    if not boxes.valid(box, slot):
        return Response(status_code=404)
    try:
        after = int(request.query_params.get("after", "0"))
        wait = min(max(float(request.query_params.get("wait", "0")), 0.0), 25.0)
        m = await boxes.get(box, slot, after, wait)
    except ValueError as e:
        return Response(str(e), status_code=503 if "busy" in str(e) else 400)
    if m is None:
        return Response(status_code=204, headers={"Cache-Control": "no-store"})
    return Response(m.data, media_type="application/octet-stream",
                    headers={"X-Seq": str(m.seq), "Cache-Control": "no-store"})


async def health(_: Request) -> Response:
    return JSONResponse({"ok": True})


class SecureStatic(StaticFiles):
    async def get_response(self, path, scope):
        r = await super().get_response(path, scope)
        r.headers.update({"Content-Security-Policy": CSP, "X-Content-Type-Options": "nosniff",
                          "Referrer-Policy": "no-referrer", "Cache-Control": "no-cache"})
        return r


app = Starlette(routes=[
    Route("/healthz", health),
    Route("/mb/{box}/{slot}", put, methods=["PUT"]),
    Route("/mb/{box}/{slot}", get, methods=["GET"]),
    Mount("/", SecureStatic(directory=STATIC, html=True)),
])
