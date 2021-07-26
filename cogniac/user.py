"""
CogniacUser Object

Copyright (C) 2019 Cogniac Corporation

"""

import json
from retrying import retry
from .common import *


mutable_keys = ['given_name', 'surname', 'title']


##
#   CogniacUser
##
class CogniacUser(object):

    @classmethod
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def get(cls, connection):
        resp = connection._get("/1/users/current")
        return CogniacUser(connection, json.loads(resp.content))

    def __init__(self, connection, tenant_dict):
        self._cc = connection
        for k, v in tenant_dict.items():
            super(CogniacUser, self).__setattr__(k, v)

    def __str__(self):
        return "%s %s (%s)" % (self.given_name, self.surname, self.email)

    def __repr__(self):
        return "%s %s (%s)" % (self.given_name, self.surname, self.email)

    def __setattr__(self, name, value):
        if name in mutable_keys:
            data = {name: value}
            resp = self._cc._post("/1/users/%s" % self.user_id, json=data)
            for k, v in resp.json().items():
                super(CogniacUser, self).__setattr__(k, v)
            return
        super(CogniacUser, self).__setattr__(name, value)

    def api_keys(self):
        resp = self._cc._get("/1/users/%s/apiKeys" % self.user_id)
        return resp.json()['data']

    def api_key(self, key_id):
        resp = self._cc._get("/1/users/%s/apiKeys/%s" % (self.user_id, key_id))
        return resp.json()

    def create_api_key(self, description):
        resp = self._cc._post("/1/users/%s/apiKeys" % self.user_id, json={'description': description})
        return resp.json()

    def delete_api_key(self, key_id):
        self._cc._delete("/1/users/%s/apiKeys/%s" % (self.user_id, key_id))
