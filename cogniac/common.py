"""
Cogniac API common definitions

Copyright (C) 2016 Cogniac Corporation
"""

import json

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
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


def maybe_json(value):
    """If value is a JSON object/array serialized as a string, return the parsed
    structure; otherwise return value unchanged. Some API fields (e.g. subject
    app_data, media custom_data) are occasionally returned as JSON strings."""
    if isinstance(value, str):
        s = value.strip()
        if s[:1] in ('{', '['):
            try:
                return json.loads(value)
            except ValueError:
                return value
    return value


def normalize_association(record):
    """Normalize JSON-string fields the API sometimes returns serialized:
    top-level ``app_data`` / ``custom_data`` and the same keys nested under a
    ``media`` or ``subject`` stanza. Mutates and returns the record so callers
    always see dicts/lists rather than strings. See issue #157."""
    if not isinstance(record, dict):
        return record
    for key in ('app_data', 'custom_data'):
        if isinstance(record.get(key), str):
            record[key] = maybe_json(record[key])
    for nested in ('media', 'subject'):
        sub = record.get(nested)
        if isinstance(sub, dict):
            for key in ('app_data', 'custom_data'):
                if isinstance(sub.get(key), str):
                    sub[key] = maybe_json(sub[key])
    return record


def credential_error(exception):
    return isinstance(exception, CredentialError)


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


def raise_errors(response):
    """
    raise ServerError or ClientError based on requests response as appropriate
    """
    if response.status_code >= 500:
        msg = "ServerError (%d): %s" % (response.status_code, response.text)
        raise ServerError(msg)

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
