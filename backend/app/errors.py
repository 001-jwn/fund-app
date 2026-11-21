"""Public API errors.

Every error body is exactly {"detail": <plain sentence>, "code": <code>}.
detail is one of the agreed sentences. It never includes a code name, a
field list, a stack trace, or a vendor name.

Upstream Finnhub and SEC failures are not API errors. Callers keep serving
whatever is already cached. rate_limited and data_unavailable are reserved:
this app does not limit its own traffic, and it does not answer with
data_unavailable while a cached value can still be served.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("fund.errors")

USER_NOT_FOUND = "We couldn't find your saved picks. Please choose your interests again."
COMPANY_NOT_FOUND = "We couldn't find that company."
COMPANY_NOT_ACTIVE = "That company isn't available right now."
OUTSIDE_INTERESTS = "That company doesn't match the interests you picked."
UNKNOWN_INTEREST = (
    "That interest isn't available. Please pick from Gaming, Travel, Music, or Automobile."
)
PICK_ONE_INTEREST = "Pick at least one interest."

NOT_FOUND = "We couldn't find that. Please try again."
BAD_REQUEST = "That didn't work. Please try again."
RATE_LIMITED = "Lots of requests right now. Wait a moment and try again."
DATA_UNAVAILABLE = "This information isn't available yet. Check back a little later."
SERVER_ERROR = "Something went wrong. Try again."

FALLBACKS = {
    "not_found": NOT_FOUND,
    "bad_request": BAD_REQUEST,
    "rate_limited": RATE_LIMITED,
    "data_unavailable": DATA_UNAVAILABLE,
    "server_error": SERVER_ERROR,
}

# Sentences a route is allowed to show. Anything else uses the code's fallback
# so a raw exception, a field list, or a vendor message cannot leak.
_ALLOWED_DETAILS = {
    USER_NOT_FOUND,
    COMPANY_NOT_FOUND,
    COMPANY_NOT_ACTIVE,
    OUTSIDE_INTERESTS,
    UNKNOWN_INTEREST,
    PICK_ONE_INTEREST,
    *FALLBACKS.values(),
}

_LEGACY_DETAILS = {
    "User not found.": USER_NOT_FOUND,
    "Company not found.": COMPANY_NOT_FOUND,
    "That company is not active.": COMPANY_NOT_ACTIVE,
    "That company is outside the interests you picked.": OUTSIDE_INTERESTS,
}


def code_for_status(status: int) -> str:
    """Map an HTTP status onto one agreed code. Existing statuses stay put."""
    if status == 404:
        return "not_found"
    if status == 429:
        return "rate_limited"
    # Reserved for a route that has no cached value and cannot answer.
    if status == 503:
        return "data_unavailable"
    if 500 <= status <= 599:
        return "server_error"
    return "bad_request"


def public_detail(detail: object, code: str) -> str:
    """One plain sentence. Unknown or unsafe text becomes the code's fallback."""
    if isinstance(detail, str):
        if detail in _ALLOWED_DETAILS:
            return detail
        mapped = _LEGACY_DETAILS.get(detail)
        if mapped is not None:
            return mapped
        # The old onboarding error included the rejected text. Never echo it.
        if detail.startswith("Unknown interest"):
            return UNKNOWN_INTEREST
    return FALLBACKS[code]


def error_body(status: int, detail: object = None, code: str | None = None) -> dict[str, str]:
    chosen = code if code in FALLBACKS else code_for_status(status)
    return {"detail": public_detail(detail, chosen), "code": chosen}


def json_error(
    status: int,
    detail: object = None,
    code: str | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    # headers keeps Allow on a 405. The body stays the two agreed fields.
    return JSONResponse(
        status_code=status,
        content=error_body(status, detail, code),
        headers=dict(headers) if headers else None,
    )


async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    return json_error(exc.status_code, exc.detail, headers=exc.headers)


async def validation_exception_handler(_request: Request, _exc: RequestValidationError) -> JSONResponse:
    # 422 stays 422. The field list is not part of the body.
    return json_error(422, None, "bad_request")


async def unhandled_exception_handler(request: Request, _exc: Exception) -> JSONResponse:
    # The traceback stays in the server log. The client only sees the fallback.
    logger.exception("Unhandled API error on %s %s", request.method, request.url.path)
    return json_error(500, None, "server_error")


class UnhandledErrorMiddleware:
    """Turn an unhandled error into the server_error JSON before CORS sees it.

    Starlette's own server-error handler sits outside user middleware, so a 500
    produced there has no CORS headers. This wrapper is registered inside
    CORSMiddleware and does not re-raise, so the browser can read the body.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            if response_started:
                raise
            response = await unhandled_exception_handler(Request(scope), exc)
            await response(scope, receive, send)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
