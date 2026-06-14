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


def credential_error(exception):
    return isinstance(exception, CredentialError)


def server_error(exception):
    """Return True if we should retry (in this case when it's an ServerError, False otherwise"""
    return isinstance(exception, ServerError) or isinstance(exception, ConnectError)


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
        raise ServerError(msg)

    if response.status_code == 401:
        msg = "Invalid username password credentials (%d): %s" % (response.status_code, response.text)
        raise CredentialError(msg)

    if response.status_code == 429:
        # Raise as ServerError so the tenacity retry path picks it up.
        # Callers using the shared retry decorator get automatic backoff;
        # the Retry-After header is not currently honored (improvement tracked
        # in cogniac-sdk-py#158).
        msg = "RateLimited (429): %s" % response.text
        raise ServerError(msg)

    if response.status_code >= 400:
        msg = "ClientError (%d): %s" % (response.status_code, response.text)
        raise ClientError(msg, response.status_code)
