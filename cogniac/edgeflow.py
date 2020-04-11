"""
CogniacEdgeFlow Object Client

Copyright (C) 2016 Cogniac Corporation
"""

import os
import sys
import logging
import requests
import socket
import re
from retrying import retry
from requests.auth import HTTPBasicAuth
from requests.packages.urllib3 import Retry
from requests.adapters import HTTPAdapter

from common import server_error, raise_errors

from media import file_creation_time

IP_REGEX = re.compile('^(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])$')

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
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def get(cls, connection, edgeflow_id):
        """
        Get a single EdgeFlow.
        connnection (CogniacConnection): Authenticated CogniacConnection object
        edgeflow_id (String): the unique identifier of a EdgeFlow object
        returns CogniacEdgeFlow object
        """
        edgeflow_dict = None
        resp = connection._get("/gateways/{}".format(edgeflow_id))
        return CogniacEdgeFlow(connection, resp.json())

    @classmethod
    def get_all(cls, connection):
        """
        return all CogniacEdgeFlow objects belonging to the currently authenticated tenant

        connnection (CogniacConnection):     Authenticated CogniacConnection object
        """
        resp = connection._get('/tenants/%s/gateways' % connection.tenant.tenant_id)
        edgeflows = resp.json()['data']
        return [CogniacEdgeFlow(connection, edgeflow) for edgeflow in edgeflows]

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

        # Validate IP address.
        if self.ip_address and IP_REGEX.match(self.ip_address):
            self.url_prefix = 'http://{}:8000/1'.format(self.ip_address)
        else:
            self.url_prefix = None

        self.timeout = timeout

        self.__initialize()

    def __setattr__(self, name, value):
        if name not in self._edgeflow_keys:
            super(CogniacEdgeFlow, self).__setattr__(name, value)
            return
        data = {name: value}
        resp = self._cc._post("/gateways/%s" % self.gateway_id, json=data)
        for k, v in resp.json().items():
            super(CogniacEdgeFlow, self).__setattr__(k, v)

    def __str__(self):
        s = "%s (%s)" % (self.name, self.gateway_id)
        return s.encode(sys.stdout.encoding)

    def __repr__(self):
        s = "%s (%s)" % (self.name, self.gateway_id)
        return s.encode(sys.stdout.encoding)

    # -------------------------------------------------------------------------
    #
    #  EdgeFlow API.
    #
    # -------------------------------------------------------------------------

    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def __initialize(self):
        self.session = requests.Session()

        # Configure session with appropriate retries.
        self.session.mount('https://', HTTPAdapter(
            max_retries=Retry(connect=5,
                              read=5,
                              status=5,
                              redirect=2,
                              backoff_factor=.001,
                              status_forcelist=(500, 502, 503, 504))))

    @retry(stop_max_attempt_number=3, retry_on_exception=lambda e: isinstance(e, Exception))
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

    @retry(stop_max_attempt_number=3, retry_on_exception=lambda e: isinstance(e, Exception))
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
        resp = self._get("/version")
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

        subject_uid		                  A subject's unique identifier.
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

        @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
        def upload():
            if filename.startswith('http'):
                raise Exception("The media file must be uploaded from local storage.")
            else:
                files = {'file': open(filename, 'rb')}
            resp = self._post("/process/{}".format(subject_uid), data=args, files=files)
            return resp

        resp = upload()
        return resp.json()

    # -------------------------------------------------------------------------
    #
    #  CloudCore API.
    #
    # -------------------------------------------------------------------------

    def flush_upload_queue(self, start_time=None, stop_time=None):
        args = dict()
        if start_time is not None:
            args['start_time'] = start_time
        if stop_time is not None:
            args['stop_time'] = stop_time
        resp = self._cc._post("/gateways/%s/event/flush_upload_queue" % (self.gateway_id), data=args)

    def factory_reset(self):
        resp = self._cc._post("/gateways/%s/event/factory_reset" % (self.gateway_id))

    def upgrade(self, software_version):
        args = dict()
        if software_version is not None:
            args['software_version'] = software_version
        resp = self._cc._post("/gateways/%s/event/upgrade" % (self.gateway_id), data=args)

    def reboot(self):
        resp = self._cc._post("/gateways/%s/event/reboot" % (self.gateway_id))

    def status(self, subsystem_name=None, start=None, end=None, reverse=True, limit=None):
        """
        Yields EdgeFlow status, optionally only for a particular subsytem, sorted by timestamp.

        start (float)          filter by last update timestamp > start (seconds since epoch)
        end (float)            filter by last update timestamp < end   (seconds since epoch)
        reverse (bool)         reverse the sorting order: sort high to low
        limit (int)            yield maximum of limit results
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
            url = "/gateways/%s/status/%s?" % self.gateway_id, subsystem_name
        else:
            url = "/gateways/%s/status?" % self.gateway_id
        del args['subsystem_name']
        url += "&".join(args)

        @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
        def get_next(url):
            resp = self._cc._get(url)
            return resp.json()

        count = 0
        while url:
            resp = get_next(url)
            for data in resp['data']:
                yield data
                count += 1
                if limit and count == limit:
                    return
            url = resp['paging'].get('next')