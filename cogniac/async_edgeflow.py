"""
Async CogniacEdgeFlow Object Client

Copyright (C) 2016 Cogniac Corporation
"""

import os
from time import time
from .common import retry, stop_after_attempt, wait_exponential, retry_if_exception, server_error


class AsyncCogniacEdgeFlow(object):
    """
    AsyncCogniacEdgeFlow
    Async version of CogniacEdgeFlow (CloudCore API methods only).

    Provides async access to the CloudCore API for managing EdgeFlow devices.
    Local EdgeFlow API methods (_get, _post, process_media) are not included
    in this async version.
    """

    ##
    #  get
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def get(cls, connection, edgeflow_id):
        """
        Get a single EdgeFlow.

        connection (AsyncCogniacConnection): Authenticated AsyncCogniacConnection object
        edgeflow_id (String):                the unique identifier of an EdgeFlow object

        Returns AsyncCogniacEdgeFlow object
        """
        resp = await connection._get("/1/gateways/{}".format(edgeflow_id))
        return AsyncCogniacEdgeFlow(connection, resp.json())

    ##
    #  get_all
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def get_all(cls, connection):
        """
        Return all AsyncCogniacEdgeFlow objects belonging to the authenticated tenant.

        connection (AsyncCogniacConnection): Authenticated AsyncCogniacConnection object
        """
        resp = await connection._get('/1/tenants/%s/gateways' % connection.tenant_id)
        edgeflows = resp.json()['data']
        return [AsyncCogniacEdgeFlow(connection, edgeflow) for edgeflow in edgeflows]

    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def create(cls, connection, body=None):
        """
        Create a new EdgeFlow (gateway).

        See POST /1/gateways.
        """
        resp = await connection._post("/1/gateways", json=body if body is not None else {})
        return AsyncCogniacEdgeFlow(connection, resp.json())

    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def metric_names(cls, connection):
        """
        Return the list of available EdgeFlow metric names for the tenant.

        See GET /1/metrics_name (ef-metrics-api).
        """
        resp = await connection._get("/1/metrics_name")
        return resp.json()

    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def all_metrics(cls, connection, **params):
        """
        Return EdgeFlow metrics across the tenant.

        See GET /1/metrics (ef-metrics-api).
        """
        resp = await connection._get("/1/metrics", params=params)
        return resp.json()

    ##
    #  __init__
    ##
    def __init__(self, connection, edgeflow_dict):
        """
        Initialize an AsyncCogniacEdgeFlow object.
        """
        if not edgeflow_dict:
            edgeflow_dict = {}
        super(AsyncCogniacEdgeFlow, self).__setattr__('_edgeflow_keys', edgeflow_dict.keys())

        self._cc = connection
        self._edgeflow_keys = edgeflow_dict.keys()
        for k, v in edgeflow_dict.items():
            super(AsyncCogniacEdgeFlow, self).__setattr__(k, v)

    def __setattr__(self, name, value):
        if name.startswith('_') or name not in self._edgeflow_keys:
            super(AsyncCogniacEdgeFlow, self).__setattr__(name, value)
            return
        raise AttributeError("Use 'await edgeflow.set(%s=...)' to update server-managed attributes" % name)

    def __str__(self):
        return "%s (%s)" % (self.name, self.gateway_id)

    def __repr__(self):
        return self.__str__()

    ##
    #  set
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def set(self, **kwargs):
        """
        Update edgeflow attributes via a single POST call.

        Example:
            await edgeflow.set(name="new name")
        """
        resp = await self._cc._post("/1/gateways/%s" % self.gateway_id, json=kwargs)
        for k, v in resp.json().items():
            super(AsyncCogniacEdgeFlow, self).__setattr__(k, v)

    ##
    #  update
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def update(self, body):
        """
        Update this EdgeFlow's mutable fields with the given body dict and
        return the updated EdgeFlow JSON.

        body (dict):  fields to update

        See POST /1/gateways/{gateway_id}.
        """
        resp = await self._cc._post("/1/gateways/%s" % self.gateway_id, json=body)
        result = resp.json()
        for k, v in result.items():
            super(AsyncCogniacEdgeFlow, self).__setattr__(k, v)
        return result

    # -------------------------------------------------------------------------
    #
    #  CloudCore API methods
    #
    # -------------------------------------------------------------------------

    ##
    #  status
    ##
    async def status(self,
                     subsystem_name=None,
                     start=None,
                     end=None,
                     reverse=True,
                     limit=None,
                     sort=None):
        """
        Async generator yielding EdgeFlow status, optionally for a particular subsystem.

        start (float)          filter by last update timestamp > start (seconds since epoch)
        end (float)            filter by last update timestamp < end   (seconds since epoch)
        reverse (bool)         reverse the sorting order: sort high to low
        limit (int)            yield maximum of limit results
        sort (str)             optional sort field

        Record timestamp schema (each yielded record):
          gw_timestamp  gateway-side sample clock; always present. This is the
                        canonical clock for time-series math / differencing
                        cumulative counters, and is recommended for rate math.
          cc_timestamp  CloudCore receive clock; always present.
          timestamp     now guaranteed on every yielded record. The backend
                        omits it on a minority of records; in that case it is
                        aliased to gw_timestamp here. An existing timestamp is
                        never overwritten.
        """
        args = []
        if start is not None:
            args.append("start=%f" % start)
        if end is not None:
            args.append("end=%f" % end)
        if reverse:
            args.append('reverse=True')
        if limit:
            assert(limit > 0)
            args.append('limit=%d' % min(limit, 100))

        if subsystem_name:
            url = "/1/gateways/%s/status/%s?" % (self.gateway_id, subsystem_name)
        else:
            url = "/1/gateways/%s/status?" % self.gateway_id

        if sort:
            args.append("sort=%s" % sort)

        url += "&".join(args)

        @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
        async def get_next(url):
            resp = await self._cc._get(url)
            return resp.json()

        count = 0
        while url:
            resp = await get_next(url)
            for data in resp['data']:
                # Guarantee a top-level 'timestamp' on every record. The
                # backend omits it on a minority of records (they carry only
                # gw_timestamp/cc_timestamp); alias to gw_timestamp so callers
                # can sort/diff on data['timestamp'] uniformly. Never clobber
                # an existing timestamp.
                if 'timestamp' not in data and 'gw_timestamp' in data:
                    data['timestamp'] = data['gw_timestamp']
                yield data
                count += 1
                if limit and count == limit:
                    return
            url = resp.get('paging', {}).get('next')

    ##
    #  get_aggregated_stats
    ##
    async def get_aggregated_stats(self, start=None, end=None):
        """
        Returns total detections and pixels processed
        between start and end timestamp (default: last 5 minutes).

        start (float)    filter by timestamp > start (seconds since epoch)
        end (float)      filter by timestamp < end   (seconds since epoch)
        """
        REPORTING_PERIOD_SECONDS = int(os.environ.get('REPORTING_PERIOD_SECONDS', 15))

        if end is None:
            end = time()
        if start is None:
            start = end - 300
        start = start - (start % REPORTING_PERIOD_SECONDS)
        end = end - (end % REPORTING_PERIOD_SECONDS)

        # Detection telemetry is reported as one subsystem per deployed
        # model, named ``model_detections_<model_instance_id>`` (this is how
        # all CloudFlows report). The ``status`` subsystem filter is exact
        # match only -- it does not support wildcards/prefixes -- so we pull
        # all subsystems for the window and aggregate over every event whose
        # subsystem name begins with ``model_detections_``.
        MODEL_DETECTIONS_PREFIX = 'model_detections_'

        aggregated_stats = {'total': {}, 'app': {}}
        total_model_detections = 0
        total_aggregated_media_pixels = 0
        total_aggregated_gpu_pixels = 0

        async for event in self.status(start=start,
                                       end=end,
                                       sort='edgeflow_timestamp'):
            subsystem = event.get('subsystem', '')
            if not subsystem.startswith(MODEL_DETECTIONS_PREFIX):
                continue
            app_id = subsystem[len(MODEL_DETECTIONS_PREFIX):]
            event_status = event['status'].get(app_id)
            if not event_status:
                continue
            model_detections = event_status.get('model_detections', 0)
            media_pixels = event_status.get('aggregated_media_pixels', 0)
            gpu_pixels = event_status.get('aggregated_gpu_pixels', 0)
            if gpu_pixels and app_id not in aggregated_stats['app']:
                aggregated_stats['app'][app_id] = {
                    'model_detections': 0,
                    'aggregated_media_pixels': 0,
                    'aggregated_gpu_pixels': 0}
            if gpu_pixels:
                app_stats = aggregated_stats['app'][app_id]
                app_stats['aggregated_media_pixels'] += media_pixels
                app_stats['aggregated_gpu_pixels'] += gpu_pixels
                app_stats['model_detections'] += model_detections
                total_model_detections += model_detections
                total_aggregated_media_pixels += media_pixels
                total_aggregated_gpu_pixels += gpu_pixels

        total_stats = {
            'model_detections': total_model_detections,
            'aggregated_media_pixels': total_aggregated_media_pixels,
            'aggregated_gpu_pixels': total_aggregated_gpu_pixels}
        aggregated_stats['total'].update(total_stats)
        aggregated_stats['start_timestamp'] = start
        aggregated_stats['end_timestamp'] = end
        return aggregated_stats

    ##
    #  time_bound_media_upload
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def time_bound_media_upload(self, start_time, end_time):
        """
        Request a time region to upload images from the EdgeFlow to CloudCore.
        Must specify start_time and end_time in unix time.
        """
        args = dict()
        args['start_time'] = start_time
        args['end_time'] = end_time
        await self._cc._post("/1/gateways/%s/event/time_bound_media_upload" % self.gateway_id, json=args)

    ##
    #  flush_upload_queue
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def flush_upload_queue(self, start_time=None, end_time=None):
        """
        Flush the EdgeFlow to Core upload queue.
        """
        args = dict()
        if start_time is not None:
            args['start_time'] = start_time
        if end_time is not None:
            args['end_time'] = end_time
        await self._cc._post("/1/gateways/%s/event/flush_upload_queue" % self.gateway_id, json=args)

    ##
    #  factory_reset
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def factory_reset(self):
        """
        Factory reset the EdgeFlow.
        This results in deletion of this EdgeFlow object in CloudCore/SiteCore!
        """
        await self._cc._post("/1/gateways/%s/event/factory_reset" % self.gateway_id)

    ##
    #  upgrade
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def upgrade(self, software_version):
        """
        Upgrade the EdgeFlow to the specified software version.
        """
        args = dict()
        if software_version is not None:
            args['software_version'] = software_version
        await self._cc._post("/1/gateways/%s/event/upgrade" % self.gateway_id, json=args)

    ##
    #  set_boot_software_version
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def set_boot_software_version(self, software_version):
        """
        Set the boot software version for the EdgeFlow.
        """
        args = dict()
        if software_version is not None:
            args['software_version'] = software_version
        await self._cc._post("/1/gateways/%s/event/set_boot_software_version" % self.gateway_id, json=args)

    ##
    #  reboot
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def reboot(self):
        """
        Reboot the EdgeFlow.
        """
        await self._cc._post("/1/gateways/%s/event/reboot" % self.gateway_id)

    ##
    #  ping
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def ping(self, ping_id=None):
        """
        Send ping event with optional ping_id.
        EdgeFlow will respond with a status message with subsystem="ping".
        """
        event = {"timestamp": time()}
        if ping_id is not None:
            event['ping_id'] = ping_id
        await self._cc._post("/1/gateways/%s/event/ping" % self.gateway_id, json=event)

    ##
    #  trigger_camera_capture
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def trigger_camera_capture(self, subject_uid, trigger_domain_unit=None):
        """
        Trigger a camera capture app via the public-api.
        subject_uid of the 'trigger subject' is required.
        """
        event = {'subject_uid': subject_uid}
        if trigger_domain_unit is not None:
            event['trigger_domain_unit'] = trigger_domain_unit
        await self._cc._post("/1/gateways/%s/event/trigger_camera_capture" % self.gateway_id, json=event)

    ##
    #  delete
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def delete(self):
        """
        Delete this EdgeFlow (gateway).

        See DELETE /1/gateways/{gw_id}.
        """
        await self._cc._delete("/1/gateways/%s" % self.gateway_id)

    ##
    #  TLS certificate
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def get_certificate(self):
        """
        Return this EdgeFlow's TLS certificate.

        See GET /1/gateways/{gateway_id}/certificate.
        """
        resp = await self._cc._get("/1/gateways/%s/certificate" % self.gateway_id)
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def set_certificate(self, body=None):
        """
        Create/set this EdgeFlow's TLS certificate.

        See POST /1/gateways/{gateway_id}/certificate.
        """
        resp = await self._cc._post("/1/gateways/%s/certificate" % self.gateway_id,
                                   json=body if body is not None else {})
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def replace_certificate(self, body=None):
        """
        Replace this EdgeFlow's TLS certificate (idempotent PUT).

        See PUT /1/gateways/{gateway_id}/certificate.
        """
        resp = await self._cc._put("/1/gateways/%s/certificate" % self.gateway_id,
                                   json=body if body is not None else {})
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def delete_certificate(self):
        """
        Delete this EdgeFlow's TLS certificate.

        See DELETE /1/gateways/{gateway_id}/certificate.
        """
        await self._cc._delete("/1/gateways/%s/certificate" % self.gateway_id)

    ##
    #  metrics
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def metrics(self, **params):
        """
        Return runtime metrics for this EdgeFlow.

        The EdgeFlow is identified via the gateway_id query parameter.

        See GET /1/metrics/ef (ef-metrics-api).
        """
        params.setdefault('gateway_id', self.gateway_id)
        resp = await self._cc._get("/1/metrics/ef", params=params)
        return resp.json()
