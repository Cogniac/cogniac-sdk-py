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
