"""
CogniacSubject Object Client

Copyright (C) 2016 Cogniac Corporation
"""

from retrying import retry
from common import *
import sys

from media import CogniacMedia


##
#  CogniacSubject
##
class CogniacSubject(object):
    """
    CogniacSubject
    Subjects are a central organizational mechanism in the Cogniac system.
    A subject is any user-defined concept that is relevant to images or video.
    More generally a subject can represent any logical grouping of images of video.

    Most Cogniac applications work by taking input media from user-defined subjects
    and outputing those media to other user-defined subjects based on the content
    of the media.

    Create a new subject with
    CogniacConnection.create_subject() or CogniacSubject.create()

    Get an existing subject with
    CogniacConnection.get_subject() or CogniacSubject.get()

    Get all tenant's subject with
    CogniacConnection.get_all_subjects() or CogniacSubject.get_all()

    Writes to mutable CogniacSubjects attributes are saved immediately via the Cogniac API.
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
               external_id=None,
               public_read=False,
               public_write=False):
        """
        Create a CogniacSubject

        connnection (CogniacConnection):     Authenticated CogniacConnection object
        name (String):                       Name of new subject
        description (String):                Optional description of the subject
        external_id (String):                Optional user supplied id for the subject
        public_read(Bool):                   Subject media is accessible to other tenants and can be input into other tenant's apps.
        public_write(Bool):                  Other tenants can access and associate media with this subject.
        """
        if public_write:
            public_read = True

        data = dict(name=name, public_read=public_read, public_write=public_write)
        if description:
            data['description'] = description
        if external_id:
            data['external_id'] = external_id

        resp = connection._post("/subjects", json=data)

        return CogniacSubject(connection, resp.json())

    ##
    #  get
    ##
    @classmethod
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def get(cls,
            connection,
            subject_uid):
        """
        return an existing CogniacSubject

        connnection (CogniacConnection):     Authenticated CogniacConnection object
        subject_id (String):                 The subject_id of the Cogniac Subject to return
        """
        resp = connection._get("/subjects/%s" % subject_uid)
        return CogniacSubject(connection, resp.json())

    ##
    #  get_all
    ##
    @classmethod
    def get_all(cls, connection, public_read=False, public_write=False):
        """
        return CogniacSubjects for all subjects belonging to the currently authenticated tenant

        connnection (CogniacConnection):     Authenticated CogniacConnection object
        public_read (bool):                  return subjects that are publicly readable (other tenants can use associated media)
        public_write (bool):                 return subjects that are publicly writeable (others tenants associate new media)
        """

        args = []
        if public_read:
            args.append("public_read=True")
        if public_write:
            args.append("public_read_write=True")

        url = "/tenants/%s/subjects?" % connection.tenant.tenant_id
        url += "&".join(args)

        resp = connection._get(url)
        subs = resp.json()['data']
        return [CogniacSubject(connection, s) for s in subs]

    ##
    #  search
    ##
    @classmethod
    def search(cls, connection, ids=[], prefix=None, similar=None, name=None, tenant_owned=True, public_read=False, public_write=False, limit=10):
        """
        search CogniacSubjects for either batch subject ID's, based on prefix, or semantic simlarity

        connnection (CogniacConnection):     Authenticated CogniacConnection object

        ids (list of strings):               return list of subjects with the given subject_uid's
        prefix (string):                     return subjects that have a name containing the given string;
                                             direct prefix matching results in a higher search score
        similar (string):                    return subjects with a name that is related to the given search term;
                                             i.e. similar='cat' will return a set containing the subject 'dog'
        name (string):                       returns list of subjects with the exact name specified.

        Exactly one ids, prefix, similar, or name must be specified.

        tenant_owned (bool):                 return subjects belonging to this tenant.
        public_read (bool):                  return subjects that are publicly readable (other tenants can use associated media)
        public_write (bool):                 return subjects that are publicly writeable (others tenants associate new media)
        limit (int):                         max number of results to return
        """

        args = []

        # build the search args
        args.append('limit=%d' % limit)
        args.append('tenant_read_write=%s' % str(tenant_owned))
        if public_read:
            args.append("public_read=True")

        if public_write:
            args.append("public_read_write=True")

        # perform only one search at a time
        # id search, prefix search, similarity or name search
        if len(ids):
            args.append('ids=%s' % (',').join(ids))
        elif prefix:
            args.append('prefix=%s' % prefix)
        elif similar:
            args.append('similar=%s' % similar)
        elif name:
            args.append('name=%s' % name)

        url = "/tenants/%s/subjects?" % connection.tenant.tenant_id
        url += "&".join(args)

        resp = connection._get(url)
        subs = resp.json()['data']
        return [CogniacSubject(connection, s) for s in subs]

    ##
    #  __init__
    ##
    def __init__(self, connection, subject_dict):
        """
        create a CogniacSubject

        This is not normally called directly by users, instead use:
        CogniacConnection.create_subject() or
        CogniacSubject.create()
        """
        self._cc = connection
        self._sub_keys = subject_dict.keys()
        for k, v in subject_dict.items():
            super(CogniacSubject, self).__setattr__(k, v)

    ##
    #  delete
    ##
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def delete(self):
        """
        Delete the subject.
        """
        resp = self._cc._delete("/subjects/%s" % self.subject_uid)

        for k in self._sub_keys:
            delattr(self, k)
        self._sub_keys = None
        self.connection = None

    def __setattr__(self, name, value):
        if name in ['subject_uid', 'created_at', 'created_by', 'modified_at', 'modified_by']:
            raise AttributeError("%s is immutable" % name)
        if name in ['name', 'description', 'public_read', 'public_write']:
            data = {name: value}
            resp = self._cc._post("/subjects/%s" % self.subject_uid, json=data)
            for k, v in resp.json().items():
                super(CogniacSubject, self).__setattr__(k, v)
            return
        super(CogniacSubject, self).__setattr__(name, value)

    def __str__(self):
        s = "%s (%s)" % (self.name, self.subject_uid)
        return s.encode(sys.stdout.encoding)

    def __repr__(self):
        s = "%s (%s)" % (self.name, self.subject_uid)
        return s.encode(sys.stdout.encoding)

    ##
    #  dissassociate_media
    ##
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def disassociate_media(self,
                           media,
                           focus=None):
        """
        Disassociate the media (with an optional focus within the media) with this subject.

        media (String or CogniacMedia)   media object or media_id to associate
        focus (dict)                     Optional Focus of this association within the media
                                         'frame'   Optional frame within a video media
                                         'box'     Optional dictionary of bounding box pixel offsets (with keys x0, x1, y0, y1) within the frame.

        """
        if type(media) is CogniacMedia:
            data = {'media_id': media.media_id}
        else:
            data = {'media_id': media}

        if focus is not None:
            data['focus'] = focus
        self._cc._delete("/subjects/%s/media" % self.subject_uid, json=data)

    ##
    #  associate_media
    ##
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def associate_media(self,
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

        media (String or CogniacMedia)   media object or media_id to associate
        focus (dict)                     Optional Focus of this association within the media
                                         'frame'   Optional frame within a video media
                                         'box'     Optional dictionary of bounding box pixel offsets (with keys x0, x1, y0, y1) within the frame.
        consensus (str)                  'True' if media is associated with subject,
                                         'False' if media is NOT associated with subject.
                                         'None' if consenus is unknown.  Required uncal_prob
        probability (float)              association probability, only valid if consensus = 'None'
        force_feedback (bool)            True to force feedback on the media item in downstream apps
        force_random_feedback(bool)      True to force feedback on the media item in downstream apps because.
                                         Set only if this media was randomly selected for feedback.
                                         This media will be used for the (random) performance assessment.
        app_data                         Specific app data for this subject-media association
        app_data_type                    Type of app data for the subject-media association
        enable_wait_result(bool)         When True: enable 'synchronous' result interfaces whereby subsequent
                                         GET /media/<media_id>/detections?wait_capture_id=<capture_id> endpoints block until
                                         the full results of the application pipeline resulting from this input association are available

        returns the unique capture_id
        """

        if type(media) is CogniacMedia:
            data = {'media_id': media.media_id}
        else:
            data = {'media_id': media}

        if focus is not None:
            data['focus'] = focus

        assert(consensus in ['True', 'False', 'None'])
        data['consensus'] = consensus

        if consensus is 'None' and probability is None:
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

        resp = self._cc._post("/subjects/%s/media" % self.subject_uid, json=data)
        return resp.json()['capture_id']

    ##
    #  media_associations
    ##
    def media_associations(self, start=None, end=None, reverse=True, probability_lower=None, probability_upper=None, consensus=None, sort_probability=False, limit=None, abridged_media=True):
        """
        yield media associations for the subject sorted by last update timestamp or probability

        start (float)          filter by last update timestamp > start (seconds since epoch)
        end (float)            filter by last update timestamp < end   (seconds since epoch)
        reverse (bool)         reverse the sorting order: sort high to low
        probability_lower:     filter by probability > probability_lower
        probability_upper:     filter by probability < probability_upper
        consensus (string):    filter by consensus label: "True", "False"
        sort_probability(bool) Sort by probability instead of last update timestamp
        limit (int)            yield maximum of limit results
        abridged_media (bool)  return full media items if False (slower), otherwise return just media_id's for each media_item

        Returns (yield) association dictionary with the following fields:

        media_id        the media_id
        subject_uid		the subject_uid
        focus (dict)    Optional Focus of this association within the media
                           'frame'   Optional frame within a video media
                           'box'     Optional dictionary of bounding box pixel offsets (with keys x0, x1, y0, y1) within the frame.
        probability		current assessment of the probability in [0,1] that the subject_uid is associated with the media_id
                        1 = subject definitely associated with media+focus
                        0 = subject definitely NOT associated with media+focus
                        0.5 ~= uncertain association between subject and media+focus
        timestamp	time of last update to subject media association
        app_data_type	optional app data type if applicable
        app_data        optional app data if applicable
        consensus		'True', 'False', or , or None
                        'True' if there is consensus that the subject is associated with the media
                            (Media will be used as a positive training example of the subject)
                        'False' if there is consensus that the subject is not associated w/the media
                            (Media will be used as a negative training example of the subject.)
                         None if if there is not enough evidence to reach consensus
                         Some application types only support 'True' or None.
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
            assert(consensus in ['True', 'False'])
            args.append("consensus=%s" % consensus)
        if reverse:
            args.append('reverse=True')
        else:
            args.append('reverse=False')
        if sort_probability:
            args.append("sort=probability")
        if limit:
            assert(limit > 0)
            args.append('limit=%d' % min(limit, 100))  # api support max limit of 100
        if abridged_media:
            args.append('abridged_media=True')

        url = "/subjects/%s/media?" % self.subject_uid
        url += "&".join(args)

        @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
        def get_next(url):
            resp = self._cc._get(url)
            return resp.json()

        count = 0
        while url:
            resp = get_next(url)
            for sma in resp['data']:
                yield sma
                count += 1
                if limit and count == limit:
                    return
            url = resp['paging'].get('next')
