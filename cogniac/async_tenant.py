"""
Async CogniacTenant Object

Copyright (C) 2016 Cogniac Corporation
"""

from .common import retry, stop_after_attempt, wait_exponential, retry_if_exception, server_error


TENANT_ADMIN_ROLE = "tenant_admin"
TENANT_USER_ROLE = "tenant_user"
TENANT_VIEWER_ROLE = "tenant_viewer"
TENANT_BILLING_ROLE = "tenant_billing"


class AsyncCogniacTenant(object):
    """
    AsyncCogniacTenant
    Async version of CogniacTenant.

    Use the async set() method to update mutable attributes.
    """

    ##
    #  get
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def get(cls, connection):
        """
        Get the current tenant.

        connection (AsyncCogniacConnection): Authenticated AsyncCogniacConnection object
        """
        resp = await connection._get("/1/tenants/current")
        return AsyncCogniacTenant(connection, resp.json())

    ##
    #  __init__
    ##
    def __init__(self, connection, tenant_dict):
        super(AsyncCogniacTenant, self).__setattr__('_tenant_keys', tenant_dict.keys())
        self._cc = connection
        for k, v in tenant_dict.items():
            super(AsyncCogniacTenant, self).__setattr__(k, v)

    def __str__(self):
        return "%s (%s)" % (self.name, self.tenant_id)

    def __repr__(self):
        return self.__str__()

    def __setattr__(self, name, value):
        if name not in self._tenant_keys:
            super(AsyncCogniacTenant, self).__setattr__(name, value)
            return
        # Block sync writes to tenant-key attributes; use async set() instead
        super(AsyncCogniacTenant, self).__setattr__(name, value)

    ##
    #  set
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def set(self, **kwargs):
        """
        Update tenant attributes via a single POST call.

        Example:
            await tenant.set(name="new tenant name")
        """
        resp = await self._cc._post("/1/tenants/%s" % self.tenant_id, json=kwargs)
        for k, v in resp.json().items():
            super(AsyncCogniacTenant, self).__setattr__(k, v)

    ##
    #  users
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def users(self):
        """
        Return list of users for this tenant.
        """
        resp = await self._cc._get("/1/tenants/%s/users" % self.tenant_id)
        return resp.json()['data']

    ##
    #  set_user_role
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def set_user_role(self, user_email, role):
        """
        Set the role of a user in this tenant.

        user_email (str): email of the user
        role (str):       role to assign
        """
        all_users = await self.users()
        users = [u for u in all_users if u['email'] == user_email]
        if not users:
            raise Exception("unknown user_email %s" % user_email)
        data = {'user_id': users[0]['user_id'], 'role': role}
        await self._cc._post("/1/tenants/%s/users/role" % self.tenant_id, json=data)

    ##
    #  add_user
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def add_user(self, user_email, role='tenant_user'):
        """
        Add a user to this tenant.

        user_email (str): email of the user
        role (str):       role to assign (default: 'tenant_user')
        """
        all_users = await self.users()
        users = [u for u in all_users if u['email'] == user_email]
        if not users:
            raise Exception("unknown user_email %s" % user_email)
        data = {'user_id': users[0]['user_id'], 'role': role}
        await self._cc._post("/1/tenants/%s/users" % self.tenant_id, json=data)

    ##
    #  delete_user
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def delete_user(self, user_email):
        """
        Remove a user from this tenant.

        user_email (str): email of the user to remove
        """
        all_users = await self.users()
        users = [u for u in all_users if u['email'] == user_email]
        if not users:
            raise Exception("unknown user_email %s" % user_email)
        data = {'user_id': users[0]['user_id']}
        await self._cc._delete("/1/tenants/%s/users" % self.tenant_id, json=data)

    ##
    #  usage
    ##
    async def usage(self, start, end, period='15min'):
        """
        Async generator yielding sparse tenant usage records between start and end epoch times.

        start (float):    start epoch time
        end (float):      end epoch time
        period (str):     aggregation period: '15min', 'hour', or 'day'
        """
        assert(period in ['15min', 'hour', 'day'])

        url = "/1/usage/summary?period=%s&start=%d&end=%d" % (period, start, end)

        @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
        async def get_next(url):
            resp = await self._cc._get(url)
            return resp.json()

        while url:
            resp = await get_next(url)
            for record in resp['data']:
                yield record
            url = resp['paging'].get('next')
