"""Bound requests before multipart/JSON parsing, within the private demo boundary."""

import asyncio
from tempfile import SpooledTemporaryFile
from urllib.parse import urlsplit

from starlette.responses import JSONResponse

from backend.config import settings


class RequestBoundaryMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = scope["headers"]

        async def reject(status, code, message):
            response = JSONResponse(
                {"error": {"code": code, "message": message}},
                status_code=status,
                headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
            )
            await response(scope, receive, send)

        hosts = [value.decode("latin-1") for key, value in headers if key == b"host"]
        try:
            if len(hosts) != 1 or any(c in hosts[0] for c in "/\\?#@"):
                raise ValueError
            host_url = urlsplit("http://" + hosts[0])
            host_url.port  # Validate a supplied port as well as the hostname.
            if host_url.hostname not in {
                h.strip().lower() for h in settings.allowed_hosts.split(",")
            }:
                return await reject(400, "untrusted_host", "The requested host is not allowed.")
        except ValueError:
            return await reject(400, "invalid_host", "Use one valid Host header.")
        origins = [value.decode("latin-1") for key, value in headers if key == b"origin"]
        allowed = {origin.strip() for origin in settings.allowed_origins.split(",")}
        allowed.add(f"{scope['scheme']}://{hosts[0]}")
        if origins and (len(origins) != 1 or origins[0] not in allowed):
            return await reject(
                403, "untrusted_origin", "Requests from this browser origin are not allowed."
            )
        content_type = dict(headers).get(b"content-type", b"").split(b";", 1)[0].strip().lower()
        # Multipart framing gets a separate allowance; each file still has its exact byte limit.
        limit = (
            settings.max_upload_bytes + 65536
            if content_type == b"multipart/form-data"
            else settings.max_json_bytes
        )
        lengths = [value for key, value in headers if key == b"content-length"]
        if lengths:
            if len(lengths) != 1 or len(lengths[0]) > 20 or not lengths[0].isdigit():
                return await reject(
                    400, "invalid_content_length", "Use one valid Content-Length header."
                )
            if int(lengths[0]) > limit:
                return await reject(
                    413, "request_too_large", "Request exceeds the configured body limit."
                )

        async def private_send(message):
            if message["type"] == "http.response.start":
                response_headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() not in {b"cache-control", b"x-content-type-options"}
                ]
                message = {
                    **message,
                    "headers": response_headers
                    + [(b"cache-control", b"no-store"), (b"x-content-type-options", b"nosniff")],
                }
            await send(message)

        with SpooledTemporaryFile(max_size=1024 * 1024) as body:
            size = 0
            try:
                async with asyncio.timeout(settings.upload_timeout_seconds):
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        chunk = message.get("body", b"")
                        size += len(chunk)
                        if size > limit:
                            return await reject(
                                413,
                                "request_too_large",
                                "Request exceeds the configured body limit.",
                            )
                        body.write(chunk)
                        if not message.get("more_body", False):
                            break
            except TimeoutError:
                return await reject(
                    408, "upload_timeout", "The request body took too long to arrive."
                )
            body.seek(0)
            replayed = False

            async def replay():
                nonlocal replayed
                if replayed:
                    return await receive()
                chunk = body.read(65536)
                more = body.tell() < size
                replayed = not more
                return {"type": "http.request", "body": chunk, "more_body": more}

            await self.app(scope, replay, private_send)
