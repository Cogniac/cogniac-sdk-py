#!/usr/bin/env python
"""
Cogniac API Python SDK

Copyright (C) 2016 Cogniac Corporation.

"""

import logging
import os
import re
import httpx
import sys
from .common import retry, stop_after_attempt, wait_exponential, retry_if_exception
from .common import server_error, raise_errors, CredentialError, credential_error
from .credentials import stored_api_key, stored_url_prefix

from .app     import CogniacApplication
from .subject import CogniacSubject
from .tenant  import CogniacTenant
from .user    import CogniacUser
from .media   import CogniacMedia
from .edgeflow import CogniacEdgeFlow

from .network_camera import CogniacNetworkCamera

DEFAULT_COG_URL_PREFIX = "https://api.cogniac.io/"

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
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def get_all_authorized_tenants(cls, username=None, password=None, url_prefix="https://api.cogniac.io/"):
        """
        return the list of valid tenants for the specified user credentials and url_prefix
        """
        api_key = os.environ.get('COG_API_KEY')
        has_env_userpass = 'COG_USER' in os.environ and 'COG_PASS' in os.environ
        if api_key is None and username is None and password is None and not has_env_userpass:
            # fall back to a stored `cogniac auth login` credential
            # (only after explicit args and COG_USER/COG_PASS env, per documented precedence)
            api_key = stored_api_key()
        if api_key is not None:
            resp = httpx.get(url_prefix + "/1/users/current/tenants",
                             headers={"Authorization": "Key %s" % api_key})
            raise_errors(resp)
            return resp.json()

        if username is None and password is None:
            # credentials not specified, use environment variables if found
            try:
                username = os.environ['COG_USER']
                password = os.environ['COG_PASS']
            except KeyError:
                raise Exception("No Cogniac Credentials. Try setting COG_USER and COG_PASS environment, or run `cogniac auth login`.")

        resp = httpx.get(url_prefix + "/1/users/current/tenants", auth=(username, password))
        raise_errors(resp)
        return resp.json()

    def __init__(self,
                 username=None,
                 password=None,
                 api_key=None,
                 tenant_id=None,
                 timeout=60,
                 url_prefix=None):
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
        elif 'COG_USER' in os.environ and 'COG_PASS' in os.environ:
            self.username = os.environ['COG_USER']
            self.password = os.environ['COG_PASS']
        elif stored_api_key() is not None:
            # fall back to a credential stored by `cogniac auth login`
            self.api_key = stored_api_key()
        else:
            raise Exception("No Cogniac Credentials. Specify username and password, set COG_USER, COG_PASS or COG_API_KEY environment variables, or run `cogniac auth login`.")

        self.url_prefix = None
        if url_prefix is not None:
            self.url_prefix = url_prefix
        elif 'COG_URL_PREFIX' in os.environ:
            self.url_prefix = os.environ['COG_URL_PREFIX']
        elif stored_url_prefix() is not None:
            # adopt the url_prefix recorded by `cogniac auth login`
            self.url_prefix = stored_url_prefix()
        else:
            self.url_prefix = DEFAULT_COG_URL_PREFIX

        self.url_prefix = self.__strip_url_version_num__(self.url_prefix)
        self.timeout = timeout

        logger.info("Connecting to Cogniac system at %s" % url_prefix)

        if tenant_id is None:
            try:
                tenant_id = os.environ['COG_TENANT']
            except KeyError:
                if not self.api_key:
                    # For username/password: try to auto-select if only one tenant
                    tenants = CogniacConnection.get_all_authorized_tenants(username, password, url_prefix)['tenants']
                    if len(tenants) == 1:
                        tenant_id = tenants[0]['tenant_id']
                    # else: proceed without tenant; HTTP responses will signal if one is required

        self.tenant_id = tenant_id

        # get and store auth headers
        self.__authenticate()

        # get tenant and user objects associated with this connection
        if self.tenant_id is not None:
            self._tenant = CogniacTenant.get(self)
            if self._tenant.region is not None and url_prefix is None and 'COG_URL_PREFIX' not in os.environ:
                # use tenant object's specified region preference unless explicitly overridden
                self.url_prefix = 'https://' + self._tenant.region
        else:
            self._tenant = None
        self.user = CogniacUser.get(self)

    @property
    def tenant(self):
        if self._tenant is None:
            self._require_tenant()
        return self._tenant

    @tenant.setter
    def tenant(self, value):
        self._tenant = value

    def _require_tenant(self):
        """Raise a helpful error listing available tenants when none is configured."""
        try:
            resp = self.session.get(self.url_prefix + "/1/users/current/tenants", follow_redirects=True)
            tenants = resp.json().get('tenants', [])
        except Exception:
            raise Exception("Unspecified tenant")
        print("\nError: must specify tenant (e.g. export COG_TENANT=... ) from the following choices:")
        tenants.sort(key=lambda x: x['name'])
        for tenant in tenants:
            print("%24s (%s)    export COG_TENANT='%s'" % (tenant['name'], tenant['tenant_id'], tenant['tenant_id']))
        print()
        raise Exception("Unspecified tenant")

    @staticmethod
    def __strip_url_version_num__(url_prefix):
        """Return a cogniac URL without the version number and slash from the begining of the path componet.
        """
        m = re.search(r'/\d+(/)?$', url_prefix)
        # Strip API version number and tailing '/' from URL prefix.
        if m is not None:
            url_prefix = url_prefix[0:m.span()[0]]
        if url_prefix.endswith('/'):
            url_prefix = url_prefix[0:-1]
        return url_prefix

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def __authenticate(self):
        #  Authenticate to the cogniac system using a username and password or an API KEY
        #  Save the http Authorization headers that can be used for subsequent http requests to the cogniac API.
        tenant_data = {"tenant_id": self.tenant_id}
        if self.api_key:
            # trade API KEY for user+tenant token
            resp = httpx.get(self.url_prefix + "/1/token",
                             params=tenant_data,
                             headers={"Authorization": "Key %s" % self.api_key},
                             timeout=self.timeout)
        else:
            # trade username/password for user+tenant token

            # https://staging.cogniac.io/21/users/mfa/status
            resp = httpx.get(self.url_prefix + "/21/users/mfa/status",
                             auth=(self.username, self.password),
                             timeout=self.timeout)
            raise_errors(resp)

            mfa_status = resp.json()
            if mfa_status.get('totp') == 'active':
                try:
                    totp = input('Multi-Factor Authentication is required. Enter OTP: ')
                except KeyboardInterrupt:
                    sys.exit()
                tenant_data['otp'] = totp

            resp = httpx.get(self.url_prefix + "/1/token",
                             params=tenant_data,
                             auth=(self.username, self.password),
                             timeout=self.timeout)

        raise_errors(resp)

        token = resp.json()
        headers = {"Authorization": "Bearer %s" % token['access_token']}
        transport = httpx.HTTPTransport(retries=5)
        self.session = httpx.Client(transport=transport, headers=headers, follow_redirects=True)

    @retry(stop=stop_after_attempt(3), retry=retry_if_exception(credential_error))
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

    @retry(stop=stop_after_attempt(3), retry=retry_if_exception(credential_error))
    def _get(self, url, timeout=None, **kwargs):
        """
        wrap httpx client to re-authenticate on credential expiration
        """
        if not url.startswith("http"):
            # Prepend /1/ version if no version is specified in the URL (backward compatibility).
            m = re.search(r'^/\d+(/)?', url)
            if m is None:
                url = '/1' + url

            url = self.url_prefix + url
        if timeout is None:
            timeout = self.timeout
        kwargs.pop('stream', None)  # httpx handles streaming differently
        try:
            # httpx's .get() rejects a request body; route body-bearing GETs
            # (e.g. the model-package fetch) through .request(), which is
            # otherwise equivalent to .get() for bodyless calls.
            if any(k in kwargs for k in ('json', 'data', 'content')):
                resp = self.session.request("GET", url, timeout=timeout, **kwargs)
            else:
                resp = self.session.get(url, timeout=timeout, **kwargs)
            raise_errors(resp)
        except CredentialError:
            self.__authenticate()
            raise
        return resp

    @retry(stop=stop_after_attempt(3), retry=retry_if_exception(credential_error))
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

    @retry(stop=stop_after_attempt(3), retry=retry_if_exception(credential_error))
    def _delete(self, url, timeout=None, **kwargs):
        """
        wrap httpx client to re-authenticate on credential expiration
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
            # use request() instead of delete() to support json/content body
            resp = self.session.request('DELETE', url, timeout=timeout, **kwargs)
            raise_errors(resp)
        except CredentialError:
            self.__authenticate()
            raise
        return resp

    @retry(stop=stop_after_attempt(3), retry=retry_if_exception(credential_error))
    def _put(self, url, timeout=None, **kwargs):
        """
        wrap httpx client to re-authenticate on credential expiration
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
            resp = self.session.request('PUT', url, timeout=timeout, **kwargs)
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
                           app_managers=None,
                           app_type_config=None):
        """
        Create a new CogniacApplication

        name (String):                       Name of new application
        application_type (String)            Cogniac Application Type name
        description (String):                Optional description of new application
        active (Boolean):                    Application operational state
        input_subjects ([CogniacSubjects]):  List of CogniacSubjects inputs to this application
        output_subjects ([CogniacSubjects]): List of CogniacSubjects outputs for this application
        app_type_config ({String: Any}):     Dict containing parameters specific to the app's type
        """
        return CogniacApplication.create(self,
                                         name=name,
                                         application_type=application_type,
                                         description=description,
                                         active=active,
                                         input_subjects=input_subjects,
                                         output_subjects=output_subjects,
                                         app_managers=app_managers,
                                         app_type_config=app_type_config)

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

    def edgeflows(self):
        """
        return CogniacEdgeFlow for all EdgeFlows belonging to the currently authenticated tenant.

        This is the preferred name for get_all_edgeflows().
        """
        return CogniacEdgeFlow.get_all(self)

    def gateways(self):
        """
        DEPRECATED: use edgeflows() instead.

        return CogniacEdgeFlow for all EdgeFlows belonging to the currently authenticated tenant.
        """
        import warnings
        warnings.warn("CogniacConnection.gateways() is deprecated; use edgeflows() instead.",
                      DeprecationWarning, stacklevel=2)
        return self.edgeflows()

    def get_all_deployments(self):
        """
        return CogniacDeployment for all deployment groups belonging to the currently authenticated tenant
        """
        from .deployment import CogniacDeployment
        return CogniacDeployment.get_all(self)

    def get_deployment(self, deployment_group_id):
        """
        return an existing CogniacDeployment (deployment group)

        deployment_group_id (String):  The id of the deployment group to return
        """
        from .deployment import CogniacDeployment
        return CogniacDeployment.get(self, deployment_group_id)

    def get_all_workflows(self):
        """
        return CogniacWorkflow for all workflows belonging to the currently authenticated tenant
        """
        from .workflow import CogniacWorkflow
        return CogniacWorkflow.get_all(self)

    def get_workflow(self, workflow_id):
        """
        return an existing CogniacWorkflow

        workflow_id (String):  The id of the workflow to return
        """
        from .workflow import CogniacWorkflow
        return CogniacWorkflow.get(self, workflow_id)


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
