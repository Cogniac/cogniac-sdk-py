"""
Cogniac Network Camera Object Client

Copyright (C) 2019 Cogniac Corporation
"""

from retrying import retry
import sys
from common import server_error

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
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def create(cls,
               connection,
               name,
               description=None,
               active=True,
               url=None):

        """
        Create a network camera object

        connnection (CogniacConnection): Authenticated CogniacConnection object
        """
        data = dict(camera_name=name)
        if active:
            data['active'] = 1
        else:
            data['active'] = 0

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
        return all CogniacNetworkcamera belonging to the currently authenticated tenant

        connnection (CogniacConnection):     Authenticated CogniacConnection object
        """
        resp = connection._get('/tenants/%s/networkCameras' % connection.tenant.tenant_id)
        netcams = resp.json()['data']
        return [CogniacNetworkCamera(connection, netcam) for netcam in netcams]

    ##
    #  post
    ##
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def update(self,
               camera_name=None,
               description=None,
               active=None,
               lat=None,
               lon=None,
               hae=None,
               last_pose_change_timestamp=None,
               resolution_h_px=None,
               resolution_v_px=None,
               pixel_h_um=None,
               pixel_v_um=None,
               focal_length_h_mm=None,
               focal_length_v_mm=None,
               skew=None,
               ch_px=None,
               cv_px=None,
               radial_distortion_coefficients=None,
               tangential_distortion_coefficients=None,
               pitch=None,
               yaw=None,
               roll=None,
               tx_m=None,
               ty_m=None,
               tz_m=None,
               origin_x=None,
               origin_y=None,
               x_axis_x=None,
               x_axis_y=None,
               y_axis_x=None,
               y_axis_y=None,
               z_axis_x=None,
               z_axis_y=None):
        """
        update single network camera's camera model
        connnection (CogniacConnection): Authenticated CogniacConnection object
        network_camera_id (String): the netcam id of the Cogniac NetCam object
        returns CogniacNetworkCamera object
        """
        data = {}

        if camera_name is not None:
            data['camera_name'] = camera_name
        if description is not None:
            data['description'] = description
        if active is not None:
            data['active'] = active
        if lat is not None:
            data['lat'] = lat
        if lon is not None:
            data['lon'] = lon
        if hae is not None:
            data['hae'] = hae

        # pose/model related
        if last_pose_change_timestamp is not None:
            data['last_pose_change_timestamp'] = last_pose_change_timestamp

        if resolution_h_px is not None:
            data['resolution_h_px'] = resolution_h_px
        if resolution_v_px is not None:
            data['resolution_v_px'] = resolution_v_px
        if pixel_h_um is not None:
            data['pixel_h_um'] = pixel_h_um
        if pixel_v_um is not None:
            data['pixel_v_um'] = pixel_v_um
        if focal_length_h_mm is not None:
            data['focal_length_h_mm'] = focal_length_h_mm
        if focal_length_v_mm is not None:
            data['focal_length_v_mm'] = focal_length_v_mm

        if skew is not None:
            data['skew'] = skew
        if ch_px is not None:
            data['ch_px'] = ch_px
        if cv_px is not None:
            data['cv_px'] = cv_px

        if radial_distortion_coefficients is not None:
            data['radial_distortion_coefficients'] = radial_distortion_coefficients
        if tangential_distortion_coefficients is not None:
            data['tangential_distortion_coefficients'] = tangential_distortion_coefficients
        if pitch is not None:
            data['pitch'] = pitch
        if yaw is not None:
            data['yaw'] = yaw
        if roll is not None:
            data['roll'] = roll

        if tx_m is not None:
            data['tx_m'] = tx_m
        if ty_m is not None:
            data['ty_m'] = ty_m
        if tz_m is not None:
            data['tz_m'] = tz_m

        if origin_x is not None:
            data['origin_x'] = origin_x
        if origin_y is not None:
            data['origin_y'] = origin_y

        if x_axis_x is not None:
            data['x_axis_x'] = x_axis_x
        if x_axis_y is not None:
            data['x_axis_y'] = x_axis_y
        if y_axis_x is not None:
            data['y_axis_x'] = y_axis_x
        if y_axis_y is not None:
            data['y_axis_y'] = y_axis_y
        if z_axis_x is not None:
            data['z_axis_x'] = z_axis_x
        if z_axis_y is not None:
            data['z_axis_y'] = z_axis_y

        resp = self._cc._post("/networkCameras/%s" % self.network_camera_id, json=data)
        return CogniacNetworkCamera(self._cc, resp.json())

    ##
    #  delete
    ##
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def delete(self):
        """
        Delete the op review result.
        """
        resp = self._cc._delete("/networkCameras/%s" % self.network_camera_id)

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
        if name in ['network_camera_id', 'created_at', 'created_by', 'modified_at', 'modified_by']:
            raise AttributeError("%s is immutable" % name)
        if name in ['camera_name', 'description', 'active', 'lat', 'lon', 'hae'] + camera_model_keys:
            data = {name: value}
            print "\n====", data
            resp = self._cc._post("/networkCameras/%s" % self.network_camera_id, json=data)
            for k, v in resp.json().items():
                super(CogniacNetworkCamera, self).__setattr__(k, v)
            return
        super(CogniacNetworkCamera, self).__setattr__(name, value)

    def __str__(self):
        s = "%s (%s)" % (self.camera_name, self.network_camera_id)
        return s.encode(sys.stdout.encoding)

    def __repr__(self):
        s = "%s (%s)" % (self.camera_name, self.network_camera_id)
        return s.encode(sys.stdout.encoding)
