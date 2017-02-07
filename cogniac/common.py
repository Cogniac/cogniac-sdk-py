"""
Cogniac API common definitions

Copyright (C) 2016 Cogniac Corporation
"""

from requests.exceptions import ConnectionError


url_prefix = "https://api.cogniac.io/1"


class CredentialError(Exception):
    """Invalid Username/Password Credentials"""


class ServerError(Exception):
    """Unknown API Error"""


class ClientError(Exception):
    """Error with the call parameters (e.g. 4xx)"""

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
        raise ClientError(msg)
