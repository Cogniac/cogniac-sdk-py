#!/usr/bin/env python
"""
Cogniac API Python SDK

Copyright (C) 2016 Cogniac Corporation.

"""

import os
import logging
import re
import requests
from retrying import retry
from requests.auth import HTTPBasicAuth
from requests.packages.urllib3 import Retry
from requests.adapters import HTTPAdapter

from .common import server_error, raise_errors, CredentialError, credential_error

from .app     import CogniacApplication
from .subject import CogniacSubject
from .tenant  import CogniacTenant
from .user    import CogniacUser
from .media   import CogniacMedia
from .edgeflow import CogniacEdgeFlow

from .network_camera import CogniacNetworkCamera

logger = logging.getLogger(__name__)


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
    def get_all_authorized_tenants(cls, username=None, password=None, url_prefix="https://api.cogniac.io/"):
        """
        return the list of valid tenants for the specified user credentials and url_prefix
        """
        if 'COG_API_KEY' in os.environ:
            resp = requests.get(url_prefix + "/1/users/current/tenants",
                                headers={"Authorization": "Key %s" % os.environ['COG_API_KEY']})
            raise_errors(resp)
            return resp.json()

        if username is None and password is None:
            # credentials not specified, use environment variables if found
            try:
                username = os.environ['COG_USER']
                password = os.environ['COG_PASS']
            except:
                raise Exception("No Cogniac Credentials. Try setting COG_USER and COG_PASS environment.")

        resp = requests.get(url_prefix + "/1/users/current/tenants", auth=HTTPBasicAuth(username, password))
        raise_errors(resp)
        return resp.json()

    def __init__(self,
                 username=None,
                 password=None,
                 api_key=None,
                 tenant_id=None,
                 timeout=60,
                 url_prefix="https://api.cogniac.io/"):
        """
        Create an authenticated CogniacConnection with the following credentials:

        username (String):            The Cogniac account username (usually an email address).
                                      The username can also be supplied via the COG_USER
                                      environment variable.

        password (String):            The associated Cogniac account password.
                                      The password can also be supplied via the COG_PASS
                                      environment variable.

        api_key (String):             A Cogniac-issued API key that can be used as a substitute for
                                      a username+password.  The api_key can also be supplied via the
                                      COG_API_KEY environment variable.

        tenant_id (String):           Cogniac tenant_id with which to assume credentials.
                                      This is only required if the user is a member of multiple tenants.
                                      If tenant_id is None, and the user is a member of multiple tenants
                                      then use the contents of the COG_TENANT environment variable
                                      will be used as the tenant.

        url_prefix (String):          Cogniac API url prefix.
                                      Defaults to "https://api.cogniac.io/" for the Cogniac cloud system.
                                      If you are accessing an 'on-prem' version of the Cogniac system,
                                      please set this accordingly (e.g. 'https://your_company_name.local.cogniac.io/'
                                      or a custom DNS prefix assigned by your internal IT.)
                                      The url_prefix can alternatively be set via the COG_URL_PREFIX environment variable.

        If a user is a member of multiple tenants the user can retrieve his list of associated
        tenants via the CogniacConnection.get_all_authorized_tenants() classmethod.
        """
        self.api_key = None
        if api_key is not None:
            self.api_key = api_key
        elif username is not None and password is not None:
            self.username = username
            self.password = password
        elif 'COG_API_KEY' in os.environ:
            self.api_key = os.environ['COG_API_KEY']
        else:
            # credentials not specified, use environment variables if found
            try:
                username = os.environ['COG_USER']
                password = os.environ['COG_PASS']
                self.username = username
                self.password = password
            except:
                raise Exception("No Cogniac Credentials. Specify username and password or set COG_USER, COG_PASS or COG_API_KEY environment variables.")

        if 'COG_URL_PREFIX' in os.environ:
            url_prefix = os.environ['COG_URL_PREFIX']
        m = re.search(r'/\d+(/)?$', url_prefix)
        # Strip API version number and tailing '/' from URL prefix.
        if m is not None:
            url_prefix = url_prefix[0:m.span()[0]]
        if url_prefix.endswith('/'):
            url_prefix = url_prefix[0:-1]

        self.url_prefix = url_prefix
        self.timeout = timeout

        logger.info("Connecting to Cogniac system at %s" % url_prefix)

        if tenant_id is None:
            try:
                tenant_id = os.environ['COG_TENANT']
            except:
                if self.api_key:
                    print("tenant_id must be explicitly specified when using api_key")
                    raise Exception("Unspecified tenant")

                # get list of user's tenants
                tenants = CogniacConnection.get_all_authorized_tenants(username, password, url_prefix)['tenants']
                if len(tenants) == 1:
                    # only one choice -- automatically use that
                    tenant_id = tenants[0]['tenant_id']
                else:
                    # try to be helpful and provider interactive user with a list of valid tenants
                    print("\nError: must specify tenant (e.g. export COG_TENANT=... ) from the following choices:")
                    tenants.sort(key=lambda x: x['name'])
                    for tenant in tenants:
                        print("%24s (%s)    export COG_TENANT='%s'" % (tenant['name'], tenant['tenant_id'], tenant['tenant_id']))
                    print
                    raise Exception("Unspecified tenant")

        self.tenant_id = tenant_id

        # get and store auth headers
        self.__authenticate()

        # get tenant and user objects associated with this connection
        self.tenant = CogniacTenant.get(self)
        self.user = CogniacUser.get(self)

        if self.tenant.region is not None:
            # use tenant object's specified region preference
            # print "Using API endpoint from Tenant:", self.tenant.region
            self.url_prefix = 'https://' + self.tenant.region

    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def __authenticate(self):
        #  Authenticate to the cogniac system using a username and password or an API KEY
        #  Save the http Authorization headers that can be used for subsequent http requests to the cogniac API.
        tenant_data = {"tenant_id": self.tenant_id}
        if self.api_key:
            # trade API KEY for user+tenant token
            resp = requests.get(self.url_prefix + "/1/token",
                                params=tenant_data,
                                headers={"Authorization": "Key %s" % self.api_key},
                                timeout=self.timeout)
        else:
            # trade username/password for user+tenant token
            resp = requests.get(self.url_prefix + "/1/token",
                                params=tenant_data,
                                auth=HTTPBasicAuth(self.username, self.password),
                                timeout=self.timeout)
        raise_errors(resp)

        token = resp.json()
        headers = {"Authorization": "Bearer %s" % token['access_token']}
        self.session = requests.Session()
        # configure session with appropriate retries
        self.session.mount('https://', HTTPAdapter(max_retries=Retry(connect=5,
                                                                     read=5,
                                                                     status=5,
                                                                     redirect=2,
                                                                     backoff_factor=.001,
                                                                     status_forcelist=(500, 502, 503, 504))))
        self.session.headers.update(headers)

    @retry(stop_max_attempt_number=3, retry_on_exception=credential_error)
    def _head(self, url, timeout=None, **kwargs):
        """
        wrap requests session to re-authenticate on credential expiration
        """
        if not url.startswith("http"):
            # Prepend /1/ version if no version is specified in the URL (backward compatibility).
            m = re.search(r'^/\d+(/)?', url)
            if m is None:
                url = '/1' + url

            url = self.url_prefix + url
        if timeout is None:
            timeout = self.timeout
        try:
            resp = self.session.head(url, timeout=timeout, **kwargs)
            raise_errors(resp)
        except CredentialError:
            self.__authenticate()
            raise
        return resp

    @retry(stop_max_attempt_number=3, retry_on_exception=credential_error)
    def _get(self, url, timeout=None, **kwargs):
        """
        wrap requests session to re-authenticate on credential expiration
        """
        if not url.startswith("http"):
            # Prepend /1/ version if no version is specified in the URL (backward compatibility).
            m = re.search(r'^/\d+(/)?', url)
            if m is None:
                url = '/1' + url

            url = self.url_prefix + url
        if timeout is None:
            timeout = self.timeout
        try:
            resp = self.session.get(url, timeout=timeout, **kwargs)
            raise_errors(resp)
        except CredentialError:
            self.__authenticate()
            raise
        return resp

    @retry(stop_max_attempt_number=3, retry_on_exception=credential_error)
    def _post(self, url, timeout=None, **kwargs):
        """
        wrap requests session to re-authenticate on credential expiration
        """
        if not url.startswith("http"):
            # Prepend /1/ version if no version is specified in the URL (backward compatibility).
            m = re.search(r'^/\d+(/)?', url)
            if m is None:
                url = '/1' + url

            url = self.url_prefix + url
        if timeout is None:
            timeout = self.timeout
        try:
            resp = self.session.post(url, timeout=timeout, **kwargs)
            raise_errors(resp)
        except CredentialError:
            self.__authenticate()
            raise
        return resp

    @retry(stop_max_attempt_number=3, retry_on_exception=credential_error)
    def _delete(self, url, timeout=None, **kwargs):
        """
        wrap requests session to re-authenticate on credential expiration
        """
        if not url.startswith("http"):
            # Prepend /1/ version if no version is specified in the URL (backward compatibility).
            m = re.search(r'^/\d+(/)?', url)
            if m is None:
                url = '/1' + url

            url = self.url_prefix + url
        if timeout is None:
            timeout = self.timeout
        try:
            resp = self.session.delete(url, timeout=timeout, **kwargs)
            raise_errors(resp)
        except CredentialError:
            self.__authenticate()
            raise
        return resp

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
                           output_subjects=None,
                           app_managers=None):
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
                                         name=name,
                                         application_type=application_type,
                                         description=description,
                                         active=active,
                                         input_subjects=input_subjects,
                                         output_subjects=output_subjects,
                                         app_managers=app_managers)

    def get_all_subjects(self, public_read=False, public_write=False):
        """
        return CogniacSubjects for all subjects belonging to the currently authenticated tenant
        """
        return CogniacSubject.get_all(self, public_read=public_read, public_write=public_write)

    def search_subjects(self, ids=[], prefix=None, similar=None, name=None, tenant_owned=True, public_read=False, public_write=False, limit=10):
        """
        return CogniacSubjects based on given search filters
        """
        return CogniacSubject.search(self,
                                     ids=ids,
                                     prefix=prefix,
                                     similar=similar,
                                     name=name,
                                     tenant_owned=tenant_owned,
                                     public_read=public_read,
                                     public_write=public_write,
                                     limit=limit)

    def get_subject(self, subject_uid):
        """
        return an existing CogniacSubject

        subject_id (String):                 The subject_id of the Cogniac Subject to return
        """
        return CogniacSubject.get(self, subject_uid)

    def create_subject(self,
                       name,
                       description=None,
                       external_id=None,
                       public_read=False,
                       public_write=False):
        """
        Create a CogniacSubject

        name (String):                       Name of new subject
        description (String):                Optional description of the subject
        public_read(Bool):                   Subject media is accessible to other tenants and can be input into other tenant's apps.
        public_write(Bool):                  Other tenants can access and associate media with this subject.
        """
        return CogniacSubject.create(self,
                                     name=name,
                                     description=description,
                                     external_id=external_id,
                                     public_read=public_read,
                                     public_write=public_write)

    def get_media(self, media_id):
        """
        return a CogniacMedia object for an existing media item

        connnection (CogniacConnection):     Authenticated CogniacConnection object
        media_id (String):                   The media_id of the Cogniac Media item to return
        """
        return CogniacMedia.get(self, media_id)

    def search_media(self, md5=None, filename=None, external_media_id=None, domain_unit=None, limit=None):
        """
        return list of CogniacMedia within tenant based on specified md5, filename, or external_media_id
        """
        return CogniacMedia.search(self, md5, filename, external_media_id, domain_unit, limit)

    def create_media(self,
                     filename,
                     meta_tags=None,
                     force_set=None,
                     set_assignment=None,
                     external_media_id=None,
                     original_url=None,
                     original_landing_url=None,
                     license=None,
                     author_profile_url=None,
                     author=None,
                     title=None,
                     media_timestamp=None,
                     domain_unit=None,
                     trigger_id=None,
                     sequence_ix=None,
                     custom_data=None,
                     fp=None):
        """
        Create a new CogniacMedia object and upload the media to the Cogniac System.

        filename (str):                   Local filename or http/s URL of image or video media file
        meta_tags ([str]):                Optional list of arbitrary strings to associate with the media
        force_set (str):                  [DEPRECATED] Optionally force the media into the 'training', 'validation' or 'test' sets
        set_assignment (str):             Optionally associate media with the 'training', 'validation' or 'test' sets
        external_media_id (str):          Optional arbitrary external id for this media
        original_url(str):                Optional source url for this media
        original_landing_url (str):       Optional source landing url for this media
        license (str):                    Optional copyright licensing info for this media
        author_profile_url (str):         Optional media author url
        author (str):                     Optional author name
        title (str):                      Optional media title
        media_timestamp (float):          Optional actual timestamp of media creation/occurance time
        domain_unit (str):                Optional domain id (e.g. serial number) for set assignment grouping.
                                          Media with the same domain_unit will always be assigned to the same
                                          training or validation set. Set this to avoid overfitting when you have
                                          multiple images of the same thing or almost the same thing.
        trigger_id (str):                 Unique trigger identifier leading to a media sequence containing this media
        sequence_ix (str):                The index of this media within a triggered sequence
        custom_data (str):                Opaque user-specified data associated with this media; limited to 32KB
        fp (file):                        A '.read()'-supporting file-like object (under 16MB) from which to acquire
                                          the media instead of reading the media from the specified filename.
        """
        return CogniacMedia.create(self,
                                   filename=filename,
                                   meta_tags=meta_tags,
                                   force_set=force_set,
                                   set_assignment=set_assignment,
                                   external_media_id=external_media_id,
                                   original_url=original_url,
                                   original_landing_url=original_landing_url,
                                   license=license,
                                   author_profile_url=author_profile_url,
                                   author=author,
                                   title=title,
                                   media_timestamp=media_timestamp,
                                   domain_unit=domain_unit,
                                   trigger_id=trigger_id,
                                   sequence_ix=sequence_ix,
                                   custom_data=custom_data,
                                   fp=fp)

    def get_version(self, auth=False):
        """
        get api version info
        auth (bool):  use authenticated endpoint for benchmark purposes
        returns json version info
        """
        if auth:
            url = self.url_prefix + "/1/authversion"
        else:
            url = self.url_prefix + "/1/version"
        resp = self._get(url)
        raise_errors(resp)
        return resp.json()

    def get_all_cameras(self):
        """
        return CogniacNetworkCameras for all netcams belonging to the currently authenticated tenant
        """
        return CogniacNetworkCamera.get_all(self)

    def get_camera(self, network_camera_id):
        """
        return an existing CogniacNetworkCamera

        network_camera_id (String):  The id of the Cogniac network camera to return
        """
        return CogniacNetworkCamera.get(self, network_camera_id)

    def get_all_edgeflows(self):
        """
        return CogniacEdgeFlow for all EdgeFlows belonging to the currently authenticated tenant
        """
        return CogniacEdgeFlow.get_all(self)

    def get_edgeflow(self, edgeflow_id):
        """
        return an existing CogniacEdgeFlow 

        edgeflow_id (String):  The id of the Cogniac EdgeFlow to return
        """
        return CogniacEdgeFlow.get(self, edgeflow_id)


if __name__ == "__main__":
    c = CogniacConnection()
    tenant = c.tenant()
    from pprint import pprint
    print(tenant)
    print("\nApplications:")
    for app in tenant.applications():
        pprint(app.name)
    print("\Subjects:")
    for sub in tenant.subjects():
        print(sub.name, sub.subject_uid)
