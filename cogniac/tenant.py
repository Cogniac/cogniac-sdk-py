"""
CogniacTenant Object

Copyright (C) 2016 Cogniac Corporation

"""

import json
from retrying import retry
from common import *

immutable_fields = ['region', 'created_at', 'created_by', 'modified_at', 'modified_by', 'tenant_id']

mutable_keys = ['name', 'description', 'azure_sas_tokens']

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
