"""
Cogniac Network Camera Object Client

Copyright (C) 2019 Cogniac Corporation
"""

from retrying import retry
import sys
from common import server_error


##
#  Cogniac Ops Review
##
class CogniacNetworkCamera(object):
    """
    CogniacNetworkCamera
    """

    ##
    #  create
    ##
    @classmethod
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def create(cls,
               connection,
               name=None,
               description=None,
               active=True,
               url=None):

        """
        Create a network camera object

        connnection (CogniacConnection): Authenticated CogniacConnection object
        """
        if active:
            data = {'active': 1}
        else:
            data = {'active': 0}

        if name:
            data['camera_name'] = name

        if description:
            data['description'] = description

        if url:
            data['url'] = url

        resp = connection._post("/networkCameras", json=data)
        return CogniacNetworkCamera(connection, resp.json())

    ##
    #  get
    ##
    @classmethod
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def get(cls,
            connection,
            network_camera_id):
        """
        get single network camera
        connnection (CogniacConnection): Authenticated CogniacConnection object
        network_camera_id (String): the netcam id of the Cogniac NetCam object
        returns CogniacNetworkCamera object
        """
        resp = connection._get("/networkCameras/%s" % network_camera_id)
        return CogniacNetworkCamera(connection, resp.json())

    ##
    #  get_all
    ##
    @classmethod
    def get_all(cls, connection):
        """
        return CogniacApplications for all applications belonging to the currently authenticated tenant

        connnection (CogniacConnection):     Authenticated CogniacConnection object
        """
        resp = connection._get('/tenants/%s/networkCameras' % connection.tenant.tenant_id)
        netcams = resp.json()['data']
        print "netcams", netcams
        for netcam in netcams:
            print netcam
        return [CogniacNetworkCamera(connection, netcam) for netcam in netcams]

    ##
    #  delete
    ##
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def delete(self):
        """
        Delete the op review result.
        """
        resp = self._cc._delete("/ops/review/%s" % self.network_camera_id)

        for k in self._sub_keys:
            delattr(self, k)
        self._sub_keys = None
        self.connection = None

    ##
    #  __init__
    ##
    def __init__(self, connection, netcam_dict):
        """
        create a CogniacNetworkCamera

        This is not normally called directly by users, instead use:
        CogniacConnection.create_application() or
        CogniacApplication.create()
        """
        self._cc = connection
        self._app_keys = netcam_dict.keys()
        for k, v in netcam_dict.items():
            super(CogniacNetworkCamera, self).__setattr__(k, v)

    def __setattr__(self, name, value):
        if name in ['network_camera_id', 'created_at', 'created_by', 'modified_at', 'modified_by']:
            raise AttributeError("%s is immutable" % name)
        if name in ['name', 'description', 'active', 'url']:
            data = {name: value}
            resp = self._cc._post("/networkCameras/%s" % self.network_camera_id, json=data)
            for k, v in resp.json().items():
                super(CogniacNetworkCamera, self).__setattr__(k, v)
            return
        super(CogniacNetworkCamera, self).__setattr__(name, value)

    def __str__(self):
        s = "%s" % (self.network_camera_id)
        return s.encode(sys.stdout.encoding)

    def __repr__(self):
        s = "%s" % (self.network_camera_id)
        return s.encode(sys.stdout.encoding)
