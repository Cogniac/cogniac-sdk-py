"""
Async CogniacSubject Object Client

Copyright (C) 2016 Cogniac Corporation
"""

from .common import retry, stop_after_attempt, wait_exponential, retry_if_exception, server_error, raise_errors


class AsyncCogniacSubject(object):
    """
    AsyncCogniacSubject
    Async version of CogniacSubject.

    Subjects are a central organizational mechanism in the Cogniac system.
    A subject is any user-defined concept that is relevant to images or video.

    Create a new subject with AsyncCogniacSubject.create()
    Get an existing subject with AsyncCogniacSubject.get()
    Get all tenant's subjects with AsyncCogniacSubject.get_all()

    Use the async set() method to update mutable attributes.
    """

    mutable_keys = ['name', 'description', 'expires_in', 'external_id', 'custom_data']
    immutable_keys = ['subject_uid', 'created_at', 'created_by', 'modified_at', 'modified_by']

    ##
    #  create
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def create(cls,
                     connection,
                     name,
                     description=None,
                     external_id=None,
                     public_read=False,
                     public_write=False):
        """
        Create a AsyncCogniacSubject

        connection (AsyncCogniacConnection): Authenticated AsyncCogniacConnection object
        name (String):                       Name of new subject
        description (String):                Optional description of the subject
        external_id (String):                Optional user supplied id for the subject
        public_read(Bool):                   Subject media is accessible to other tenants
        public_write(Bool):                  Other tenants can associate media with this subject
        """
        if public_write:
            public_read = True

        data = dict(name=name, public_read=public_read, public_write=public_write)
        if description:
            data['description'] = description
        if external_id:
            data['external_id'] = external_id

        resp = await connection._post("/1/subjects", json=data)
        return AsyncCogniacSubject(connection, resp.json())

    ##
    #  get
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def get(cls, connection, subject_uid):
        """
        Return an existing AsyncCogniacSubject

        connection (AsyncCogniacConnection): Authenticated AsyncCogniacConnection object
        subject_uid (String):                The subject_uid of the Cogniac Subject to return
        """
        resp = await connection._get("/1/subjects/%s" % subject_uid)
        return AsyncCogniacSubject(connection, resp.json())

    ##
    #  get_all
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def get_all(cls, connection, public_read=False, public_write=False):
        """
        Return AsyncCogniacSubjects for all subjects belonging to the currently authenticated tenant

        connection (AsyncCogniacConnection): Authenticated AsyncCogniacConnection object
        public_read (bool):                  return subjects that are publicly readable
        public_write (bool):                 return subjects that are publicly writeable
        """
        args = []
        if public_read:
            args.append("public_read=True")
        if public_write:
            args.append("public_read_write=True")

        url = "/1/tenants/%s/subjects?" % connection.tenant_id
        url += "&".join(args)

        resp = await connection._get(url)
        subs = resp.json()['data']
        return [AsyncCogniacSubject(connection, s) for s in subs]

    ##
    #  search
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def search(cls, connection, ids=None, prefix=None, similar=None, name=None,
                     tenant_owned=True, public_read=False, public_write=False, limit=10):
        """
        Search AsyncCogniacSubjects by batch subject IDs, prefix, or semantic similarity

        connection (AsyncCogniacConnection): Authenticated AsyncCogniacConnection object
        ids (list of strings):               return subjects with the given subject_uid's
        prefix (string):                     return subjects with name containing the given string
        similar (string):                    return subjects with a name related to the given search term
        name (string):                       returns subjects with the exact name specified

        Exactly one of ids, prefix, similar, or name must be specified.

        tenant_owned (bool):                 return subjects belonging to this tenant
        public_read (bool):                  return publicly readable subjects
        public_write (bool):                 return publicly writeable subjects
        limit (int):                         max number of results to return
        """
        args = []
        args.append('limit=%d' % limit)
        args.append('tenant_read_write=%s' % str(tenant_owned))
        if public_read:
            args.append("public_read=True")
        if public_write:
            args.append("public_read_write=True")

        if ids:
            args.append('ids=%s' % (',').join(ids))
        elif prefix:
            args.append('prefix=%s' % prefix)
        elif similar:
            args.append('similar=%s' % similar)
        elif name:
            args.append('name=%s' % name)

        url = "/1/tenants/%s/subjects?" % connection.tenant_id
        url += "&".join(args)

        resp = await connection._get(url)
        subs = resp.json()['data']
        return [AsyncCogniacSubject(connection, s) for s in subs]

    ##
    #  __init__
    ##
    def __init__(self, connection, subject_dict):
        """
        Create a AsyncCogniacSubject

        This is not normally called directly by users, instead use:
        AsyncCogniacSubject.create() or AsyncCogniacSubject.get()
        """
        self._cc = connection
        self._sub_keys = subject_dict.keys()
        for k, v in subject_dict.items():
            super(AsyncCogniacSubject, self).__setattr__(k, v)

    ##
    #  delete
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def delete(self):
        """
        Delete the subject.
        """
        await self._cc._delete("/1/subjects/%s" % self.subject_uid)

        for k in self._sub_keys:
            delattr(self, k)
        self._sub_keys = None
        self._cc = None

    ##
    #  set
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def set(self, **kwargs):
        """
        Update mutable subject attributes via a single POST call.

        Accepted keys: name, description, expires_in, external_id, custom_data

        Example:
            await subject.set(name="new name", description="new desc")
        """
        for key in kwargs:
            if key in self.immutable_keys:
                raise AttributeError("%s is immutable" % key)
            if key not in self.mutable_keys:
                raise AttributeError("%s is not a recognized mutable attribute" % key)

        resp = await self._cc._post("/1/subjects/%s" % self.subject_uid, json=kwargs)
        for k, v in resp.json().items():
            super(AsyncCogniacSubject, self).__setattr__(k, v)

    def __setattr__(self, name, value):
        if name in self.immutable_keys:
            raise AttributeError("%s is immutable" % name)
        if name in self.mutable_keys:
            raise AttributeError("Use 'await subject.set(%s=...)' to update server-managed attributes" % name)
        super(AsyncCogniacSubject, self).__setattr__(name, value)

    def __str__(self):
        return "%s (%s)" % (self.name, self.subject_uid)

    def __repr__(self):
        return self.__str__()

    ##
    #  associate_media
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def associate_media(self,
                              media,
                              focus=None,
                              consensus='None',
                              probability=None,
                              force_feedback=False,
                              force_random_feedback=False,
                              app_data=None,
                              app_data_type=None,
                              enable_wait_result=False):
        """
        Associate the media (with an optional focus within the media) with this subject.

        media (String or object)         media object (with media_id attr) or media_id string
        focus (dict)                     Optional focus within the media
        consensus (str)                  'True', 'False', 'Sidelined', or 'None'
        probability (float)              association probability, only valid if consensus='None'
        force_feedback (bool)            force feedback on the media item
        force_random_feedback(bool)      force random feedback
        app_data                         specific app data
        app_data_type                    type of app data
        enable_wait_result(bool)         enable synchronous result interface

        returns the unique capture_id
        """
        if hasattr(media, 'media_id'):
            data = {'media_id': media.media_id}
        else:
            data = {'media_id': media}

        if focus is not None:
            data['focus'] = focus

        assert(consensus in ['True', 'False', 'None', 'Sidelined'])
        data['consensus'] = consensus

        if consensus == 'None' and probability is None:
            data['uncal_prob'] = .99

        if probability is not None:
            assert(consensus == 'None')
            data['uncal_prob'] = probability

        if enable_wait_result:
            data['enable_wait_result'] = True

        data['force_feedback'] = force_feedback
        data['force_random_feedback'] = force_random_feedback
        data['app_data_type'] = app_data_type
        data['app_data'] = app_data

        resp = await self._cc._post("/1/subjects/%s/media" % self.subject_uid, json=data)
        return resp.json()['capture_id']

    ##
    #  disassociate_media
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def disassociate_media(self, media, focus=None):
        """
        Disassociate the media (with an optional focus) from this subject.

        media (String or object)   media object (with media_id attr) or media_id string
        focus (dict)               Optional focus within the media
        """
        if hasattr(media, 'media_id'):
            data = {'media_id': media.media_id}
        else:
            data = {'media_id': media}

        if focus is not None:
            data['focus'] = focus
        await self._cc._delete("/1/subjects/%s/media" % self.subject_uid, json=data)

    ##
    #  media_associations
    ##
    async def media_associations(self, start=None, end=None, reverse=True,
                                 probability_lower=None, probability_upper=None,
                                 consensus=None, sort_probability=False,
                                 limit=None, abridged_media=True):
        """
        Async generator yielding media associations for the subject.

        start (float)          filter by last update timestamp > start (seconds since epoch)
        end (float)            filter by last update timestamp < end   (seconds since epoch)
        reverse (bool)         reverse the sorting order: sort high to low
        probability_lower:     filter by probability > probability_lower
        probability_upper:     filter by probability < probability_upper
        consensus (string):    filter by consensus label: "True", "False" or "None"
        sort_probability(bool) Sort by probability instead of last update timestamp
        limit (int)            yield maximum of limit results
        abridged_media (bool)  return abridged media items if True
        """
        args = []
        if start is not None:
            args.append("start=%f" % start)
        if end is not None:
            args.append("end=%f" % end)
        if probability_lower is not None:
            args.append("probability_lower=%f" % probability_lower)
        if probability_upper is not None:
            args.append("probability_upper=%f" % probability_upper)
        if consensus is not None:
            assert(consensus in ['True', 'False', 'Sidelined', 'None'])
            args.append("consensus=%s" % consensus)
        if reverse:
            args.append('reverse=True')
        else:
            args.append('reverse=False')
        if sort_probability:
            args.append("sort=probability")
        if limit:
            assert(limit > 0)
            args.append('limit=%d' % min(limit, 100))
        if abridged_media:
            args.append('abridged_media=True')

        url = "/1/subjects/%s/media?" % self.subject_uid
        url += "&".join(args)

        @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
        async def get_next(url):
            resp = await self._cc._get(url)
            return resp.json()

        count = 0
        while url:
            resp = await get_next(url)
            for sma in resp['data']:
                yield sma
                count += 1
                if limit and count == limit:
                    return
            url = resp.get('paging', {}).get('next')
