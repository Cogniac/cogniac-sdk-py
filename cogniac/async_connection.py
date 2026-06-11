"""
Cogniac API Python SDK - Async Connection

Async version of CogniacConnection using httpx.AsyncClient and async/await.

Copyright (C) 2016 Cogniac Corporation.
"""

import logging
import os
import re
import httpx
from .common import retry, stop_after_attempt, wait_exponential, retry_if_exception
from .common import server_error, raise_errors, CredentialError, credential_error
from .credentials import stored_api_key, stored_url_prefix

DEFAULT_COG_URL_PREFIX = "https://api.cogniac.io/"

logger = logging.getLogger(__name__)


class AsyncCogniacConnection(object):
    """
    AsyncCogniacConnection

    Async version of CogniacConnection.  Authenticate to the Cogniac System
    and maintain session state using httpx.AsyncClient.

    Use the async factory classmethod to create:

        cc = await AsyncCogniacConnection.create(...)

    Or as an async context manager:

        async with await AsyncCogniacConnection.create(...) as cc:
            ...
    """

    def __init__(self):
        # Private — callers must use the create() classmethod.
        self.session = None
        self.api_key = None
        self.username = None
        self.password = None
        self.url_prefix = None
        self.timeout = 60
        self.tenant_id = None

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    async def create(cls,
                     username=None,
                     password=None,
                     api_key=None,
                     tenant_id=None,
                     timeout=60,
                     url_prefix=None):
        """
        Create an authenticated AsyncCogniacConnection.

        Parameters mirror CogniacConnection.__init__.  Returns an
        AsyncCogniacConnection instance (also usable as an async context
        manager).

        username (String):            Cogniac account username (or COG_USER env var)
        password (String):            Cogniac account password (or COG_PASS env var)
        api_key (String):             Cogniac API key (or COG_API_KEY env var)
        tenant_id (String):           Tenant to authenticate against (or COG_TENANT env var)
        timeout (int):                Default request timeout in seconds
        url_prefix (String):          API url prefix (or COG_URL_PREFIX env var,
                                      default https://api.cogniac.io/)
        """
        self = cls()
        self.timeout = timeout

        # --- credentials ---
        if api_key is not None:
            self.api_key = api_key
        elif username is not None and password is not None:
            self.username = username
            self.password = password
        elif 'COG_API_KEY' in os.environ:
            self.api_key = os.environ['COG_API_KEY']
        elif 'COG_USER' in os.environ and 'COG_PASS' in os.environ:
            self.username = os.environ['COG_USER']
            self.password = os.environ['COG_PASS']
        elif stored_api_key() is not None:
            # fall back to a credential stored by `cogniac auth login`
            self.api_key = stored_api_key()
        else:
            raise Exception(
                "No Cogniac Credentials. Specify username and password, "
                "set COG_USER, COG_PASS or COG_API_KEY environment variables, "
                "or run `cogniac auth login`."
            )

        # --- url prefix ---
        if url_prefix is not None:
            self.url_prefix = url_prefix
        elif 'COG_URL_PREFIX' in os.environ:
            self.url_prefix = os.environ['COG_URL_PREFIX']
        elif stored_url_prefix() is not None:
            # adopt the url_prefix recorded by `cogniac auth login`
            self.url_prefix = stored_url_prefix()
        else:
            self.url_prefix = DEFAULT_COG_URL_PREFIX

        self.url_prefix = cls.__strip_url_version_num__(self.url_prefix)

        logger.info("Connecting to Cogniac system at %s", self.url_prefix)

        # --- tenant ---
        if tenant_id is None:
            tenant_id = os.environ.get('COG_TENANT')

        self.tenant_id = tenant_id

        # --- authenticate ---
        await self.__authenticate()

        return self

    # ------------------------------------------------------------------
    # Async context manager
    # ------------------------------------------------------------------

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        return False

    async def close(self):
        """Close the underlying httpx.AsyncClient."""
        if self.session is not None:
            await self.session.aclose()
            self.session = None

    # ------------------------------------------------------------------
    # URL helpers
    # ------------------------------------------------------------------

    @staticmethod
    def __strip_url_version_num__(url_prefix):
        """Return a Cogniac URL without the version number and slash
        from the beginning of the path component."""
        m = re.search(r'/\d+(/)?$', url_prefix)
        if m is not None:
            url_prefix = url_prefix[0:m.span()[0]]
        if url_prefix.endswith('/'):
            url_prefix = url_prefix[0:-1]
        return url_prefix

    def _build_url(self, url):
        """Resolve a possibly-relative URL against the url_prefix,
        prepending /1/ version when no version is present."""
        if not url.startswith("http"):
            m = re.search(r'^/\d+(/)?', url)
            if m is None:
                url = '/1' + url
            url = self.url_prefix + url
        return url

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def __authenticate(self):
        """Authenticate to the Cogniac system using API key or
        username/password and create an httpx.AsyncClient with bearer
        token headers."""
        tenant_data = {"tenant_id": self.tenant_id}

        if self.api_key:
            resp = await _async_get(
                self.url_prefix + "/1/token",
                params=tenant_data,
                headers={"Authorization": "Key %s" % self.api_key},
                timeout=self.timeout,
            )
        else:
            # Check MFA status
            resp = await _async_get(
                self.url_prefix + "/21/users/mfa/status",
                auth=(self.username, self.password),
                timeout=self.timeout,
            )
            raise_errors(resp)

            mfa_status = resp.json()
            if mfa_status.get('totp') == 'active':
                raise Exception(
                    "MFA/OTP is required for this account but is not supported "
                    "in AsyncCogniacConnection. Use an API key instead."
                )

            resp = await _async_get(
                self.url_prefix + "/1/token",
                params=tenant_data,
                auth=(self.username, self.password),
                timeout=self.timeout,
            )

        raise_errors(resp)

        token = resp.json()
        headers = {"Authorization": "Bearer %s" % token['access_token']}

        # Close any pre-existing session (e.g. on re-authentication).
        if self.session is not None:
            await self.session.aclose()

        transport = httpx.AsyncHTTPTransport(retries=5)
        self.session = httpx.AsyncClient(
            transport=transport,
            headers=headers,
            follow_redirects=True,
        )

    # ------------------------------------------------------------------
    # HTTP methods
    # ------------------------------------------------------------------

    @retry(stop=stop_after_attempt(3), retry=retry_if_exception(credential_error))
    async def _get(self, url, timeout=None, **kwargs):
        """Async GET with auto re-authentication on credential expiry."""
        url = self._build_url(url)
        if timeout is None:
            timeout = self.timeout
        kwargs.pop('stream', None)  # httpx handles streaming differently
        try:
            # httpx's .get() rejects a request body; route body-bearing GETs
            # (e.g. the model-package fetch) through .request(), which is
            # otherwise equivalent to .get() for bodyless calls.
            if any(k in kwargs for k in ('json', 'data', 'content')):
                resp = await self.session.request("GET", url, timeout=timeout, **kwargs)
            else:
                resp = await self.session.get(url, timeout=timeout, **kwargs)
            raise_errors(resp)
        except CredentialError:
            await self.__authenticate()
            raise
        return resp

    @retry(stop=stop_after_attempt(3), retry=retry_if_exception(credential_error))
    async def _post(self, url, timeout=None, **kwargs):
        """Async POST with auto re-authentication on credential expiry."""
        url = self._build_url(url)
        if timeout is None:
            timeout = self.timeout
        try:
            resp = await self.session.post(url, timeout=timeout, **kwargs)
            raise_errors(resp)
        except CredentialError:
            await self.__authenticate()
            raise
        return resp

    @retry(stop=stop_after_attempt(3), retry=retry_if_exception(credential_error))
    async def _head(self, url, timeout=None, **kwargs):
        """Async HEAD with auto re-authentication on credential expiry."""
        url = self._build_url(url)
        if timeout is None:
            timeout = self.timeout
        try:
            resp = await self.session.head(url, timeout=timeout, **kwargs)
            raise_errors(resp)
        except CredentialError:
            await self.__authenticate()
            raise
        return resp

    @retry(stop=stop_after_attempt(3), retry=retry_if_exception(credential_error))
    async def _delete(self, url, timeout=None, **kwargs):
        """Async DELETE with auto re-authentication on credential expiry.
        Uses session.request('DELETE', ...) to support json/content body."""
        url = self._build_url(url)
        if timeout is None:
            timeout = self.timeout
        try:
            resp = await self.session.request('DELETE', url, timeout=timeout, **kwargs)
            raise_errors(resp)
        except CredentialError:
            await self.__authenticate()
            raise
        return resp

    @retry(stop=stop_after_attempt(3), retry=retry_if_exception(credential_error))
    async def _put(self, url, timeout=None, **kwargs):
        """Async PUT with auto re-authentication on credential expiry."""
        url = self._build_url(url)
        if timeout is None:
            timeout = self.timeout
        try:
            resp = await self.session.request('PUT', url, timeout=timeout, **kwargs)
            raise_errors(resp)
        except CredentialError:
            await self.__authenticate()
            raise
        return resp

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    def _stream(self, method, url, timeout=None):
        """Return an httpx async stream context manager for large downloads.

        Usage:
            async with connection._stream('GET', url) as resp:
                async for chunk in resp.aiter_bytes():
                    ...
        """
        url = self._build_url(url)
        if timeout is None:
            timeout = self.timeout
        return self.session.stream(method, url, timeout=timeout)

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    async def get_version(self, auth=False):
        """Get API version info.

        auth (bool): use authenticated endpoint for benchmark purposes
        """
        if auth:
            url = self.url_prefix + "/1/authversion"
        else:
            url = self.url_prefix + "/1/version"
        resp = await self._get(url)
        return resp.json()


# ------------------------------------------------------------------
# Module-level async helper (used during authentication before the
# session exists)
# ------------------------------------------------------------------

async def _async_get(url, **kwargs):
    """One-shot async GET using a temporary AsyncClient."""
    async with httpx.AsyncClient() as client:
        return await client.get(url, follow_redirects=True, **kwargs)
