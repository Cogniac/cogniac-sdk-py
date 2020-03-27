"""
CogniacGateway Object Client

Copyright (C) 2016 Cogniac Corporation
"""

import os
import logging
import requests
from retrying import retry
from requests.auth import HTTPBasicAuth
from requests.packages.urllib3 import Retry
from requests.adapters import HTTPAdapter

from common import server_error, raise_errors

from media import file_creation_time


logger = logging.getLogger(__name__)

class CogniacGateway(object):
    """
    CogniacGateway

    Connect to a Cogniac EdgeFlow gateway and maintain session state.
    
    Class definition for an object that stores information about a physical
    Cogniac gateway device (i.e., EdgeFlow) and methods that provide a client
    interface for programmatically managing and requesting work to be done
    on the gateway.
    
    A CogniacGateway object's methods can be used to trigger media capture
    (e.g., triggering cameras to save images to a gateway) and ingesting
    media from another host on the same network.
    """

    def __init__(self, timeout=60, url_prefix=None):
        """
        Initialize a CogniacGateway object.
        
        url_prefix (String):          URL prefix for a Cogniac EdgeFlow device.
        """
        if 'COG_GW_URL_PREFIX' in os.environ:
            url_prefix = os.environ['COG_GW_URL_PREFIX']

        if not url_prefix:
            raise Exception("No EdgeFlow URL prefix was specified.")

        self.url_prefix = url_prefix
        self.timeout = timeout

        self.__initialize()

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

    def process_media(self,
                      subject_uid,
                      filename,
                      external_media_id=None,
                      media_timestamp=None,
                      domain_unit=None,
                      post_url=None):
        """
        Uploads a media file object to an EdgeFlow gateway device.

        connnection (CogniacGateway):     CogniacGateway object
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