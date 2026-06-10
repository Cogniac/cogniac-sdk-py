"""
Async CogniacTenant Object

Copyright (C) 2016 Cogniac Corporation
"""

from .common import retry, stop_after_attempt, wait_exponential, retry_if_exception, server_error

mutable_keys = ['name', 'description']
immutable_keys = ['tenant_id', 'created_at', 'created_by', 'modified_at', 'modified_by']

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
        if name.startswith('_') or name not in self._tenant_keys:
            super(AsyncCogniacTenant, self).__setattr__(name, value)
            return
        if name in mutable_keys:
            raise AttributeError("Use 'await tenant.set(%s=...)' to update server-managed attributes" % name)
        raise AttributeError("%s is immutable" % name)

    ##
    #  set
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def set(self, **kwargs):
        """
        Update mutable tenant attributes via a single POST call.

        Accepted keys: name, description

        Example:
            await tenant.set(name="new tenant name")
        """
        for key in kwargs:
            if key in immutable_keys:
                raise AttributeError("%s is immutable" % key)
            if key not in mutable_keys:
                raise AttributeError("%s is not a recognized mutable attribute" % key)

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
            url = resp.get('paging', {}).get('next')

    ##
    #  EdgeFlow TLS certificate
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def get_edgeflow_certificate(self):
        """
        Return the tenant-wide EdgeFlow TLS certificate.

        See GET /1/tenants/{tenant_id}/edgeflow_certificate.
        """
        resp = await self._cc._get("/1/tenants/%s/edgeflow_certificate" % self.tenant_id)
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def set_edgeflow_certificate(self, body=None):
        """
        Upload/set the tenant-wide EdgeFlow TLS certificate.

        See POST /1/tenants/{tenant_id}/edgeflow_certificate.
        """
        resp = await self._cc._post("/1/tenants/%s/edgeflow_certificate" % self.tenant_id,
                                   json=body if body is not None else {})
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def delete_edgeflow_certificate(self):
        """
        Delete the tenant-wide EdgeFlow TLS certificate.

        See DELETE /1/tenants/{tenant_id}/edgeflow_certificate.
        """
        resp = await self._cc._delete("/1/tenants/%s/edgeflow_certificate" % self.tenant_id)
        try:
            return resp.json()
        except Exception:
            return None

    ##
    #  Meraki API key
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def delete_meraki_api_key(self):
        """
        Delete the tenant's stored Meraki API key.

        See DELETE /1/tenants/{tenant_id}/meraki_api_key.
        """
        await self._cc._delete("/1/tenants/%s/meraki_api_key" % self.tenant_id)

    ##
    #  invitations
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def invites(self, invitation_status='pending'):
        """
        Return invitations for this tenant.

        See GET /1/tenants/{tenant_id}/invites.
        """
        resp = await self._cc._get("/1/tenants/%s/invites" % self.tenant_id,
                                  params={'invitation_status': invitation_status})
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def create_invite(self, body):
        """
        Create an invitation for this tenant.

        See POST /1/tenants/{tenant_id}/invites.
        """
        resp = await self._cc._post("/1/tenants/%s/invites" % self.tenant_id, json=body)
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def delete_invite(self, body):
        """
        Delete (revoke) an invitation for this tenant.

        See DELETE /1/tenants/{tenant_id}/invites.
        """
        await self._cc._delete("/1/tenants/%s/invites" % self.tenant_id, json=body)

    ##
    #  CloudCore import key
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def get_cloudcore_import(cls, connection, tenant_id, cloudcore_import_key):
        """
        Return the CloudCore import payload for a tenant via an unguessable import key.

        See GET /1/tenants/{tenant_id}/import/{cloudcore_import_key}.
        """
        resp = await connection._get("/1/tenants/%s/import/%s" % (tenant_id, cloudcore_import_key))
        return resp.json()
