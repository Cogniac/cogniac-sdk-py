"""
CogniacDeployment (deployment group) Object Client

Copyright (C) 2024 Cogniac Corporation
"""

from .common import retry, stop_after_attempt, wait_exponential, retry_if_exception, server_error

# Default read timeout (seconds) for deploy(). The dispatch blocks server-side
# until every EdgeFlow in the group accepts the deployment event, so large
# groups need far longer than the connection's default 60s timeout.
DEPLOY_DEFAULT_TIMEOUT = 300


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
    def history(self, reverse=True, limit=None, last_key=None):
        """
        Yield this deployment group's deployment-history records, following the
        DynamoDB last_key cursor until the full history is drained.

        reverse (bool)   reverse the sorting order
        limit (int)      yield maximum of limit records
        last_key (str)   resume from a previous last_key cursor

        See GET /1/deploymentGroups/{deployment_group_id}/history.
        """
        @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
        def get_next(last_key):
            params = {'reverse': reverse}
            if limit is not None:
                params['limit'] = limit
            if last_key is not None:
                params['last_key'] = last_key
            resp = self._cc._get("/1/deploymentGroups/%s/history" % self.deployment_group_id, params=params)
            return resp.json()

        count = 0
        while True:
            resp = get_next(last_key)
            data = resp['data'] if isinstance(resp, dict) and 'data' in resp else resp
            for record in data:
                yield record
                count += 1
                if limit and count == limit:
                    return
            last_key = resp.get('last_key') if isinstance(resp, dict) else None
            if not last_key:
                return

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

        This only RECORDS the target — it does NOT dispatch a rollout and
        leaves current_workflow_id unchanged. Call deploy() to actually
        deploy the workflow to the group's EdgeFlows.

        See POST /1/deploymentGroups/{deployment_group_id}/targetWorkflow.
        """
        resp = self._cc._post("/1/deploymentGroups/%s/targetWorkflow" % self.deployment_group_id,
                             json={'target_workflow_id': workflow_id})
        return resp.json()

    ##
    #  deploy
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def deploy(self, workflow_id, now=False, timeout=None):
        """
        DISPATCH a workflow rollout to every EdgeFlow in this deployment group.

        Unlike set_target_workflow(), which only records the target_workflow_id
        without deploying anything, this call actually triggers the rollout.

        workflow_id (str)  the workflow to deploy
        now (bool)         False (default): set next_workflow_id — dispatched
                           immediately when the group has no scheduled_time,
                           otherwise picked up by the deployment scheduler.
                           True: set deploy_now_workflow_id — immediate one-off
                           dispatch that bypasses the group's schedule.
        timeout (float)    read timeout in seconds (default DEPLOY_DEFAULT_TIMEOUT,
                           300). The server blocks until every EdgeFlow in the
                           group accepts the deployment event, so large groups
                           need a generous timeout. If the call raises a read
                           timeout the dispatch may still complete server-side —
                           check deploy_status() before retrying.

        Returns the updated deployment group JSON (next_workflow_id set on a
        successful dispatch; the group later converges so current_workflow_id
        == target_workflow_id and next_workflow_id returns to null).

        See POST /1/deploymentGroups/{deployment_group_id}.
        """
        if timeout is None:
            timeout = DEPLOY_DEFAULT_TIMEOUT
        key = 'deploy_now_workflow_id' if now else 'next_workflow_id'
        resp = self._cc._post("/1/deploymentGroups/%s" % self.deployment_group_id,
                             json={key: workflow_id}, timeout=timeout)
        return resp.json()

    ##
    #  deploy_status
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def deploy_status(self):
        """
        Return this deployment group's rollout convergence status.

        Idempotent status check: re-GETs the group and returns a dict with
        target_workflow_id / current_workflow_id / next_workflow_id /
        deploy_now_workflow_id plus a boolean 'converged' (True when
        current_workflow_id == target_workflow_id and no next_workflow_id is
        pending). Use after deploy() — especially after a client read
        timeout — to determine whether the dispatch completed server-side.

        See GET /1/deploymentGroups/{deployment_group_id}.
        """
        resp = self._cc._get("/1/deploymentGroups/%s" % self.deployment_group_id)
        group = resp.json()
        target = group.get('target_workflow_id')
        current = group.get('current_workflow_id')
        next_wf = group.get('next_workflow_id')
        return {
            'deployment_group_id': group.get('deployment_group_id', self.deployment_group_id),
            'target_workflow_id': target,
            'current_workflow_id': current,
            'next_workflow_id': next_wf,
            'deploy_now_workflow_id': group.get('deploy_now_workflow_id'),
            'converged': current is not None and current == target and next_wf is None,
        }


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
