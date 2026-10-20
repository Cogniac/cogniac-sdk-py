"""
Cogniac API common definitions

Copyright (C) 2016 Cogniac Corporation
"""

import json

from tenacity import retry, stop_after_attempt, stop_after_delay, wait_exponential, retry_if_exception
from httpx import ConnectError


class CredentialError(Exception):
    """Invalid Username/Password Credentials"""
    status_code = 401


class ServerError(Exception):
    """Unknown server-side error. Operation can be retried."""


class ClientError(Exception):
    """Error with the client-supplied parameters.
    Operation should not be retried with the same parameters."""
    status_code = 400

    def __init__(self, message, status_code=None):
        Exception.__init__(self)
        self.message = message
        if status_code is not None:
            self.status_code = status_code

    def __str__(self):
        return self.message


class CaptureConsumedError(ServerError):
    """detections(wait_capture_id=...) cannot return this capture's detections any more:
    the API already consumed its completion message (504 capture_timeout with
    capture_consumed true), or its result queue is gone (503). Re-polling the same
    capture_id will not help; start a new capture."""

    def __init__(self, capture_id, error):
        ServerError.__init__(self, "Capture %s cannot be polled again, start a new capture: %s" % (capture_id, error))
        self.capture_id = capture_id
        self.status_code = error.status_code
        self.response = getattr(error, 'response', None)


def credential_error(exception):
    return isinstance(exception, CredentialError)


def rate_limit_error(exception):
    """True only for HTTP 429 responses — safe to retry on non-idempotent methods."""
    return isinstance(exception, ClientError) and getattr(exception, 'status_code', None) == 429


def rate_limit_or_credential_error(exception):
    """True for 429 or expired credentials — for non-idempotent methods (_post, _delete, _put).

    Intentionally excludes 5xx ServerError: retrying a POST/DELETE on a server
    error risks duplicate submissions. 429 is always safe to retry; credential
    expiry requires re-authentication.
    """
    return rate_limit_error(exception) or credential_error(exception)


def server_or_credential_error(exception):
    """True for any retryable error (5xx, 429, connect errors, or expired credentials).

    Use on idempotent methods (_get, _head) where retrying on any server-side
    error is safe. Non-idempotent methods (_post, _delete) should use
    rate_limit_error + credential_error instead.
    """
    return server_error(exception) or credential_error(exception)


def server_error(exception):
    """Return True if the operation should be retried.

    Retries on ServerError (5xx), connection errors, and HTTP 429 rate-limit
    responses (a ClientError carrying status_code 429): 429 is transient, so a
    bulk operation should back off and retry rather than die on the first
    throttle. Retries use the caller's exponential backoff; the server's
    Retry-After header (when present) is recorded on the exception as
    ``retry_after`` for callers/waits that want to honor it.
    """
    if isinstance(exception, (ServerError, ConnectError)):
        return True
    return isinstance(exception, ClientError) and getattr(exception, 'status_code', None) == 429


# Default request timeout for application evaluate(), the public evaluations route's gateway timeout.
EVALUATE_TIMEOUT = 3600


def server_error_not_gateway_timeout(exception):
    """server_error, except a 504: the gateway gave up on a long request, and repeating
    it would likely wait just as long again."""
    return server_error(exception) and getattr(exception, 'status_code', None) != 504


# Request timeout for detections(wait_capture_id=...): above the API's 60s capture deadline
# and the 70s proxy timeout in front of it, so the client sees the API's 504 instead of
# hanging up first.
CAPTURE_WAIT_TIMEOUT = 75

# Re-poll the same capture_id only while the capture is younger than this (seconds,
# counted from the first poll).
CAPTURE_WAIT_MAX_AGE = 180


def capture_poll_error(exception):
    """server_error for a wait_capture_id poll: re-poll the same capture_id, except on a
    500 (report it) or a CaptureConsumedError (the caller must start a new capture)."""
    if isinstance(exception, CaptureConsumedError) or getattr(exception, 'status_code', None) == 500:
        return False
    return server_error(exception)


def raise_capture_error(exception, capture_id):
    """Raise CaptureConsumedError when a wait_capture_id poll failed in a way re-polling
    cannot fix: a 503, or a 504 capture_timeout whose capture_consumed is true. Return for
    anything else, including a 504 whose capture_consumed is false, null or absent (a
    proxy's HTML 504 has no JSON body)."""
    status = getattr(exception, 'status_code', None)
    consumed = None
    if status == 504:
        try:
            body = exception.response.json()
            if body.get('error') == 'capture_timeout':
                consumed = body.get('capture_consumed')
        except (AttributeError, ValueError):
            pass
    if status == 503 or consumed is True:
        raise CaptureConsumedError(capture_id, exception) from exception


def parse_json_str(val):
    """Return val parsed as JSON if it's a string, otherwise return it unchanged.

    The API occasionally serializes app_data and custom_data as JSON strings
    instead of inline objects. Callers should not need to guard for this.
    Non-string values (dict, list, None) are passed through untouched.
    A string that is not valid JSON is also returned as-is.
    """
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (ValueError, TypeError):
            pass
    return val


def raise_errors(response):
    """
    raise ServerError or ClientError based on requests response as appropriate
    """
    if response.status_code >= 500:
        msg = "ServerError (%d): %s" % (response.status_code, response.text)
        exc = ServerError(msg)
        exc.status_code = response.status_code
        exc.response = response
        raise exc

    if response.status_code == 401:
        msg = "Invalid username password credentials (%d): %s" % (response.status_code, response.text)
        raise CredentialError(msg)

    if response.status_code == 429:
        # rate-limited: retryable (see server_error). Record Retry-After if present.
        msg = "RateLimited (429): %s" % response.text
        exc = ClientError(msg, 429)
        retry_after = response.headers.get('Retry-After')
        if retry_after:
            try:
                exc.retry_after = float(retry_after)
            except (TypeError, ValueError):
                pass
        raise exc

    if response.status_code >= 400:
        msg = "ClientError (%d): %s" % (response.status_code, response.text)
        raise ClientError(msg, response.status_code)
