"""
Cogniac API common definitions

Copyright (C) 2016 Cogniac Corporation
"""

from requests.exceptions import ConnectionError


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
    return isinstance(exception, ServerError) or isinstance(exception, ConnectionError)


def raise_errors(response):
    """
    raise ServerError or ClientError based on requests response as appropriate
    """
    if response.status_code >= 500:
        msg = "ServerError (%d): %s" % (response.status_code, response.content)
        raise ServerError(msg)

    if response.status_code == 401:
        msg = "Invalid username password credentials (%d): %s" % (response.status_code, response.content)
        raise CredentialError(msg)

    if response.status_code >= 400:
        msg = "ClientError (%d): %s" % (response.status_code, response.content)
        raise ClientError(msg, response.status_code)
