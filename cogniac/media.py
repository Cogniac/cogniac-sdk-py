"""
CogniacMedia Object Client

Copyright (C) 2016 Cogniac Corporation
"""

from hashlib import md5
from retrying import retry
from .common import *
from os import stat, fstat, path, SEEK_END
import platform
from time import time

platform_system = platform.system()

immutable_keys = ['frame', 'video', 'media_id', 'size', 'network_camera_id', 'original_url', 'image_width', 'filename', 'original_landing_url', 'uploaded_by_user', 'media_timestamp', 'media_url', 'status', 'hash', 'external_media_id', 'author_profile_url', 'media_src', 'parent_media_id',  'media_resize_urls', 'license', 'tenant_id', 'created_at', 'author', 'public', 'image_height', 'media_format', 'title', 'domain_unit']

mutable_keys =['set_assignment', 'force_set', 'meta_tags', "custom_data"]


def file_creation_time(path_to_file):
    """
    Try to get the date that a file was created, falling back to when it was
    last modified if that isn't possible.
    See http://stackoverflow.com/a/39501288/1709587 for explanation.
    """
    if platform_system == 'Windows':
        return path.getctime(path_to_file)
    else:
        fstat = stat(path_to_file)
        try:
            return fstat.st_birthtime
        except AttributeError:
            # We're probably on Linux. No easy way to get creation dates here,
            # so we'll settle for when its content was last modified.
            return fstat.st_mtime

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
        resp = connection._get("/1/media/%s" % media_id)

        return CogniacMedia(connection, resp.json())

    @classmethod
    def search(cls, connection, md5=None, filename=None, external_media_id=None, domain_unit=None, limit=None):
        """
        Search for a CogniacMedia item in current tenant by md5, filename, or external_media_id.

        connnection (CogniacConnection):     Authenticated CogniacConnection object
        md5 (String):                        MD5 of media item
        filename (String):                   Original filename of media item
        external_media_id (String):          Customer specified unique ID

        Only one of md5, filename, or external_media_id must be specified

        returns list of CogniacMedia objects that match the query parameters
        """

        if md5 is not None:
            assert((filename is None) & (external_media_id is None) & (domain_unit is None))
            query = "md5=%s" % md5
        elif filename is not None:
            assert((md5 is None) & (external_media_id is None) & (domain_unit is None))
            query = "filename=%s" % filename
        elif external_media_id is not None:
            assert((md5 is None) & (filename is None) & (domain_unit is None))
            query = "external_media_id=%s" % external_media_id
        else:
            assert((md5 is None) & (filename is None) & (external_media_id is None))
            query = "domain_unit=%s" % domain_unit

        def get_next(last_key=None):
            query_limit = limit if limit and limit < 100 else 100
            url = "/1/media/all/search?%s&limit=%s" % (query, query_limit)
            if last_key:
                url += "&last_key=%s" % (last_key)
            resp = connection._get(url)
            return resp.json()

        matches = []
        last_key = None
        while True:
            resp = get_next(last_key=last_key)
            last_key = resp.get('last_key')
            data = [CogniacMedia(connection, m) for m in resp['data']]
            for datum in data:
                matches.append(datum)
                if limit and len(matches) == limit:
                    return matches
            if not last_key:
                break

        return matches

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
            resp = self._cc._post("/1/media/%s" % self.media_id, json=data)
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
               set_assignment=None,
               external_media_id=None,
               original_url=None,
               original_landing_url=None,
               license=None,
               author_profile_url=None,
               author=None,
               title=None,
               media_timestamp=None,
               domain_unit=None,
               trigger_id=None,
               sequence_ix=None,
               custom_data=None,
               fp=None):
        """
        Create a new CogniacMedia object and upload the media to the Cogniac System.

        connnection (CogniacConnection):  Authenticated CogniacConnection object
        filename (str):                   Local filename or http/s URL of image or video media file
        meta_tags ([str]):                Optional list of arbitrary strings to associate with the media
        force_set (str):                  [DEPRECATED] Optionally force the media into the 'training', 'validation' or 'test' sets
        set_assignment (str):             Optionally force the media into the 'training', 'validation' or 'test' sets
        external_media_id (str):          Optional arbitrary external id for this media
        original_url(str):                Optional source url for this media
        original_landing_url (str):       Optional source landing url for this media
        license (str):                    Optional copyright licensing info for this media
        author_profile_url (str):         Optional media author url
        author (str):                     Optional author name
        title (str):                      Optional media title
        media_timestamp (float):          Optional actual timestamp of media creation/occurance time
        domain_unit (str):                Optional domain id (e.g. serial number) for set assignment grouping.
                                          Media with the same domain_unit will always be assigned to the same
                                          training or validation set. Set this to avoid overfitting when you have
                                          multiple images of the same thing or almost the same thing.
        trigger_id (str):                 Unique trigger identifier leading to a media sequence containing this media
        sequence_ix (str):                The index of this media within a triggered sequence
        custom_data (str):                Opaque user-specified data associated with this media; limited to 32KB
        fp (file):                        A '.read()'-supporting file-like object from which to acquire
                                          the media instead of reading the media from the specified filename.
        """

        args = dict()
        if meta_tags is not None:
            args['meta_tags'] = meta_tags
        if force_set is not None:
            args['force_set'] = force_set
        if set_assignment is not None:
            args['set_assignment'] = set_assignment
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
        if media_timestamp is not None:
            args['media_timestamp'] = media_timestamp
        if domain_unit is not None:
            args['domain_unit'] = domain_unit
        if trigger_id is not None:
            args['trigger_id'] = trigger_id
        if sequence_ix is not None:
            args['sequence_ix'] = sequence_ix
        if custom_data is not None:
            args['custom_data'] = custom_data

        if filename.startswith('http'):
            args['source_url'] = filename
        else:
            if 'media_timestamp' not in args:
                if fp is None:
                    # set the unspecified media timestamp to the earliest file time we have
                    args['media_timestamp'] = file_creation_time(filename)
                else:
                    args['media_timestamp'] = time()

            if fp is None:
                fsize = stat(filename).st_size
                # use the multipart interface for large files
            else:
                fp.seek(0, SEEK_END) # most reliable way of finding file size.
                fsize = fp.tell()
                fp.seek(0)

            if fsize > 12 * 1024 * 1024:
                return CogniacMedia._create_multipart(connection, filename, fp, fsize, args)

        @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
        def upload():
            if filename.startswith('http'):
                files = None
            elif fp is not None:
                fp.seek(0)  # for the retry win
                files = {filename: fp}
            else:
                files = {filename: open(filename, 'rb')}
            resp = connection._post("/1/media", data=args, files=files)
            return resp

        resp = upload()
        return CogniacMedia(connection, resp.json())

    @classmethod
    def _create_multipart(cls, connection, filename, mfp, filesize, args):
        """
        upload via the multipart api
        """
        def md5_hexdigest(fp):
            """
            return the md5 hexdigest of a potentially very large file
            """
            md = md5()
            while True:
                block = fp.read(8*1024*1024)
                if not block:
                    return md.hexdigest()
                md.update(block)

        if mfp is None:
            mfp = open(filename, 'rb')
        else:
            mfp.seek(0)

        md5hash = md5_hexdigest(mfp)

        @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
        def post_data(data):
            resp = connection._post("/1/media/resumable", json=data)
            return resp.json()

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
            resp = connection._post("/1/media/resumable", data=data, files=files)
            return resp.json()

        idx = 1
        mfp.seek(0)
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

    def delete(self):
        """
        delete the media object
        """
        self._cc._delete("/1/media/%s" % self.media_id)
        self.__dict__.clear()

    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def download(self, filep=None, timeout=60):
        """
        Download the media file and return as a string or write to a file.

        filep:   open file object to store downloaded media
                 If filep is None: return the media as a string

        timeout: timeout in seconds
        """
        url = self.media_url

        stream = False
        if filep is not None:
            stream = True  # user requests output to file so stream potentially large results
        resp = self._cc._get(url, stream=stream, timeout=timeout)
        raise_errors(resp)

        if filep is None:  # return response all at once
            return resp.content
        else:
            filep.seek(0)  # in case of retries

        # write response out to file
        for chunk in resp.iter_content(chunk_size=512 * 1024):
            if chunk:  # filter out keep-alive new chunks
                filep.write(chunk)
        filep.close()

    ##
    #  detections
    ##
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def detections(self, wait_capture_id=None):
        """
        return a list of detection dictionaries as follows for the specified media_id and this subject
        wait_capture_id (str):    capture_id from previous subject associate_media call that had enable_wait_result=True
                                  This operation with block and return all applications detections resulting from capture_id
                                  when available.

        Returns:

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

        url = "/1/media/%s/detections" % (self.media_id)

        if wait_capture_id is not None:
            url += "?wait_capture_id=%s" % wait_capture_id

        resp = self._cc._get(url)
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
        consensus		'True', 'False', or None
                        'True' if there is consensus that the subject is associated with the media
                            (Media will be used as a positive training example of the subject)
                        'False' if there is consensus that the subject is not associated w/the media
                            (Media will be used as a negative training example of the subject.)
                         None if if there is not enough evidence to reach consensus
                         Some application types only support 'True' or None.
                         }
        """
        resp = self._cc._get("/1/media/%s/subjects" % (self.media_id))
        return resp.json()['data']
