#!/usr/bin/env python
"""
Cogniac API Python SDK

Copyright (C) 2016 Cogniac Corporation.

"""

import os
from hashlib import md5

import requests
from retrying import retry
from requests.auth import HTTPBasicAuth

from common import *

from app     import CogniacApplication
from subject import CogniacSubject
from tenant  import CogniacTenant
from media   import CogniacMedia


###
#  CogniacConnection
##
class CogniacConnection(object):
    """
    CogniacConnection

    Authenticate to the Cogniac System and maintain session state.

    CogniacConnection also provides helper functions for creating and retrieving the user's
    CogniacMedia, CogniacApplication, CogniacSubject, and CogniacTenant objects.

    If a user is a member of multiple tenants the user can retrieve his list of associated
    tenants via the CogniacConnection.get_all_authorized_tenants() classmethod.
    """

    @classmethod
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def get_all_authorized_tenants(cls, username=None, password=None):
        """
        return the list of valid tenants for the specified user credentials
        """
        if username is None and password is None:
            # credentials not specified, use environment variables if found
            try:
                username = os.environ['COG_USER']
                password = os.environ['COG_PASS']
            except:
                raise Exception("No Cogniac Credentials. Try setting COG_USER and COG_PASS environment.")

        resp = requests.get(url_prefix + "/users/current/tenants", auth=HTTPBasicAuth(username, password))
        raise_errors(resp)
        return resp.json()

    def __init__(self, username=None, password=None, tenant_id=None, timeout=20):
        """
        Create an authenticated CogniacConnection with the following credentials:

        username (String):            The Cogniac account username (usually an email address).
                                      If username is None, then use the contents of the
                                      COG_USER environment variable as the username.

        password (String):            The associated Cogniac account password.
                                      If password is None, then use the contents of the
                                      COG_PASS environment variable as the username.

        tenant_id (String):           Cogniac tenant_id with which to assume credentials.
                                      This is only required if the user is a member of multiple tenants.
                                      If tenant_id is None, and the user is a member of multiple tenants
                                      then use the contents of the COG_TENANT environment variable
                                      will be used as the tenant.

        If a user is a member of multiple tenants the user can retrieve his list of associated
        tenants via the CogniacConnection.get_all_authorized_tenants() classmethod.
        """
        if username is None and password is None:
            # credentials not specified, use environment variables if found
            try:
                username = os.environ['COG_USER']
                password = os.environ['COG_PASS']
            except:
                raise Exception("No Cogniac Credentials. Specify username and password or set COG_USER and COG_PASS environment variables.")

        if tenant_id is None:
            try:
                tenant_id = os.environ['COG_TENANT']
            except:
                tenants = CogniacConnection.get_all_authorized_tenants(username, password)['tenants']
                if len(tenants) > 1:
                    print "\nError: must specify tenant (e.g. export COG_TENANT=... ) from the following choices:"
                    for tenant in tenants:
                        print "%20s (%s)    export COG_TENANT='%s'" % (tenant['name'], tenant['tenant_id'], tenant['tenant_id'])
                    print
                    raise Exception("Unspecified tenant")
                tenant_id = tenants[0]['tenant_id']

        self.timeout = timeout
        self.session = requests.Session()

        @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
        def authenticate(username, password, tenant_id):
            #  Authenticate to the cogniac system using a username and password.
            #  Save the http Authorization headers that can be used for subsequent http requests to the cogniac API.
            tenant_data = {"tenant_id": tenant_id}
            resp = requests.get(url_prefix + "/oauth/token", params=tenant_data, auth=HTTPBasicAuth(username, password), timeout=self.timeout)
            raise_errors(resp)

            token = resp.json()
            headers = {"Authorization": "Bearer %s" % token['access_token']}
            self.session.headers.update(headers)

        authenticate(username, password, tenant_id)
        self.tenant = CogniacTenant.get(self)

    def get_tenant(self):
        """
        return the currently authenticated CogniacTenant
        """
        return self.tenant

    def get_all_applications(self):
        """
        return CogniacApplications for all applications belonging to the currently authenticated tenant
        """
        return CogniacApplication.get_all(self)

    def get_application(self, application_id):
        """
        return an existing CogniacApplication

        application_id (String):             The application_id of the Cogniac application to return
        """
        return CogniacApplication.get(self, application_id)

    def create_application(self,
                           name,
                           application_type,
                           description=None,
                           active=True,
                           input_subjects=None,
                           output_subjects=None):
        """
        Create a new CogniacApplication

        name (String):                       Name of new application
        application_type (String)            Cogniac Application Type name
        description (String):                Optional description of new application
        active (Boolean):                    Application operational state
        input_subjects ([CogniacSubjects]):  List of CogniacSubjects inputs to this application
        output_subjects ([CogniacSubjects]): List of CogniacSubjects outputs for this application
        """
        return CogniacApplication.create(self,
                                         name,
                                         application_type,
                                         description,
                                         active,
                                         input_subjects,
                                         output_subjects)

    def get_all_subjects(self, public_read=False, public_write=False):
        """
        return CogniacSubjects for all subjects belonging to the currently authenticated tenant
        """
        return CogniacSubject.get_all(self, public_read, public_write)

    def get_subject(self, subject_uid):
        """
        return an existing CogniacSubject

        subject_id (String):                 The subject_id of the Cogniac Subject to return
        """
        return CogniacSubject.get(self, subject_uid)

    def create_subject(self,
                       name,
                       description=None,
                       public_read=False,
                       public_write=False):
        """
        Create a CogniacSubject

        name (String):                       Name of new application
        description (String):                Optional description of the subject
        public_read(Bool):                   Subject media is accessible to other tenants and can be input into other tenant's apps.
        public_write(Bool):                  Other tenants can access and associate media with this subject.
        """
        return CogniacSubject.create(self,
                                     name,
                                     description,
                                     public_read,
                                     public_write)

    def get_media(self, media_id):
        """
        return a CogniacMedia object for an existing media item

        connnection (CogniacConnection):     Authenticated CogniacConnection object
        media_id (String):                   The media_id of the Cogniac Media item to return
        """
        return CogniacMedia.get(self, media_id)

    def create_media(self,
                     filename,
                     meta_tags=None,
                     force_set=None,
                     external_media_id=None,
                     original_url=None,
                     original_landing_url=None,
                     license=None,
                     author_profile_url=None,
                     author=None,
                     title=None):
        """
        Create a new CogniacMedia object and upload the media to the Cogniac System.

        filename (str):                   Local filename of image or video media file
        meta_tags ([str]):                Optional list of arbitrary strings to associate with the media
        force_set (str):                  Optionally force the media into the 'training', 'validation' or 'test' sets
        external_media_id (str):          Optional arbitrary external id for this media
        original_url(str):                Optional source url for this media
        original_landing_url (str):       Optional source landing url for this media
        license (str):                    Optional copyright licensing info for this media
        author_profile_url (str):         Optional media author url
        author (str):                     Optional author name
        title (str):                      Optional media title
        """
        return CogniacMedia.create(self,
                                   filename,
                                   meta_tags,
                                   force_set,
                                   external_media_id,
                                   original_url,
                                   original_landing_url,
                                   license,
                                   author_profile_url,
                                   author,
                                   title)

if __name__ == "__main__":
    c = CogniacConnection()
    tenant = c.tenant()
    from pprint import pprint
    print tenant
    print "\nApplications:"
    for app in tenant.applications():
        pprint(app.name)
    print "\Subjects:"
    for sub in tenant.subjects():
        print sub.name, sub.subject_uid
