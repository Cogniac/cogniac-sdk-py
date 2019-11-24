"""
CogniacUser Object

Copyright (C) 2019 Cogniac Corporation

"""

import json
from retrying import retry
from common import server_error


##
#   CogniacEdgeflow
##
class CogniacEdgeFlow(object):

    @classmethod
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def get(cls, connection, gateway_id):
        resp = connection._get("/gateways/%s" % gateway_id)
        return CogniacEdgeFlow(connection, json.loads(resp.content))

    def trigger(self, connection, capture_app_id):
        resp = connection._post("/gateways/%s/event/capture_trigger/%s" % (self.gateway_id, capture_app_id))
        print "resp", resp

    def __init__(self, connection, gw_dict):
        self._cc = connection
        for k, v in gw_dict.items():
            super(CogniacEdgeFlow, self).__setattr__(k, v)

    def __str__(self):
        return "%s (%s)" % (self.name, self.gateway_id)

    def __repr__(self):
        return "%s (%s)" % (self.name, self.gateway_id)

    def __setattr__(self, name, value):
        mutable_keys = {'name'}
        if name in mutable_keys:
            data = {name: value}
            resp = self._cc._post("/gateways/%s" % self.gateway_id, json=data)
            for k, v in resp.json().items():
                super(CogniacEdgeFlow, self).__setattr__(k, v)
            return
        super(CogniacEdgeFlow, self).__setattr__(name, value)
