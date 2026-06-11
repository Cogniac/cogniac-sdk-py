"""
Async CogniacWorkflow Object Client

Copyright (C) 2024 Cogniac Corporation
"""

from .common import retry, stop_after_attempt, wait_exponential, retry_if_exception, server_error


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

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def delete(self):
        """
        Delete this workflow.

        See DELETE /1/workflows/{workflow_id}.
        """
        await self._cc._delete("/1/workflows/%s" % self.workflow_id)
