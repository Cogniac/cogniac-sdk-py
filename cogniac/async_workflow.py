"""
Async CogniacWorkflow Object Client

Copyright (C) 2024 Cogniac Corporation
"""

from .common import retry, stop_after_attempt, wait_exponential, retry_if_exception, server_error
from .workflow import workflow_diff, workflow_summary


class AsyncCogniacWorkflow(object):
    """
    AsyncCogniacWorkflow
    Async version of CogniacWorkflow.

    A workflow is an immutable, frozen snapshot of an application pipeline that
    can be deployed to EdgeFlow / CloudFlow.
    """

    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def get_all(cls, connection):
        """
        Return all AsyncCogniacWorkflow objects belonging to the authenticated tenant.

        See GET /1/tenants/{tenant_id}/workflows.
        """
        resp = await connection._get("/1/tenants/%s/workflows" % connection.tenant_id)
        data = resp.json()
        items = data.get('data', data) if isinstance(data, dict) else data
        return [AsyncCogniacWorkflow(connection, w) for w in items]

    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def get(cls, connection, workflow_id):
        """
        Return a single AsyncCogniacWorkflow by workflow_id.

        See GET /1/workflows/{workflow_id}.
        """
        resp = await connection._get("/1/workflows/%s" % workflow_id)
        return AsyncCogniacWorkflow(connection, resp.json())

    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def create(cls, connection, body=None):
        """
        Create a new workflow.

        See POST /1/workflows.
        """
        resp = await connection._post("/1/workflows", json=body if body is not None else {})
        return AsyncCogniacWorkflow(connection, resp.json())

    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def edgeflow_targets(cls, connection, edgeflow_model=None):
        """
        Return the supported EdgeFlow model targets, or details for a single model.

        See GET /1/workflows/eftargets and GET /1/workflows/eftargets/{edgeflow_model}.
        """
        if edgeflow_model is not None:
            resp = await connection._get("/1/workflows/eftargets/%s" % edgeflow_model)
        else:
            resp = await connection._get("/1/workflows/eftargets")
        return resp.json()

    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def new_version(cls, connection, base_id, body):
        """
        Create a new version of a workflow.

        See POST /1/workflows/{base_id}/versions.
        """
        resp = await connection._post("/1/workflows/%s/versions" % base_id, json=body)
        return AsyncCogniacWorkflow(connection, resp.json())

    @classmethod
    async def get_all_versions(cls, connection, base_id, reverse=True, limit=None, last_key=None):
        """
        Async generator yielding every version of a workflow base as
        AsyncCogniacWorkflow objects, following the DynamoDB last_key cursor
        until the versions are drained.

        The versions endpoint yields summary records (workflow_id, version,
        name, created_at, created_by, description, edgeflow_model, base_id,
        tenant_id) WITHOUT app_specs; fetch the full workflow via get()
        before diffing or summarizing.

        base_id (str)    the workflow base id; a full workflow_id of the form
                         <base_id>:<version> is also accepted (the version
                         suffix is ignored)
        reverse (bool)   newest first when True (default)
        limit (int)      yield a maximum of limit versions
        last_key (str)   resume from a previous last_key cursor

        See GET /1/workflows/{base_id}/versions.
        """
        base_id = base_id.split(':', 1)[0]  # tolerate a full <base_id>:<version>

        @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
        async def get_next(last_key):
            params = {'reverse': reverse}
            if limit is not None:
                params['limit'] = limit
            if last_key is not None:
                params['last_key'] = last_key
            resp = await connection._get("/1/workflows/%s/versions" % base_id, params=params)
            return resp.json()

        count = 0
        while True:
            resp = await get_next(last_key)
            data = resp['data'] if isinstance(resp, dict) and 'data' in resp else resp
            for record in data or []:
                yield AsyncCogniacWorkflow(connection, record)
                count += 1
                if limit and count == limit:
                    return
            last_key = resp.get('last_key') if isinstance(resp, dict) else None
            if not last_key:
                return

    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def get_version(cls, connection, base_id, version):
        """
        Return a specific workflow version.

        See GET /1/workflows/{base_id}/versions/{version}.
        """
        resp = await connection._get("/1/workflows/%s/versions/%s" % (base_id, version))
        return AsyncCogniacWorkflow(connection, resp.json())

    def __init__(self, connection, workflow_dict):
        self._cc = connection
        self._workflow_keys = workflow_dict.keys()
        for k, v in workflow_dict.items():
            super(AsyncCogniacWorkflow, self).__setattr__(k, v)

    def __str__(self):
        return "%s (%s)" % (getattr(self, 'name', '?'), getattr(self, 'workflow_id', '?'))

    def __repr__(self):
        return self.__str__()

    def summary(self):
        """
        Return a compact model-composition summary of this workflow:
        one row per app spec with application_id, model_runtime_image, and
        threshold fields. Pure local computation (no API call, not a coroutine).
        """
        return workflow_summary(self)

    def diff(self, other):
        """
        Return a compact diff between this workflow ('old' side) and another
        workflow ('new' side): top-level field changes, apps added/removed,
        and per-app-spec field changes keyed by application_id.

        other: an AsyncCogniacWorkflow instance or a plain workflow dict.

        Pure local computation (no API call, not a coroutine); see workflow_diff().
        """
        return workflow_diff(self, other)

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def delete(self):
        """
        Delete this workflow.

        See DELETE /1/workflows/{workflow_id}.
        """
        await self._cc._delete("/1/workflows/%s" % self.workflow_id)
