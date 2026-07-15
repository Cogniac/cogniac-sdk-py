"""
CogniacWorkflow Object Client

Copyright (C) 2024 Cogniac Corporation
"""

from .common import retry, stop_after_attempt, wait_exponential, retry_if_exception, server_error


##
#  CogniacWorkflow
##
class CogniacWorkflow(object):
    """
    CogniacWorkflow

    A workflow is an immutable, frozen snapshot of an application pipeline that
    can be deployed to EdgeFlow / CloudFlow.

    Get an existing workflow with
    CogniacConnection.get_workflow() or CogniacWorkflow.get()

    Get all of the tenant's workflows with
    CogniacConnection.get_all_workflows() or CogniacWorkflow.get_all()
    """

    ##
    #  get_all
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def get_all(cls, connection):
        """
        Return all CogniacWorkflow objects belonging to the authenticated tenant.

        See GET /1/tenants/{tenant_id}/workflows.
        """
        resp = connection._get("/1/tenants/%s/workflows" % connection.tenant.tenant_id)
        data = resp.json()
        items = data.get('data', data) if isinstance(data, dict) else data
        return [CogniacWorkflow(connection, w) for w in items]

    ##
    #  get
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def get(cls, connection, workflow_id):
        """
        Return a single CogniacWorkflow by workflow_id.

        See GET /1/workflows/{workflow_id}.
        """
        resp = connection._get("/1/workflows/%s" % workflow_id)
        return CogniacWorkflow(connection, resp.json())

    ##
    #  create
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def create(cls, connection, body=None):
        """
        Create a new workflow.

        body (dict):  CreateWorkflowRequest body

        See POST /1/workflows.
        """
        resp = connection._post("/1/workflows", json=body if body is not None else {})
        return CogniacWorkflow(connection, resp.json())

    ##
    #  edgeflow_targets
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def edgeflow_targets(cls, connection, edgeflow_model=None):
        """
        Return the supported EdgeFlow model targets, or details for a single model.

        edgeflow_model (str):  optional EdgeFlow model name; when supplied, the
                               detailed target info for that model is returned.

        See GET /1/workflows/eftargets and GET /1/workflows/eftargets/{edgeflow_model}.
        """
        if edgeflow_model is not None:
            resp = connection._get("/1/workflows/eftargets/%s" % edgeflow_model)
        else:
            resp = connection._get("/1/workflows/eftargets")
        return resp.json()

    ##
    #  new_version
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def new_version(cls, connection, base_id, body):
        """
        Create a new version of a workflow.

        base_id (str):  the base workflow id
        body (dict):    CreateWorkflowVersionRequest body

        See POST /1/workflows/{base_id}/versions.
        """
        resp = connection._post("/1/workflows/%s/versions" % base_id, json=body)
        return CogniacWorkflow(connection, resp.json())

    ##
    #  get_all_versions
    ##
    @classmethod
    def get_all_versions(cls, connection, base_id, reverse=True, limit=None, last_key=None):
        """
        Yield every version of a workflow base as CogniacWorkflow objects,
        following the DynamoDB last_key cursor until the versions are drained.

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
        def get_next(last_key):
            params = {'reverse': reverse}
            if limit is not None:
                params['limit'] = limit
            if last_key is not None:
                params['last_key'] = last_key
            resp = connection._get("/1/workflows/%s/versions" % base_id, params=params)
            return resp.json()

        count = 0
        while True:
            resp = get_next(last_key)
            data = resp['data'] if isinstance(resp, dict) and 'data' in resp else resp
            for record in data or []:
                yield CogniacWorkflow(connection, record)
                count += 1
                if limit and count == limit:
                    return
            last_key = resp.get('last_key') if isinstance(resp, dict) else None
            if not last_key:
                return

    ##
    #  get_version
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def get_version(cls, connection, base_id, version):
        """
        Return a specific workflow version.

        See GET /1/workflows/{base_id}/versions/{version}.
        """
        resp = connection._get("/1/workflows/%s/versions/%s" % (base_id, version))
        return CogniacWorkflow(connection, resp.json())

    def __init__(self, connection, workflow_dict):
        self._cc = connection
        self._workflow_keys = workflow_dict.keys()
        for k, v in workflow_dict.items():
            super(CogniacWorkflow, self).__setattr__(k, v)

    def __str__(self):
        return "%s (%s)" % (getattr(self, 'name', '?'), getattr(self, 'workflow_id', '?'))

    def __repr__(self):
        return self.__str__()

    ##
    #  delete
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def delete(self):
        """
        Delete this workflow.

        See DELETE /1/workflows/{workflow_id}.
        """
        self._cc._delete("/1/workflows/%s" % self.workflow_id)
