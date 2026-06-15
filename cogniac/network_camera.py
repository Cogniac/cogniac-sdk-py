"""
Cogniac Network Camera Object Client

Copyright (C) 2019 Cogniac Corporation
"""

from .common import retry, stop_after_attempt, wait_exponential, retry_if_exception, server_error

camera_model_keys = ['last_pose_change_timestamp',
                     'resolution_h_px', 'resolution_v_px',
                     'pixel_h_um', 'pixel_v_um',
                     'focal_length_h_mm', 'focal_length_v_mm',
                     'skew', 'ch_px', 'cv_px',
                     'radial_distortion_coefficients',
                     'tangential_distortion_coefficients',
                     'pitch', 'yaw', 'roll',
                     'tx_m', 'ty_m', 'tz_m',
                     'origin_x', 'origin_y',
                     'x_axis_x', 'x_axis_y',
                     'y_axis_x', 'y_axis_y',
                     'z_axis_x', 'z_axis_y']

mutable_keys = ['url', 'current_IP', 'camera_name', 'description',
                'active', 'lat', 'lon', 'hae', 'alt_subject_uid', 'custom_configuration'] + camera_model_keys

immutable_keys = ['network_camera_id', 'created_at',
                  'created_by', 'modified_at', 'modified_by']


##
#  Cogniac Network Camera
##
class CogniacNetworkCamera(object):
    """
    CogniacNetworkCamera
    """

    ##
    #  create
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def create(cls,
               connection,
               name,
               url,
               description=None,
               active=True,
               discovered_by=None,
               spec_version_major=None,
               spec_version_minor=None,
               device_mode=None,
               IP_config_options=None,
               IP_config_current=None,
               current_IP=None,
               current_subnet_mask=None,
               default_gateway=None,
               mac_address=None,
               model_name=None,
               serial_number=None,
               device_version=None,
               manufacturer_name=None,
               manufacturer_info=None,
               user_defined_name=None):

        """
        Create a network camera object

        connnection (CogniacConnection): Authenticated CogniacConnection object
        name (String):                   Name of new camera
        url(String):                     url of the network camera
        description (String):            Optional description of the camera
        active(Boolean):                 True to indicate system should process the images
        discovered_by (String):          cogniac edgeflow_id of the Edgeflow that discovered this camera

        plus device dictionaries returned from GVCP discovery
        """
        data = dict(camera_name=name)
        data['url'] = url
        if active:
            data['active'] = 1
        else:
            data['active'] = 0

        if description:
            data['description'] = description

        if discovered_by:
            data['discovered_by'] = discovered_by

        if spec_version_major:
            data['spec_version_major'] = str(spec_version_major)
        if spec_version_minor:
            data['spec_version_minor'] = str(spec_version_minor)

        if device_mode:
            data['device_mode'] = str(device_mode)

        if IP_config_options:
            data['IP_config_options'] = str(IP_config_options)
        if IP_config_current:
            data['IP_config_current'] = str(IP_config_current)
        if current_IP:
            data['current_IP'] = current_IP
        if current_subnet_mask:
            data['current_subnet_mask'] = current_subnet_mask
        if default_gateway:
            data['default_gateway'] = default_gateway
        if mac_address:
            data['mac_address'] = mac_address

        if model_name:
            data['model_name'] = model_name

        if serial_number:
            data['serial_number'] = str(serial_number)

        if device_version:
            data['device_version'] = device_version

        if manufacturer_name:
            data['manufacturer_name'] = manufacturer_name

        if manufacturer_info:
            data['manufacturer_info'] = manufacturer_info

        if user_defined_name:
            data['user_defined_name'] = user_defined_name

        resp = connection._post("/1/networkCameras", json=data)
        return CogniacNetworkCamera(connection, resp.json())

    ##
    #  get
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def get(cls,
            connection,
            network_camera_id):
        """
        get single network camera
        connnection (CogniacConnection): Authenticated CogniacConnection object
        network_camera_id (String): the netcam id of the Cogniac NetCam object
        returns CogniacNetworkCamera object
        """
        resp = connection._get("/1/networkCameras/%s" % network_camera_id)
        return CogniacNetworkCamera(connection, resp.json())

    ##
    #  get_all
    ##
    @classmethod
    def get_all(cls, connection):
        """
        return all CogniacNetworkcamera belonging to the currently authenticated tenant

        connnection (CogniacConnection):     Authenticated CogniacConnection object
        """
        resp = connection._get('/1/tenants/%s/networkCameras' % connection.tenant.tenant_id)
        netcams = resp.json()['data']
        return [CogniacNetworkCamera(connection, netcam) for netcam in netcams]

    ##
    #  update
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def update(self, body=None, **kwargs):
        """
        Update this network camera's mutable fields and return the updated JSON.

        body (dict):  fields to update

        Deprecated: passing per-field keyword arguments (e.g. update(url=...)) is
        still accepted for backward compatibility — they are merged into the body —
        but emits a DeprecationWarning. Prefer passing a body dict.

        See POST /1/networkCameras/{network_camera_id}.
        """
        if kwargs:
            import warnings
            warnings.warn("CogniacNetworkCamera.update(**kwargs) is deprecated; "
                          "pass a body dict instead.", DeprecationWarning, stacklevel=2)
            body = dict(body or {}, **kwargs)
        resp = self._cc._post("/1/networkCameras/%s" % self.network_camera_id, json=body or {})
        result = resp.json()
        for k, v in result.items():
            super(CogniacNetworkCamera, self).__setattr__(k, v)
        return result

    ##
    #  delete
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def delete(self):
        """
        Delete the op review result.
        """
        self._cc._delete("/1/networkCameras/%s" % self.network_camera_id)

        for k in self._cam_keys:
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
        CogniacNetworkCamera.create()
        """
        self._cc = connection
        self._cam_keys = netcam_dict.keys()

        for k, v in netcam_dict.items():
            super(CogniacNetworkCamera, self).__setattr__(k, v)

    def __setattr__(self, name, value):
        if name in immutable_keys:
            raise AttributeError("%s is immutable" % name)

        if name in mutable_keys:
            data = {name: value}
            resp = self._cc._post("/1/networkCameras/%s" % self.network_camera_id, json=data)

            for k, v in resp.json().items():
                super(CogniacNetworkCamera, self).__setattr__(k, v)

            return

        super(CogniacNetworkCamera, self).__setattr__(name, value)

    def __str__(self):
        return "%s (%s)" % (self.camera_name, self.network_camera_id)

    def __repr__(self):
        return self.__str__()

    ##
    #  genicam
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def genicam(self):
        """
        Return the GenICam XML for this network camera.

        See GET /1/networkCameras/{camera_id}/genicam.
        """
        resp = self._cc._get("/1/networkCameras/%s/genicam" % self.network_camera_id)
        return resp.text

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def upload_genicam(self, filename):
        """
        Upload a GenICam XML file for this network camera.

        filename (str):  path to a local GenICam XML file

        See POST /1/networkCameras/{camera_id}/genicam.
        """
        with open(filename, 'rb') as f:
            resp = self._cc._post("/1/networkCameras/%s/genicam" % self.network_camera_id,
                                 files={'file': f})
        try:
            return resp.json()
        except Exception:
            return None
