"""
CogniacTenant Object

Copyright (C) 2016 Cogniac Corporation

"""

import json
import six
from retrying import retry
from .common import *


TENANT_ADMIN_ROLE = "tenant_admin"
TENANT_USER_ROLE = "tenant_user"
TENANT_VIEWER_ROLE = "tenant_viewer"
TENANT_BILLING_ROLE = "tenant_billing"


##
#   CogniacTenant
##
@six.python_2_unicode_compatible
class CogniacTenant(object):

    @classmethod
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def get(cls, connection):
        resp = connection._get("/1/tenants/current")
        return CogniacTenant(connection, json.loads(resp.content))

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

        @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
        def get_next(url):
            resp = self._cc._get(url)
            return resp.json()

        while url:
            resp = get_next(url)
            for record in resp['data']:
                yield record
            url = resp['paging'].get('next')
