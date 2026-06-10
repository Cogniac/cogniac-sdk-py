"""
CogniacDeployment (deployment group) Object Client

Copyright (C) 2024 Cogniac Corporation
"""

from .common import retry, stop_after_attempt, wait_exponential, retry_if_exception, server_error


##
#  CogniacDeployment
##
class CogniacDeployment(object):
    """
    CogniacDeployment

    A deployment group is a collection of EdgeFlows that share a workflow /
    model deployment.

    Get an existing deployment group with
    CogniacConnection.get_deployment() or CogniacDeployment.get()

    Get all of the tenant's deployment groups with
    CogniacConnection.get_all_deployments() or CogniacDeployment.get_all()
    """

    ##
    #  get_all
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def get_all(cls, connection):
        """
        Return all CogniacDeployment objects belonging to the authenticated tenant.

        See GET /1/tenants/{tenant_id}/deploymentGroups.
        """
        resp = connection._get("/1/tenants/%s/deploymentGroups" % connection.tenant.tenant_id)
        groups = resp.json()['data']
        return [CogniacDeployment(connection, g) for g in groups]

    ##
    #  get
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def get(cls, connection, deployment_group_id):
        """
        Return a single CogniacDeployment by deployment_group_id.

        See GET /1/deploymentGroups/{deployment_group_id}.
        """
        resp = connection._get("/1/deploymentGroups/%s" % deployment_group_id)
        return CogniacDeployment(connection, resp.json())

    ##
    #  create
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def create(cls, connection, body=None):
        """
        Create a new deployment group.

        body (dict):  CreateDeploymentGroupRequest body

        See POST /1/deploymentGroups.
        """
        resp = connection._post("/1/deploymentGroups", json=body if body is not None else {})
        return CogniacDeployment(connection, resp.json())

    def __init__(self, connection, deployment_dict):
        self._cc = connection
        self._deployment_keys = deployment_dict.keys()
        for k, v in deployment_dict.items():
            super(CogniacDeployment, self).__setattr__(k, v)

    def __str__(self):
        return "%s (%s)" % (getattr(self, 'name', '?'), self.deployment_group_id)

    def __repr__(self):
        return self.__str__()

    ##
    #  delete
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def delete(self):
        """
        Delete this deployment group.

        See DELETE /1/deploymentGroups/{deployment_group_id}.
        """
        resp = self._cc._delete("/1/deploymentGroups/%s" % self.deployment_group_id)
        try:
            return resp.json()
        except Exception:
            return None

    ##
    #  edgeflows
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def edgeflows(self):
        """
        List the EdgeFlows (gateways) currently assigned to this deployment group.

        See GET /1/deploymentGroups/{deployment_group_id}/gateways.
        """
        resp = self._cc._get("/1/deploymentGroups/%s/gateways" % self.deployment_group_id)
        return resp.json().get('data', resp.json())

    ##
    #  history
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def history(self, reverse=True, limit=None, last_key=None):
        """
        Return this deployment group's deployment history.

        See GET /1/deploymentGroups/{deployment_group_id}/history.
        """
        params = {'reverse': reverse}
        if limit is not None:
            params['limit'] = limit
        if last_key is not None:
            params['last_key'] = last_key
        resp = self._cc._get("/1/deploymentGroups/%s/history" % self.deployment_group_id, params=params)
        return resp.json()

    ##
    #  prepull_status
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def prepull_status(self):
        """
        Return the prepull status for this deployment group.

        See GET /1/deploymentGroups/{deployment_group_id}/prepull.
        """
        resp = self._cc._get("/1/deploymentGroups/%s/prepull" % self.deployment_group_id)
        return resp.json()

    ##
    #  prepull_start
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def prepull_start(self, workflow_id):
        """
        Start pre-pulling the images for a workflow on this deployment group.

        See POST /1/deploymentGroups/{deployment_group_id}/prepull/{workflow_id}.
        """
        resp = self._cc._post("/1/deploymentGroups/%s/prepull/%s" % (self.deployment_group_id, workflow_id))
        return resp.json()

    ##
    #  set_target_workflow
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def set_target_workflow(self, workflow_id):
        """
        Set the target_workflow_id on this deployment group.

        See POST /1/deploymentGroups/{deployment_group_id}/targetWorkflow.
        """
        resp = self._cc._post("/1/deploymentGroups/%s/targetWorkflow" % self.deployment_group_id,
                             json={'target_workflow_id': workflow_id})
        return resp.json()


##
#  CogniacDeploymentCapacityClass
##
class CogniacDeploymentCapacityClass(object):
    """
    CogniacDeploymentCapacityClass

    A deployment capacity class describes the GPU products/type/count available
    for a deployment.
    """

    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def get_all(cls, connection):
        """
        Return all deployment capacity classes.

        See GET /1/deploymentCapacityClasses.
        """
        resp = connection._get("/1/deploymentCapacityClasses")
        data = resp.json()
        items = data.get('data', data) if isinstance(data, dict) else data
        return [CogniacDeploymentCapacityClass(connection, c) for c in items]

    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def get(cls, connection, capacity_class_id):
        """
        Return a single deployment capacity class.

        See GET /1/deploymentCapacityClasses/{capacity_class_id}.
        """
        resp = connection._get("/1/deploymentCapacityClasses/%s" % capacity_class_id)
        return CogniacDeploymentCapacityClass(connection, resp.json())

    def __init__(self, connection, capacity_dict):
        self._cc = connection
        self._capacity_keys = capacity_dict.keys()
        for k, v in capacity_dict.items():
            super(CogniacDeploymentCapacityClass, self).__setattr__(k, v)

    def __str__(self):
        return "%s (%s)" % (getattr(self, 'name', '?'),
                            getattr(self, 'deployment_capacity_class_id', '?'))

    def __repr__(self):
        return self.__str__()
