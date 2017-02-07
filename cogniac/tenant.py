"""
CogniacTenant Object

Copyright (C) 2016 Cogniac Corporation

"""

import json
from retrying import retry
from common import *

immutable_fields = ['aws_region', 'created_at', 'created_by', 'modified_at', 'modified_by', 'tenant_type', 'tenant_id']

##
#   CogniacTenant
##
class CogniacTenant(object):

    @classmethod
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def get(cls, connection):
        resp = connection.session.get(url_prefix + "/organizations/current", timeout=connection.timeout)
        raise_errors(resp)
        return CogniacTenant(json.loads(resp.content))

    def __init__(self, tenant_dict):
        for k, v in tenant_dict.items():
            super(CogniacTenant, self).__setattr__(k, v)

    def __str__(self):
        return "%s (%s)" % (self.name, self.tenant_id)

    def __repr__(self):
        return "%s (%s)" % (self.name, self.tenant_id)

    def __setattr__(self, name, value):
        if name in immutable_fields:
            raise AttributeError("%s is immutable" % name)
        if name in ['name', 'description']:
            raise AttributeError("sdk does not support editing tenant objects")
