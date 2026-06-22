"""
CogniacEdgeFlow Object Client

Copyright (C) 2016 Cogniac Corporation
"""

import os
import re
from time import time
import httpx
from .common import retry, stop_after_attempt, wait_exponential, retry_if_exception
from .common import server_error, raise_errors
from .media import file_creation_time


IP_REGEX = re.compile('^(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])$')


CLOUDFLOW_PREFIX = "cloudflow.cogniac.io"


class CogniacEdgeFlow(object):
    """
    CogniacEdgeFlow

    connnection (CogniacConnection):     Authenticated CogniacConnection object.

                                         If unspecified, CloudCore functions will not be available.

    url_prefix (String):                 Cogniac EdgeFlow API url prefix.

                                         This is a local URL of a physical EdgeFlow.

                                         Defaults to `None`. If unspecified, the EdgeFlow's local APIs will not be available

    Connect to a Cogniac EdgeFlow and maintain session state.

    Class definition for an object that stores information about a physical
    Cogniac EdgeFlow and methods that provide a client
    interface for programmatically managing and requesting work to be done
    on the EdgeFlow.

    A Cogniac EdgeFlow object's methods can be used to trigger media capture
    (e.g., triggering cameras to save images to an EdgeFlow) and ingesting
    media from another host on the same network.
    """

    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def get(cls, connection, edgeflow_id):
        """
        Get a single EdgeFlow.
        connnection (CogniacConnection): Authenticated CogniacConnection object
        edgeflow_id (String): the unique identifier of a EdgeFlow object
        returns CogniacEdgeFlow object
        """
        edgeflow_dict = None
        resp = connection._get("/1/gateways/{}".format(edgeflow_id))
        return CogniacEdgeFlow(connection, resp.json())

    @classmethod
    def get_all(cls, connection):
        """
        return all CogniacEdgeFlow objects belonging to the currently authenticated tenant

        connnection (CogniacConnection):     Authenticated CogniacConnection object
        """
        resp = connection._get('/1/tenants/%s/gateways' % connection.tenant.tenant_id)
        edgeflows = resp.json()['data']
        return [CogniacEdgeFlow(connection, edgeflow) for edgeflow in edgeflows]

    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def create(cls, connection, body=None):
        """
        Create a new EdgeFlow (gateway).

        connection (CogniacConnection):  Authenticated CogniacConnection object
        body (dict):                     CreateGatewayRequest body

        See POST /1/gateways.
        """
        resp = connection._post("/1/gateways", json=body if body is not None else {})
        return CogniacEdgeFlow(connection, resp.json())

    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def metric_names(cls, connection):
        """
        Return the list of available EdgeFlow metric names for the tenant.

        See GET /1/metrics_name (ef-metrics-api).
        """
        resp = connection._get("/1/metrics_name")
        return resp.json()

    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def all_metrics(cls, connection, **params):
        """
        Return EdgeFlow metrics across the tenant.

        The metrics service requires a `metric_name` and a `tenant_id`; the
        tenant_id is injected from the connection when not supplied by the
        caller. Optional `start`/`end` (paired Unix epoch seconds) bound the
        time window. Extra keyword args are passed through as query parameters.

        See GET /1/metrics (ef-metrics-api).
        """
        params.setdefault('tenant_id', connection.tenant_id)
        resp = connection._get("/1/metrics", params=params)
        return resp.json()

    def __init__(self, connection, edgeflow_dict, timeout=60):
        """
        Initialize a CogniacEdgeFlow object.
        """
        if not edgeflow_dict:
            edgeflow_dict = {}
        super(CogniacEdgeFlow, self).__setattr__('_edgeflow_keys', edgeflow_dict.keys())

        self._cc = connection
        self._edgeflow_keys = edgeflow_dict.keys()
        for k, v in edgeflow_dict.items():
            super(CogniacEdgeFlow, self).__setattr__(k, v)

        self.timeout = timeout

        self.__initialize()

    def __setattr__(self, name, value):
        if name not in self._edgeflow_keys:
            super(CogniacEdgeFlow, self).__setattr__(name, value)
            return
        data = {name: value}
        resp = self._cc._post("/1/gateways/%s" % self.gateway_id, json=data)
        for k, v in resp.json().items():
            super(CogniacEdgeFlow, self).__setattr__(k, v)

    def __str__(self):
        return "%s (%s)" % (self.name, self.gateway_id)

    def __repr__(self):
        return self.__str__()

    # -------------------------------------------------------------------------
    #
    #  EdgeFlow API.
    #
    # -------------------------------------------------------------------------
    def __set_url_prefix(self):
        """ Setup url prefix based on model of Edgeflow (cloudflow vs edgeflow).
            For local http actions, the WAN0 ip address is used"""
        self.url_prefix = None
        if 'cf' in self.model.lower():
            # cloudflow uses https based post request with token
            self.url_prefix = 'https://{}.{}'.format(self.gateway_id, CLOUDFLOW_PREFIX)
            self._post = self._cc._post
        else:
            # use wan0 if available as the http destination ip addres
            ifconfigs = list(self.status(subsystem_name='ifconfig', limit=1))

            if ifconfigs:
                self.ip_address = ifconfigs[0]['status']['wan0']['ip']

                if IP_REGEX.match(self.ip_address):
                    self.url_prefix = 'http://{}:8000'.format(self.ip_address)

    def __initialize(self):
        self.__set_url_prefix()

        # Configure session with appropriate retries.
        transport = httpx.HTTPTransport(retries=5)
        self.session = httpx.Client(transport=transport, follow_redirects=True)

    @retry(stop=stop_after_attempt(3), retry=retry_if_exception(lambda e: isinstance(e, Exception)))
    def _get(self, url, timeout=None, **kwargs):
        """
        Wrapper method to retry an HTTP GET request if an Exception is raised
        when making the request.
        """
        if not url.startswith("http"):
            url = self.url_prefix + url
        if timeout is None:
            timeout = self.timeout
        resp = self.session.get(url, timeout=timeout, **kwargs)
        raise_errors(resp)
        return resp

    @retry(stop=stop_after_attempt(3), retry=retry_if_exception(lambda e: isinstance(e, Exception)))
    def _post(self, url, timeout=None, **kwargs):
        """
        Wrapper method to retry an HTTP POST request if an Exception is raised
        when making the request.
        """
        if not url.startswith("http"):
            url = self.url_prefix + url
        if timeout is None:
            timeout = self.timeout
        resp = self.session.post(url, timeout=timeout, **kwargs)
        raise_errors(resp)
        return resp

    def get_version(self):
        resp = self._get("/1/version")
        return resp.json()


    def process_media(self,
                      subject_uid,
                      filename,
                      external_media_id=None,
                      media_timestamp=None,
                      domain_unit=None,
                      post_url=None):
        """
        Uploads a media file object to an EdgeFlow device.

        subject_uid                               A subject's unique identifier.
        filename (str):                   Local filename or http/s URL of image or video media file
        external_media_id (str):          Optional arbitrary external id for this media
        media_timestamp (float):          Optional actual timestamp of media creation/occurance time
        domain_unit (str):                Optional domain id (e.g. serial number) for set assignment grouping.
                                          Media with the same domain_unit will always be assigned to the same
                                          training or validation set. Set this to avoid overfitting when you have
                                          multiple images of the same thing or almost the same thing.
        post_url (str):                   Optional URL where media detections can be posted.

        Returns a MediaDetections list.
        """

        args = dict()
        if external_media_id is not None:
            args['external_media_id'] = external_media_id
        if media_timestamp is not None:
            args['media_timestamp'] = media_timestamp
        if domain_unit is not None:
            args['domain_unit'] = domain_unit
        if post_url is not None:
            args['post_url'] = post_url

        if filename.startswith('http'):
            raise Exception("The media file must be uploaded from local storage.")
        else:  # local filename
            fstat = os.stat(filename)
            if 'media_timestamp' not in args:
                # set the unspecified media timestamp to the earliest file time we have
                args['media_timestamp'] = file_creation_time(filename)

        @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
        def upload():
            if filename.startswith('http'):
                raise Exception("The media file must be uploaded from local storage.")
            else:
                files = {'file': open(filename, 'rb')}
            url = "%s/%s/%s" % (self.url_prefix, "1/process", subject_uid)
            resp = self._post(url, data=args, files=files)
            return resp

        resp = upload()
        return resp.json()

    # -------------------------------------------------------------------------
    #
    #  CloudCore API.
    #
    # -------------------------------------------------------------------------

    def time_bound_media_upload(self, start_time, end_time):
        """
        Request a time region to upload iamges from the EdgeFlow to CloudCore
        Must specify start_time and stop_time in unix time
        """
        args = dict()
        args['start_time'] = start_time
        args['end_time'] = end_time
        self._cc._post("/1/gateways/%s/event/time_bound_media_upload" % (self.gateway_id), json=args)


    def flush_upload_queue(self, start_time=None, end_time=None):
        """
        Flush the EdgeFlow to Core upload queue
        """
        args = dict()
        if start_time is not None:
            args['start_time'] = start_time
        if end_time is not None:
            args['end_time'] = end_time
        self._cc._post("/1/gateways/%s/event/flush_upload_queue" % (self.gateway_id), json=args)


    def factory_reset(self):
        """
        Factory reset the EdgeFlow.
        This results in deletion of this EdgeFlow object in CloudCore/SiteCore!
        """
        self._cc._post("/1/gateways/%s/event/factory_reset" % (self.gateway_id))

    def upgrade(self, software_version):
        """
        Upgrade the edgeflow to the specified software version
        """
        args = dict()
        if software_version is not None:
            args['software_version'] = software_version
        self._cc._post("/1/gateways/%s/event/upgrade" % (self.gateway_id), json=args)

    def set_boot_software_version(self, software_version):
        """
        Upgrade the edgeflow to the specified software version
        """
        args = dict()
        if software_version is not None:
            args['software_version'] = software_version
        self._cc._post("/1/gateways/%s/event/set_boot_software_version" % (self.gateway_id), json=args)

    def reboot(self):
        """
        Reboot the EdgeFlow
        """
        self._cc._post("/1/gateways/%s/event/reboot" % (self.gateway_id))

    def ping(self, ping_id=None):
        """
        Send ping event with optional ping_id.
        EdgeFlow will respond with status message with subsystem="ping"
        """
        event = {"timestamp": time()}
        if ping_id is not None:
            event['ping_id'] = ping_id
        self._cc._post("/1/gateways/%s/event/ping" % self.gateway_id, json=event)

    def trigger_camera_capture(self, subject_uid, trigger_domain_unit=None):
        """
        trigger a camera capture app via the public-api
        subject_uid of the 'trigger subject' is required
        """
        event = {'subject_uid': subject_uid}
        if trigger_domain_unit is not None:
            event['trigger_domain_unit'] = trigger_domain_unit
        self._cc._post("/1/gateways/%s/event/trigger_camera_capture" % self.gateway_id, json=event)

    def status(self,
               subsystem_name=None,
               start=None,
               end=None,
               reverse=True,
               limit=None,
               sort=None):
        """
        Yields EdgeFlow status, optionally only for a particular subsytem,
         sorted by timestamp.

        start (float)          filter by last update timestamp > start
                               (seconds since epoch)
        end (float)            filter by last update timestamp < end
                               (seconds since epoch)
        reverse (bool)         reverse the sorting order: sort high to low
        limit (int)            yield maximum of limit results

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
            args.append('limit=%d' % min(limit, 100))  # api support max limit of 100

        if subsystem_name:
            url = "/1/gateways/%s/status/%s?" % (self.gateway_id,
                                                 subsystem_name)
        else:
            url = "/1/gateways/%s/status?" % self.gateway_id
        
        if sort:
            args.append("sort=%s" % sort)

        url += "&".join(args)

        def get_next(url):
            resp = self._cc._get(url)
            return resp.json()

        count = 0
        while url:
            resp = get_next(url)
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
            url = resp['paging'].get('next')

    def get_aggregated_stats(self, start=None, end=None):
        """
        Returns total detections and pixels processed 
        between start and end timestamp (default: last 5 minutes)

        start (float)    filter by last update 
                         timestamp > start (seconds since epoch)
        end (float)      filter by last update
                         timestamp < end   (seconds since epoch)
        """
        REPORTING_PERIOD_SECONDS = int(os.environ.get(
                                        'REPORTING_PERIOD_SECONDS', 15))

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
        events = self.status(start=start,
                             end=end,
                             sort='edgeflow_timestamp')

        aggregated_stats = {'total': {}, 'app': {}}
        total_model_detections = 0
        total_aggregated_media_pixels = 0
        total_aggregated_gpu_pixels = 0
        for event in events:
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
    #  delete
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def delete(self):
        """
        Delete this EdgeFlow (gateway).

        See DELETE /1/gateways/{gw_id}.
        """
        self._cc._delete("/1/gateways/%s" % self.gateway_id)

    ##
    #  update
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def update(self, body):
        """
        Update this EdgeFlow's mutable fields with the given body dict and
        return the updated EdgeFlow JSON.

        body (dict):  fields to update

        See POST /1/gateways/{gateway_id}.
        """
        resp = self._cc._post("/1/gateways/%s" % self.gateway_id, json=body)
        result = resp.json()
        for k, v in result.items():
            super(CogniacEdgeFlow, self).__setattr__(k, v)
        return result

    ##
    #  TLS certificate
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def get_certificate(self):
        """
        Return this EdgeFlow's TLS certificate.

        See GET /1/gateways/{gateway_id}/certificate.
        """
        resp = self._cc._get("/1/gateways/%s/certificate" % self.gateway_id)
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def set_certificate(self, body=None):
        """
        Create/set this EdgeFlow's TLS certificate.

        body (dict):  TLS certificate/key pair body

        See POST /1/gateways/{gateway_id}/certificate.
        """
        resp = self._cc._post("/1/gateways/%s/certificate" % self.gateway_id,
                             json=body if body is not None else {})
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def replace_certificate(self, body=None):
        """
        Replace this EdgeFlow's TLS certificate (idempotent PUT).

        body (dict):  TLS certificate/key pair body

        See PUT /1/gateways/{gateway_id}/certificate.
        """
        resp = self._cc._put("/1/gateways/%s/certificate" % self.gateway_id,
                             json=body if body is not None else {})
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def delete_certificate(self):
        """
        Delete this EdgeFlow's TLS certificate.

        See DELETE /1/gateways/{gateway_id}/certificate.
        """
        self._cc._delete("/1/gateways/%s/certificate" % self.gateway_id)

    ##
    #  metrics
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def metrics(self, **params):
        """
        Return runtime metrics for this EdgeFlow.

        The metrics service requires a `metric_name`, a `tenant_id`, and an
        `ef_id`; the ef_id is injected from this EdgeFlow's gateway_id and the
        tenant_id from the connection when not supplied by the caller. Optional
        `start`/`end` (paired Unix epoch seconds) bound the time window. Extra
        keyword args are passed through as query parameters.

        See GET /1/metrics/ef (ef-metrics-api).
        """
        params.setdefault('ef_id', self.gateway_id)
        params.setdefault('tenant_id', self._cc.tenant_id)
        resp = self._cc._get("/1/metrics/ef", params=params)
        return resp.json()
