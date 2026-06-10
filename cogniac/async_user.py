"""
Async CogniacUser Object

Copyright (C) 2019 Cogniac Corporation
"""

from .common import retry, stop_after_attempt, wait_exponential, retry_if_exception, server_error


mutable_keys = ['given_name', 'surname', 'title']


class AsyncCogniacUser(object):
    """
    AsyncCogniacUser
    Async version of CogniacUser.

    Use the async set() method to update mutable attributes.
    """

    ##
    #  get
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def get(cls, connection):
        """
        Get the current user.

        connection (AsyncCogniacConnection): Authenticated AsyncCogniacConnection object
        """
        resp = await connection._get("/1/users/current")
        return AsyncCogniacUser(connection, resp.json())

    ##
    #  query users
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def get_all(cls, connection, id=None, tenant_id=None):
        """
        Query users by id and/or tenant_id.

        See GET /1/users.
        """
        params = {}
        if id is not None:
            params['id'] = id
        if tenant_id is not None:
            params['tenant_id'] = tenant_id
        resp = await connection._get("/1/users", params=params)
        return resp.json()

    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def get_by_id(cls, connection, user_id):
        """
        Return a single user record by user_id.

        See GET /1/users/{id}.
        """
        resp = await connection._get("/1/users/%s" % user_id)
        return AsyncCogniacUser(connection, resp.json())

    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def delete_by_id(cls, connection, user_id):
        """
        Delete a user by user_id.

        See DELETE /1/users/{id}.
        """
        await connection._delete("/1/users/%s" % user_id)

    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def tenants(cls, connection, user_id='current'):
        """
        List the tenants a user belongs to.

        See GET /1/users/{user_id}/tenants.
        """
        resp = await connection._get("/1/users/%s/tenants" % user_id)
        return resp.json()

    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def request_password_reset(cls, connection, email):
        """
        Request a password-reset email for the given email/user_id.

        See POST /1/users/requestPasswordReset.
        """
        resp = await connection._post("/1/users/requestPasswordReset", json={'user_id': email})
        try:
            return resp.json()
        except Exception:
            return None

    ##
    #  invitations
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def invites(cls, connection, user_id='current'):
        """
        List pending invitations for a user.

        See GET /1/users/{user_id}/invites.
        """
        resp = await connection._get("/1/users/%s/invites" % user_id)
        return resp.json()

    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def respond_invite(cls, connection, body, user_id='current'):
        """
        Accept or decline a pending invitation.

        See POST /1/users/{user_id}/invites.
        """
        resp = await connection._post("/1/users/%s/invites" % user_id, json=body)
        return resp.json()

    ##
    #  __init__
    ##
    def __init__(self, connection, user_dict):
        self._cc = connection
        for k, v in user_dict.items():
            super(AsyncCogniacUser, self).__setattr__(k, v)

    def __str__(self):
        return "%s %s (%s)" % (self.given_name, self.surname, self.email)

    def __repr__(self):
        return "%s %s (%s)" % (self.given_name, self.surname, self.email)

    def __setattr__(self, name, value):
        if name in mutable_keys:
            raise AttributeError("Use 'await user.set(%s=...)' to update server-managed attributes" % name)
        super(AsyncCogniacUser, self).__setattr__(name, value)

    ##
    #  set
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def set(self, **kwargs):
        """
        Update mutable user attributes via a single POST call.

        Accepted keys: given_name, surname, title

        Example:
            await user.set(given_name="Bill", surname="Smith")
        """
        for key in kwargs:
            if key not in mutable_keys:
                raise AttributeError("%s is not a recognized mutable attribute" % key)

        resp = await self._cc._post("/1/users/%s" % self.user_id, json=kwargs)
        for k, v in resp.json().items():
            super(AsyncCogniacUser, self).__setattr__(k, v)

    ##
    #  api_keys
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def api_keys(self):
        """
        Return list of API keys for this user.
        """
        resp = await self._cc._get("/1/users/%s/apiKeys" % self.user_id)
        return resp.json()['data']

    ##
    #  api_key
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def api_key(self, key_id):
        """
        Return a specific API key.

        key_id (str): the API key id
        """
        resp = await self._cc._get("/1/users/%s/apiKeys/%s" % (self.user_id, key_id))
        return resp.json()

    ##
    #  create_api_key
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def create_api_key(self, description):
        """
        Create a new API key.

        description (str): description of the API key
        """
        resp = await self._cc._post("/1/users/%s/apiKeys" % self.user_id, json={'description': description})
        return resp.json()

    ##
    #  delete_api_key
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def delete_api_key(self, key_id):
        """
        Delete an API key.

        key_id (str): the API key id to delete
        """
        await self._cc._delete("/1/users/%s/apiKeys/%s" % (self.user_id, key_id))
