"""
Cogniac API Python SDK

Copyright (C) 2016 Cogniac Corporation.

This client library provides access to most of the common functionality of the Cogniac public API.


CogniacConnection(username=None,
                  password=None,
                  api_key=None,
                  tenant_id=None,
                  timeout=60,
                  url_prefix="https://api.cogniac.io/1")

        Create an authenticated CogniacConnection with the following credentials:


        username (String):            The Cogniac account username (usually an email address).
                                      If username is None, then use the contents of the
                                      COG_USER environment variable as the username.

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
                                      Defaults to "https://api.cogniac.io/1" for the Cogniac cloud system.
                                      If you are accessing an 'on-prem' version of the Cogniac system,
                                      please set this accordingly (e.g. 'https://your_company_name.local.cogniac.io/1'
                                      or a custom DNS prefix assigned by your internal IT.)
                                      The url_prefix can alternatively be set via the COG_URL_PREFIX environment variable.

        If a user is a member of multiple tenants the user can retrieve his list of associated
        tenants via the CogniacConnection.get_all_authorized_tenants() classmethod.


CogniacConnection has a number of helper functions for working with Cogniac
common Cogniac objects such as applications, subjects, and media:

    get_all_applications
        return CogniacApplications for all applications belonging to the currently authenticated tenant

    get_application
        return an existing CogniacApplication

    create_application
        Create a new CogniacApplication

    get_all_subjects
        return CogniacSubjects for all subjects belonging to the currently authenticated tenant

    get_subject
        return an existing CogniacSubject

    create_subject
        Create a CogniacSubject

    get_media
        return CogniacMedia object for an existing media item

    create_media
        create a new cogniac media item

    get_tenant
        return the currently authenticated CogniacTenant


CogniacEdgeFlow(url_prefix, timeout=60)
    An object representing an EdgeFlow in the Cogniac System.

    An instance of this class optionally provides a client interface that 
    communicates directly with a local EdgeFlow's APIs. The local EdgeFlow APIs
    are useful for application such as uploading images to the EdgeFlow for 
    fast processing "on the edge" without first uploading the images to
    CloudCore.

    url_prefix (String):          Cogniac API url prefix.
                                    The url_prefix can alternatively be set via the COG_GW_URL_PREFIX environment variable.


CogniacApplication
    An object representing an Application in the Cogniac System.

    Applications are the main locus of activity within the Cogniac System.

    This class manages applications within the Cogniac System via the
    Cogniac public API application endpoints.

    Create a new application with
    CogniacConnection.create_application() or CogniacApplication.create()

    Get an existing application with
    CogniacConnection.get_application() or CogniacApplication.get()

    Get all tenant's applications with
    CogniacConnection.get_all_applications() or CogniacApplication.get_all()

    Writes to mutable CogniacApplication attributes are saved immediately via the Cogniac API.


 CogniacSubject
    An object representing a Subject in the Cogniac System.

    Subjects are a central organizational mechanism in the Cogniac system.
    A subject is any user-defined concept that is relevant to images or video.
    More generally a subject can represent any logical grouping of images of video.

    Most Cogniac applications work by taking input media from user-defined subjects
    and outputing those media to other user-defined subjects based on the content
    of the media.

    Create a new subject with
    CogniacConnection.create_subject() or CogniacSubject.create()

    Get an existing subject with
    CogniacConnection.get_subject() or CogniacSubject.get()

    Get all tenant's subject with
    CogniacConnection.get_all_subjects() or CogniacSubject.get_all()

    Writes to mutable CogniacSubjects attributes are saved immediately via the Cogniac API.

CogniacMedia
    CogniacMedia objects contain metadata for media files that has been input into the Cogniac System.
    New CogniacMedia can be created by specifying a local filename containing a still image or video.
    Existing CogniacMedia can be retrieved by media_id.

CogniacTenant
    An object representing a Tenant in the Cogniac System

"""

from .cogniac import CogniacConnection
from .edgeflow import CogniacEdgeFlow
from .app import CogniacApplication
from .tenant import CogniacTenant
from .subject import CogniacSubject
from .media import CogniacMedia
from .common import CredentialError, ServerError, ClientError
from .user import CogniacUser
from .external_results import CogniacExternalResult
from .ops_review import CogniacOpsReview
from .network_camera import CogniacNetworkCamera
