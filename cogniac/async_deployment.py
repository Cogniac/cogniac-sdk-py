"""
Async CogniacDeployment (deployment group) Object Client

Copyright (C) 2024 Cogniac Corporation
"""

from .common import retry, stop_after_attempt, wait_exponential, retry_if_exception, server_error


class AsyncCogniacDeployment(object):
    """
    AsyncCogniacDeployment
    Async version of CogniacDeployment.

    A deployment group is a collection of EdgeFlows that share a workflow /
    model deployment.
    """

    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def get_all(cls, connection):
        """
        Return all AsyncCogniacDeployment objects belonging to the authenticated tenant.

        See GET /1/tenants/{tenant_id}/deploymentGroups.
        """
        resp = await connection._get("/1/tenants/%s/deploymentGroups" % connection.tenant_id)
        groups = resp.json()['data']
        return [AsyncCogniacDeployment(connection, g) for g in groups]

    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def get(cls, connection, deployment_group_id):
        """
        Return a single AsyncCogniacDeployment by deployment_group_id.

        See GET /1/deploymentGroups/{deployment_group_id}.
        """
        resp = await connection._get("/1/deploymentGroups/%s" % deployment_group_id)
        return AsyncCogniacDeployment(connection, resp.json())

    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def create(cls, connection, body=None):
        """
        Create a new deployment group.

        See POST /1/deploymentGroups.
        """
        resp = await connection._post("/1/deploymentGroups", json=body if body is not None else {})
        return AsyncCogniacDeployment(connection, resp.json())

    def __init__(self, connection, deployment_dict):
        self._cc = connection
        self._deployment_keys = deployment_dict.keys()
        for k, v in deployment_dict.items():
            super(AsyncCogniacDeployment, self).__setattr__(k, v)

    def __str__(self):
        return "%s (%s)" % (getattr(self, 'name', '?'), self.deployment_group_id)

    def __repr__(self):
        return self.__str__()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def delete(self):
        """
        Delete this deployment group.

        See DELETE /1/deploymentGroups/{deployment_group_id}.
        """
        resp = await self._cc._delete("/1/deploymentGroups/%s" % self.deployment_group_id)
        try:
            return resp.json()
        except Exception:
            return None

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def edgeflows(self):
        """
        List the EdgeFlows (gateways) currently assigned to this deployment group.

        See GET /1/deploymentGroups/{deployment_group_id}/gateways.
        """
        resp = await self._cc._get("/1/deploymentGroups/%s/gateways" % self.deployment_group_id)
        return resp.json().get('data', resp.json())

    async def history(self, reverse=True, limit=None, last_key=None):
        """
        Async generator yielding this deployment group's deployment-history
        records, following the DynamoDB last_key cursor until the full history
        is drained.

        reverse (bool)   reverse the sorting order
        limit (int)      yield maximum of limit records
        last_key (str)   resume from a previous last_key cursor

        See GET /1/deploymentGroups/{deployment_group_id}/history.
        """
        @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
        async def get_next(last_key):
            params = {'reverse': reverse}
            if limit is not None:
                params['limit'] = limit
            if last_key is not None:
                params['last_key'] = last_key
            resp = await self._cc._get("/1/deploymentGroups/%s/history" % self.deployment_group_id, params=params)
            return resp.json()

        count = 0
        while True:
            resp = await get_next(last_key)
            data = resp['data'] if isinstance(resp, dict) and 'data' in resp else resp
            for record in data:
                yield record
                count += 1
                if limit and count == limit:
                    return
            last_key = resp.get('last_key') if isinstance(resp, dict) else None
            if not last_key:
                return

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def prepull_status(self):
        """
        Return the prepull status for this deployment group.

        See GET /1/deploymentGroups/{deployment_group_id}/prepull.
        """
        resp = await self._cc._get("/1/deploymentGroups/%s/prepull" % self.deployment_group_id)
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def prepull_start(self, workflow_id):
        """
        Start pre-pulling the images for a workflow on this deployment group.

        See POST /1/deploymentGroups/{deployment_group_id}/prepull/{workflow_id}.
        """
        resp = await self._cc._post("/1/deploymentGroups/%s/prepull/%s" % (self.deployment_group_id, workflow_id))
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def set_target_workflow(self, workflow_id):
        """
        Set the target_workflow_id on this deployment group.

        See POST /1/deploymentGroups/{deployment_group_id}/targetWorkflow.
        """
        resp = await self._cc._post("/1/deploymentGroups/%s/targetWorkflow" % self.deployment_group_id,
                                   json={'target_workflow_id': workflow_id})
        return resp.json()


class AsyncCogniacDeploymentCapacityClass(object):
    """
    AsyncCogniacDeploymentCapacityClass
    Async version of CogniacDeploymentCapacityClass.
    """

    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def get_all(cls, connection):
        """
        Return all deployment capacity classes.

        See GET /1/deploymentCapacityClasses.
        """
        resp = await connection._get("/1/deploymentCapacityClasses")
        data = resp.json()
        items = data.get('data', data) if isinstance(data, dict) else data
        return [AsyncCogniacDeploymentCapacityClass(connection, c) for c in items]

    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def get(cls, connection, capacity_class_id):
        """
        Return a single deployment capacity class.

        See GET /1/deploymentCapacityClasses/{capacity_class_id}.
        """
        resp = await connection._get("/1/deploymentCapacityClasses/%s" % capacity_class_id)
        return AsyncCogniacDeploymentCapacityClass(connection, resp.json())

    def __init__(self, connection, capacity_dict):
        self._cc = connection
        self._capacity_keys = capacity_dict.keys()
        for k, v in capacity_dict.items():
            super(AsyncCogniacDeploymentCapacityClass, self).__setattr__(k, v)

    def __str__(self):
        return "%s (%s)" % (getattr(self, 'name', '?'),
                            getattr(self, 'deployment_capacity_class_id', '?'))

    def __repr__(self):
        return self.__str__()
