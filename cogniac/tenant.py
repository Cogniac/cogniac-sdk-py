"""
CogniacTenant Object

Copyright (C) 2016 Cogniac Corporation

"""

import json
from retrying import retry
from common import *

immutable_fields = ['region', 'created_at', 'created_by', 'modified_at', 'modified_by', 'tenant_id']

mutable_keys = ['name', 'description', 'azure_sas_tokens']

TENANT_ADMIN_ROLE = "tenant_admin"
TENANT_USER_ROLE = "tenant_user"
TENANT_REVIEWER_ROLE = "tenant_viewer"
TENANT_BILLING_ROLE = "tenant_billing"


##
#   CogniacTenant
##
class CogniacTenant(object):

    @classmethod
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def get(cls, connection):
        resp = connection._get("/tenants/current")
        return CogniacTenant(connection, json.loads(resp.content))

    def __init__(self, connection, tenant_dict):
        self._cc = connection
        for k, v in tenant_dict.items():
            super(CogniacTenant, self).__setattr__(k, v)

    def __str__(self):
        return "%s (%s)" % (self.name, self.tenant_id)

    def __repr__(self):
        return "%s (%s)" % (self.name, self.tenant_id)

    def __setattr__(self, name, value):
        if name in immutable_fields:
            raise AttributeError("%s is immutable" % name)
        if name in mutable_keys:
            data = {name: value}
            resp = self._cc._post("/tenants/%s" % self.tenant_id, json=data)
            for k, v in resp.json().items():
                super(CogniacTenant, self).__setattr__(k, v)
            return
        super(CogniacTenant, self).__setattr__(name, value)

    def users(self):
        resp = self._cc._get("/tenants/%s/users" % self.tenant_id)
        return resp.json()['data']

    def set_user_role(self, user_email, role):
        users = self.users()
        users = [u for u in self.users() if u['email'] == user_email]
        if not users:
            raise Exception("unknown user_email %s" % user_email)
        data = {'user_id': users[0]['user_id'], 'role': role}
        self._cc._post("/tenants/%s/users/role" % self.tenant_id, json=data)

    def add_user(self, user_email, role='tenant_user'):
        users = self.users()
        users = [u for u in self.users() if u['email'] == user_email]
        if not users:
            raise Exception("unknown user_email %s" % user_email)
        data = {'user_id': users[0]['user_id'], 'role': role}
        self._cc._post("/tenants/%s/users" % self.tenant_id, json=data)

    def delete_user(self, user_email):
        users = self.users()
        users = [u for u in self.users() if u['email'] == user_email]
        if not users:
            raise Exception("unknown user_email %s" % user_email)
        data = {'user_id': users[0]['user_id']}
        self._cc._delete("/tenants/%s/users" % self.tenant_id, json=data)
