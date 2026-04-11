"""
Async CogniacMedia Object Client

Copyright (C) 2016-2022 Cogniac Corporation
"""

from .common import retry, stop_after_attempt, wait_exponential, retry_if_exception, server_error, raise_errors
from .media import file_creation_time
from hashlib import md5
from os import stat, fstat, path, SEEK_END
from urllib.parse import quote
from time import time


immutable_keys = ['frame', 'video', 'media_id', 'size', 'network_camera_id',
                  'original_url', 'image_width', 'filename', 'original_landing_url',
                  'uploaded_by_user', 'media_timestamp', 'media_url', 'status', 'hash',
                  'external_media_id', 'author_profile_url', 'media_src', 'parent_media_id',
                  'media_resize_urls', 'license', 'tenant_id', 'created_at', 'author',
                  'public', 'image_height', 'media_format', 'title', 'domain_unit']

mutable_keys = ['set_assignment', 'force_set', 'meta_tags', 'custom_data']


class AsyncCogniacMedia(object):
    """
    AsyncCogniacMedia
    Async version of CogniacMedia.

    CogniacMedia objects contain metadata for media files input into the Cogniac System.
    New media can be created by specifying a local filename containing an image or video.
    Existing media can be retrieved by media_id.

    Use the async set() method to update mutable attributes.
    """

    ##
    #  get
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def get(cls, connection, media_id):
        """
        Return an AsyncCogniacMedia object for an existing media item.

        connection (AsyncCogniacConnection): Authenticated AsyncCogniacConnection object
        media_id (String):                   The media_id of the Cogniac Media item to return
        """
        resp = await connection._get("/1/media/%s" % media_id)
        return AsyncCogniacMedia(connection, resp.json())

    ##
    #  search
    ##
    @classmethod
    async def search(cls, connection, md5=None, filename=None,
                     external_media_id=None, domain_unit=None, limit=None):
        """
        Search for media items in current tenant.

        connection (AsyncCogniacConnection): Authenticated AsyncCogniacConnection object
        md5 (String):                        MD5 of media item
        filename (String):                   Original filename of media item
        external_media_id (String):          Customer specified unique ID
        domain_unit (String):                Domain unit identifier

        Only one of md5, filename, external_media_id, or domain_unit must be specified.

        Returns list of AsyncCogniacMedia objects matching the query.
        """
        if md5 is not None:
            assert((filename is None) & (external_media_id is None) & (domain_unit is None))
            query = "md5=%s" % md5
        elif filename is not None:
            assert((md5 is None) & (external_media_id is None) & (domain_unit is None))
            query = "filename=%s" % quote(filename)
        elif external_media_id is not None:
            assert((md5 is None) & (filename is None) & (domain_unit is None))
            query = "external_media_id=%s" % external_media_id
        else:
            assert((md5 is None) & (filename is None) & (external_media_id is None))
            query = "domain_unit=%s" % domain_unit

        @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
        async def get_next(last_key=None):
            query_limit = limit if limit and limit < 100 else 100
            url = "/1/media/all/search?%s&limit=%s" % (query, query_limit)
            if last_key:
                url += "&last_key=%s" % (last_key)
            resp = await connection._get(url)
            return resp.json()

        matches = []
        last_key = None
        while True:
            resp = await get_next(last_key=last_key)
            last_key = resp.get('last_key')
            data = [AsyncCogniacMedia(connection, m) for m in resp['data']]
            for datum in data:
                matches.append(datum)
                if limit and len(matches) == limit:
                    return matches
            if not last_key:
                break

        return matches

    ##
    #  __init__
    ##
    def __init__(self, connection, media_dict):
        """
        Create an AsyncCogniacMedia

        This is not normally called directly by users, instead use:
        AsyncCogniacMedia.create() or AsyncCogniacMedia.get()
        """
        self._cc = connection
        self._media_keys = media_dict.keys()
        for k, v in media_dict.items():
            super(AsyncCogniacMedia, self).__setattr__(k, v)

    def __str__(self):
        return "%s" % self.media_id

    def __repr__(self):
        return self.__str__()

    def __setattr__(self, name, value):
        if name in immutable_keys:
            raise AttributeError("%s is immutable" % name)
        super(AsyncCogniacMedia, self).__setattr__(name, value)

    ##
    #  set
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def set(self, **kwargs):
        """
        Update mutable media attributes via a single POST call.

        Accepted keys: set_assignment, force_set, meta_tags, custom_data

        Example:
            await media.set(meta_tags=["tag1", "tag2"])
        """
        for key in kwargs:
            if key in immutable_keys:
                raise AttributeError("%s is immutable" % key)
            if key not in mutable_keys:
                raise AttributeError("%s is not a recognized mutable attribute" % key)

        resp = await self._cc._post("/1/media/%s" % self.media_id, json=kwargs)
        for k, v in resp.json().items():
            super(AsyncCogniacMedia, self).__setattr__(k, v)

    ##
    #  create
    ##
    @classmethod
    async def create(cls,
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
        Create a new AsyncCogniacMedia object and upload the media to the Cogniac System.

        connection (AsyncCogniacConnection): Authenticated AsyncCogniacConnection object
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
        media_timestamp (float):          Optional actual timestamp of media creation/occurrence time
        domain_unit (str):                Optional domain id for set assignment grouping
        trigger_id (str):                 Unique trigger identifier
        sequence_ix (str):                Index of this media within a triggered sequence
        custom_data (str):                Opaque user-specified data (limited to 32KB)
        fp (file):                        A '.read()'-supporting file-like object
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
                    args['media_timestamp'] = file_creation_time(filename)
                else:
                    args['media_timestamp'] = time()

            if fp is None:
                fsize = stat(filename).st_size
            else:
                fp.seek(0, SEEK_END)
                fsize = fp.tell()
                fp.seek(0)

            if fsize > 12 * 1024 * 1024:
                return await AsyncCogniacMedia._create_multipart(connection, filename, fp, fsize, args)

        @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
        async def upload():
            if filename.startswith('http'):
                files = None
            elif fp is not None:
                fp.seek(0)  # for the retry win
                files = {filename: fp}
            else:
                files = {filename: open(filename, 'rb')}
            resp = await connection._post("/1/media", data=args, files=files)
            return resp

        resp = await upload()
        return AsyncCogniacMedia(connection, resp.json())

    ##
    #  _create_multipart
    ##
    @classmethod
    async def _create_multipart(cls, connection, filename, mfp, filesize, args):
        """
        Upload via the multipart resumable API.
        """
        def md5_hexdigest(fp):
            """
            Return the md5 hexdigest of a potentially very large file.
            """
            md = md5()
            while True:
                block = fp.read(8 * 1024 * 1024)
                if not block:
                    return md.hexdigest()
                md.update(block)

        if mfp is None:
            mfp = open(filename, 'rb')
        else:
            mfp.seek(0)

        md5hash = md5_hexdigest(mfp)

        @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
        async def post_data(data):
            resp = await connection._post("/1/media/resumable", json=data)
            return resp.json()

        data = {'upload_phase': 'start',
                'file_size':    filesize,
                'filename':     filename,
                'md5':          md5hash}

        rdata = await post_data(data)
        upload_session_id = rdata['upload_session_id']
        chunk_size = rdata['chunk_size']

        @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
        async def upload_chunk(chunk, chunk_no, upload_session_id):
            data = {'upload_phase':        'transfer',
                    'upload_session_id':   upload_session_id,
                    'video_file_chunk_no': chunk_no}
            files = {'file': chunk}
            resp = await connection._post("/1/media/resumable", data=data, files=files)
            return resp.json()

        idx = 1
        mfp.seek(0)
        while True:
            chunk = mfp.read(chunk_size)
            if not chunk:
                break
            await upload_chunk(chunk, idx, upload_session_id)
            idx += 1

        # perform the final finish phase post with the user args
        data = {'upload_phase':      'finish',
                'upload_session_id': upload_session_id}
        data.update(args)
        rdata = await post_data(data)
        return AsyncCogniacMedia(connection, rdata)

    ##
    #  delete
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def delete(self):
        """
        Delete the media object.
        """
        await self._cc._delete("/1/media/%s" % self.media_id)
        self.__dict__.clear()

    ##
    #  download
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def download(self, filep=None, timeout=60):
        """
        Download the media file and return as bytes or write to a file.

        filep:   open file object to store downloaded media
                 If filep is None: return the media as bytes
        timeout: timeout in seconds
        """
        url = self.media_url

        resp = await self._cc._get(url, timeout=timeout)
        raise_errors(resp)

        if filep is None:
            return resp.content
        else:
            filep.seek(0)  # in case of retries

        # write response out to file
        for chunk in resp.iter_bytes(chunk_size=512 * 1024):
            if chunk:
                filep.write(chunk)
        filep.close()

    ##
    #  detections
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def detections(self, wait_capture_id=None):
        """
        Return a list of detection dictionaries for this media.

        wait_capture_id (str):  capture_id from previous associate_media call with enable_wait_result=True
                                This will block until all application detections are available.
        """
        url = "/1/media/%s/detections" % (self.media_id)

        if wait_capture_id is not None:
            url += "?wait_capture_id=%s" % wait_capture_id

        resp = await self._cc._get(url)
        return resp.json()['detections']

    ##
    #  subjects
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def subjects(self):
        """
        Return a list of subject associations for this media.
        """
        resp = await self._cc._get("/1/media/%s/subjects" % (self.media_id))
        return resp.json()['data']
