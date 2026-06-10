"""
Cogniac API Python SDK

Copyright (C) 2016 Cogniac Corporation.

This client library provides both synchronous and asynchronous access
to the Cogniac public API.  Requires Python 3.11+.

Sync API:

    import cogniac
    cc = cogniac.CogniacConnection()
    subjects = cc.get_all_subjects()

Async API:

    import cogniac
    async with await cogniac.AsyncCogniacConnection.create() as cc:
        subjects = await cogniac.AsyncCogniacSubject.get_all(cc)
        await subjects[0].set(description="updated")

Credentials via environment variables:
    COG_USER, COG_PASS (or COG_API_KEY), COG_TENANT, COG_URL_PREFIX
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
from .deployment import CogniacDeployment, CogniacDeploymentCapacityClass
from .workflow import CogniacWorkflow
from .build import CogniacBuild

# Async API
from .async_connection import AsyncCogniacConnection
from .async_app import AsyncCogniacApplication
from .async_subject import AsyncCogniacSubject
from .async_media import AsyncCogniacMedia
from .async_tenant import AsyncCogniacTenant
from .async_user import AsyncCogniacUser
from .async_edgeflow import AsyncCogniacEdgeFlow
from .async_external_results import AsyncCogniacExternalResult
from .async_ops_review import AsyncCogniacOpsReview
from .async_network_camera import AsyncCogniacNetworkCamera
from .async_deployment import AsyncCogniacDeployment, AsyncCogniacDeploymentCapacityClass
from .async_workflow import AsyncCogniacWorkflow
from .async_build import AsyncCogniacBuild
