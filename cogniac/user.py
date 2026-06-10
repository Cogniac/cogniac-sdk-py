"""
CogniacUser Object

Copyright (C) 2019 Cogniac Corporation

"""

from .common import *


mutable_keys = ['given_name', 'surname', 'title']


##
#   CogniacUser
##
class CogniacUser(object):

    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def get(cls, connection):
        resp = connection._get("/1/users/current")
        return CogniacUser(connection, resp.json())

    ##
    #  query users
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def get_all(cls, connection, id=None, tenant_id=None):
        """
        Query users by id and/or tenant_id.

        connection (CogniacConnection):  Authenticated CogniacConnection object
        id (str):                        optional user id filter
        tenant_id (str):                 optional tenant id filter

        See GET /1/users.
        """
        params = {}
        if id is not None:
            params['id'] = id
        if tenant_id is not None:
            params['tenant_id'] = tenant_id
        resp = connection._get("/1/users", params=params)
        return resp.json()

    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def get_by_id(cls, connection, user_id):
        """
        Return a single user record by user_id.

        See GET /1/users/{id}.
        """
        resp = connection._get("/1/users/%s" % user_id)
        return CogniacUser(connection, resp.json())

    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def delete_by_id(cls, connection, user_id):
        """
        Delete a user by user_id.

        See DELETE /1/users/{id}.
        """
        connection._delete("/1/users/%s" % user_id)

    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def tenants(cls, connection, user_id='current'):
        """
        List the tenants a user belongs to.

        user_id (str):  'current' (default) or a specific user_id

        See GET /1/users/{user_id}/tenants.
        """
        resp = connection._get("/1/users/%s/tenants" % user_id)
        return resp.json()

    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def request_password_reset(cls, connection, email):
        """
        Request a password-reset email for the given email/user_id.

        See POST /1/users/requestPasswordReset.
        """
        resp = connection._post("/1/users/requestPasswordReset", json={'user_id': email})
        try:
            return resp.json()
        except Exception:
            return None

    ##
    #  invitations
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def invites(cls, connection, user_id='current'):
        """
        List pending invitations for a user.

        See GET /1/users/{user_id}/invites.
        """
        resp = connection._get("/1/users/%s/invites" % user_id)
        return resp.json()

    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def respond_invite(cls, connection, body, user_id='current'):
        """
        Accept or decline a pending invitation.

        body (dict):    AcceptDeclineInviteRequest body

        See POST /1/users/{user_id}/invites.
        """
        resp = connection._post("/1/users/%s/invites" % user_id, json=body)
        return resp.json()

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
