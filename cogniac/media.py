"""
CogniacMedia Object Client

Copyright (C) 2016 Cogniac Corporation
"""

from hashlib import md5
from retrying import retry
from common import *
from os import stat
import requests

immutable_keys = ['frame', 'video', 'media_id', 'size', 'network_camera_id', 'original_url', 'image_width', 'filename', 'original_landing_url', 'uploaded_by_user', 'media_timestamp', 'media_url', 'status', 'hash', 'external_media_id', 'author_profile_url', 'media_src', 'parent_media_id',  'media_resize_urls', 'license', 'tenant_id', 'created_at', 'author', 'public', 'image_height', 'media_format', 'title']

mutable_keys =['force_set', 'meta_tags']

##
#  CogniacMedia
##
class CogniacMedia(object):
    """
    CogniacMedia objects contain metadata for media files that has been input into the Cogniac System.
    New CogniacMedia can be created by specifying a local filename containing a still image or video.
    Existing CogniacMedia can be retrieved by media_id.
    """

    @classmethod
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def get(cls, connection, media_id):
        """
        return a CogniacMedia object for an existing media item

        connnection (CogniacConnection):     Authenticated CogniacConnection object
        media_id (String):                   The media_id of the Cogniac Media item to return
        """
        resp = connection.session.get(url_prefix + "/media/%s" % media_id, timeout=connection.timeout)
        raise_errors(resp)

        return CogniacMedia(connection, resp.json())

    def __init__(self, connection, media_dict):
        """
        create a CogniacMedia

        This is not normally called directly by users, instead use:
        CogniacConnection.create_media() or
        CogniacMedia.create()
        """
        self._cc = connection
        self._media_keys = media_dict.keys()
        for k, v in media_dict.items():
            super(CogniacMedia, self).__setattr__(k, v)

    def __str__(self):
        return "%s" % self.media_id

    def __setattr__(self, name, value):
        if name in immutable_keys:
            raise AttributeError("%s is immutable" % name)
        if name in mutable_keys:
            data = {name: value}
            resp = self._cc.session.post(url_prefix + "/media/%s" % self.media_id, json=data, timeout=self._cc.timeout)
            raise_errors(resp)
            for k, v in resp.json().items():
                super(CogniacMedia, self).__setattr__(k, v)
            return
        super(CogniacMedia, self).__setattr__(name, value)


    @classmethod
    def create(cls,
               connection,
               filename,
               meta_tags=None,
               force_set=None,
               external_media_id=None,
               original_url=None,
               original_landing_url=None,
               license=None,
               author_profile_url=None,
               author=None,
               title=None):
        """
        Create a new CogniacMedia object and upload the media to the Cogniac System.

        connnection (CogniacConnection):  Authenticated CogniacConnection object
        filename (str):                   Local filename of image or video media file
        meta_tags ([str]):                Optional list of arbitrary strings to associate with the media
        force_set (str):                  Optionally force the media into the 'training', 'validation' or 'test' sets
        external_media_id (str):          Optional arbitrary external id for this media
        original_url(str):                Optional source url for this media
        original_landing_url (str):       Optional source landing url for this media
        license (str):                    Optional copyright licensing info for this media
        author_profile_url (str):         Optional media author url
        author (str):                     Optional author name
        title (str):                      Optional media title
        """

        args = dict()
        if meta_tags is not None:
            args['meta_tags'] = meta_tags
        if force_set is not None:
            args['force_set'] = force_set
        if external_media_id is not None:
            args['external_media_id'] = external_media_id
        if original_url is not None:
            args['original_url'] = original_url
        if original_landing_url is not None:
            args['original_landing_url'] = original_landing_url
        if license is not None:
            args['license'] = license
        if author_profile_url is not None:
            args['author_profile_url'] = author_profile_url
        if author is not None:
            args['author'] = author
        if title is not None:
            args['title'] = title

        if stat(filename).st_size > 12 * 1024 * 1024:
            # use the multipart interface for large files
            return CogniacMedia._create_multipart(connection, filename, args)

        @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
        def upload():
            files = {'file': open(filename, 'rb')}
            resp = connection.session.post(url_prefix+"/media", data=args, files=files, timeout=connection.timeout)
            raise_errors(resp)
            return resp

        resp = upload()
        return CogniacMedia(connection, resp.json())

    @classmethod
    def _create_multipart(cls, connection, filename, args):
        """
        upload via the multipart api
        """
        def md5_hexdigest():
            """
            return the md5 hexdigest of a potentially very large file
            """
            md = md5()
            fp = open(filename)
            while True:
                block = fp.read(8*1024*1024)
                if not block:
                    return md.hexdigest()
                md.update(block)

        md5hash = md5_hexdigest()

        @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
        def post_data(data):
            resp = connection.session.post(url_prefix + "/media/resumable", json=data, timeout=connection.timeout)
            raise_errors(resp)
            return resp.json()

        filesize = stat(filename).st_size

        data = {'upload_phase': 'start',
                'file_size':    filesize,
                'filename':     filename,
                'md5':          md5hash}

        rdata = post_data(data)
        upload_session_id = rdata['upload_session_id']
        chunk_size = rdata['chunk_size']

        @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
        def upload_chunk(chunk, chunk_no, upload_session_id):

            data = {'upload_phase':        'transfer',
                    'upload_session_id':   upload_session_id,
                    'video_file_chunk_no': chunk_no}

            files = {'file': chunk}
            resp = connection.session.post(url_prefix + "/media/resumable", data=data, files=files, timeout=connection.timeout)
            raise_errors(resp)
            return resp.json()

        mfp = open(filename, 'r')
        idx = 1
        while True:
            chunk = mfp.read(chunk_size)
            if not chunk:
                break
            upload_chunk(chunk, idx, upload_session_id)
            idx += 1

        # perform the final finihs phase post with the user args
        data = {'upload_phase':      'finish',
                'upload_session_id': upload_session_id}
        data.update(args)  # add user arg
        rdata = post_data(data)
        return CogniacMedia(connection, rdata)

    def download(self, filep=None, resize=None):
        """
        Download the original or resized media file and return as a string or write to a file.

        filep:   open file object to store downloaded media
                 If filep is None: return the media as a string

        resize:  resize size in pixels (currently 454, 750, or 1334)
                 if resize is None: return original media, not resized media
                 resize is only applicable to still images, not video media.
        """
        url = self.media_url
        if resize is not None and self.resize_urls is not None:
            if resize in self.resize_urls:
                url = self.resize_urls[resize]

        stream = False
        if filep is not None:
            stream = True  # user requests output to file so stream potentially large results

        resp = requests.get(url, stream=stream, timeout=self._cc.timeout)
        raise_errors(resp)

        if filep is None:  # return response all at once
            return resp.content

        # write response out to file
        for chunk in resp.iter_content(chunk_size=512 * 1024):
            if chunk:  # filter out keep-alive new chunks
                filep.write(chunk)
        filep.close()


    ##
    #  detections
    ##
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def detections(self):
        """
        return a list of detection dictionaries as follows for the specified media_id and this subject

        detection_id:     internal detection_id
        user_id:          a user_id if this was from a user
        model_id:         a model_id if this was from an app w/model
        app_id:           an app_id if this was from an app
        uncal_prob:       the raw uncalibrated user or model confidence (if any)
        timestamp:        the time of this detection
        prev_prob:        subject-media probability before this detection (if any)
        probability:      the resulting probability after this detection
        app_data_type     Optional type of extra app-specific data
        app_data          Optional extra app-specific data
        """
        url = url_prefix + "/media/%s/detections" % (self.media_id)
        resp = self._cc.session.get(url, timeout=self._cc.timeout)
        raise_errors(resp)
        return resp.json()['detections']


    ##
    #  subjects
    ##
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def subjects(self):
        """
        return a list of subjects as follows for the specified media_id:

        {"media":       {partial or full media item},

         "subject:"     {

        media_id        the media_id
        subject_uid		the subject_uid
        probability		current assessment of the probability in [0,1] that the subject_uid is associated with the media_id
                        1 = definitely associated
                        0 = definitely NOT associated
                        0.5 ~= uncertain association
        timestamp		time of last update
        app_data_type	optional app data type if applicable
        app_data        optional app data if applicable
        consensus		'True', 'False', or 'Uncertain', or None
                        'True' if there is consensus that the subject is associated with the media
                            (Media will be used as a positive training example of the subject)
                        'False' if there is consensus that the subject is not associated w/the media
                            (Media will be used as a negative training example of the subject.)
                        'Uncertain' if there is consensus that the association between the media and subject is ambiguous
                         None if if there is not enough evidence to reach consensus
                         Some application types only support 'True' or None.
                         }
        """
        url = url_prefix + "/media/%s/subjects" % (self.media_id)
        resp = self._cc.session.get(url, timeout=self._cc.timeout)
        raise_errors(resp)
        return resp.json()['data']
