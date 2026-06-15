"""
CogniacTenant Object

Copyright (C) 2016 Cogniac Corporation

"""

from .common import *


TENANT_ADMIN_ROLE = "tenant_admin"
TENANT_USER_ROLE = "tenant_user"
TENANT_VIEWER_ROLE = "tenant_viewer"
TENANT_BILLING_ROLE = "tenant_billing"


##
#   CogniacTenant
##
class CogniacTenant(object):

    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def get(cls, connection):
        resp = connection._get("/1/tenants/current")
        return CogniacTenant(connection, resp.json())

    def __init__(self, connection, tenant_dict):
        super(CogniacTenant, self).__setattr__('_tenant_keys', tenant_dict.keys())
        self._cc = connection
        for k, v in tenant_dict.items():
            super(CogniacTenant, self).__setattr__(k, v)

    def __str__(self):
        return "%s (%s)" % (self.name, self.tenant_id)

    def __repr__(self):
        return self.__str__()

    def __setattr__(self, name, value):
        if name not in self._tenant_keys:
            super(CogniacTenant, self).__setattr__(name, value)
            return
        data = {name: value}
        resp = self._cc._post("/1/tenants/%s" % self.tenant_id, json=data)
        for k, v in resp.json().items():
            super(CogniacTenant, self).__setattr__(k, v)

    def users(self):
        resp = self._cc._get("/1/tenants/%s/users" % self.tenant_id)
        return resp.json()['data']

    def set_user_role(self, user_email, role):
        users = self.users()
        users = [u for u in self.users() if u['email'] == user_email]
        if not users:
            raise Exception("unknown user_email %s" % user_email)
        data = {'user_id': users[0]['user_id'], 'role': role}
        self._cc._post("/1/tenants/%s/users/role" % self.tenant_id, json=data)

    def add_user(self, user_email, role='tenant_user'):
        users = self.users()
        users = [u for u in self.users() if u['email'] == user_email]
        if not users:
            raise Exception("unknown user_email %s" % user_email)
        data = {'user_id': users[0]['user_id'], 'role': role}
        self._cc._post("/1/tenants/%s/users" % self.tenant_id, json=data)

    def delete_user(self, user_email):
        users = self.users()
        users = [u for u in self.users() if u['email'] == user_email]
        if not users:
            raise Exception("unknown user_email %s" % user_email)
        data = {'user_id': users[0]['user_id']}
        self._cc._delete("/1/tenants/%s/users" % self.tenant_id, json=data)

    def usage(self, start, end, period='15min'):

        assert(period in ['15min', 'hour', 'day'])

        url = "/1/usage/summary?period=%s&start=%d&end=%d" % (period, start, end)

        @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
        def get_next(url):
            resp = self._cc._get(url)
            return resp.json()

        while url:
            resp = get_next(url)
            for record in resp['data']:
                yield record
            url = resp['paging'].get('next')

    ##
    #  EdgeFlow TLS certificate
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def get_edgeflow_certificate(self):
        """
        Return the tenant-wide EdgeFlow TLS certificate.

        See GET /1/tenants/{tenant_id}/edgeflow_certificate.
        """
        resp = self._cc._get("/1/tenants/%s/edgeflow_certificate" % self.tenant_id)
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def set_edgeflow_certificate(self, body=None):
        """
        Upload/set the tenant-wide EdgeFlow TLS certificate.

        body (dict):  TLSCertKeyPair body

        See POST /1/tenants/{tenant_id}/edgeflow_certificate.
        """
        resp = self._cc._post("/1/tenants/%s/edgeflow_certificate" % self.tenant_id,
                             json=body if body is not None else {})
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def delete_edgeflow_certificate(self):
        """
        Delete the tenant-wide EdgeFlow TLS certificate.

        See DELETE /1/tenants/{tenant_id}/edgeflow_certificate.
        """
        resp = self._cc._delete("/1/tenants/%s/edgeflow_certificate" % self.tenant_id)
        try:
            return resp.json()
        except Exception:
            return None

    ##
    #  Meraki API key
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def delete_meraki_api_key(self):
        """
        Delete the tenant's stored Meraki API key.

        See DELETE /1/tenants/{tenant_id}/meraki_api_key.
        """
        self._cc._delete("/1/tenants/%s/meraki_api_key" % self.tenant_id)

    ##
    #  invitations
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def invites(self, invitation_status='pending'):
        """
        Return invitations for this tenant.

        invitation_status (str):  filter by status (default 'pending')

        See GET /1/tenants/{tenant_id}/invites.
        """
        resp = self._cc._get("/1/tenants/%s/invites" % self.tenant_id,
                            params={'invitation_status': invitation_status})
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def create_invite(self, body):
        """
        Create an invitation for this tenant.

        body (dict):  CreateInvitationRequest body

        See POST /1/tenants/{tenant_id}/invites.
        """
        resp = self._cc._post("/1/tenants/%s/invites" % self.tenant_id, json=body)
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def delete_invite(self, body):
        """
        Delete (revoke) an invitation for this tenant.

        body (dict):  DeleteTenantInviteRequest body

        See DELETE /1/tenants/{tenant_id}/invites.
        """
        self._cc._delete("/1/tenants/%s/invites" % self.tenant_id, json=body)

    ##
    #  CloudCore import key
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def get_cloudcore_import(cls, connection, tenant_id, cloudcore_import_key):
        """
        Return the CloudCore import payload for a tenant via an unguessable import key.

        connection (CogniacConnection):  Authenticated CogniacConnection object
        tenant_id (str):                 the tenant_id
        cloudcore_import_key (str):      the import key (acts as the credential)

        See GET /1/tenants/{tenant_id}/import/{cloudcore_import_key}.
        """
        resp = connection._get("/1/tenants/%s/import/%s" % (tenant_id, cloudcore_import_key))
        return resp.json()
