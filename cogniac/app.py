"""
CogniacApplication Object Client

Copyright (C) 2016 Cogniac Corporation
"""

from retrying import retry
from common import *


class CogniacApplication(object):
    """
    CogniacApplication
    Applications are the main locus of activity within the Cogniac System.

    This classes manages applications within the Cogniac System via the
    Cogniac public API application endpoints.

    Create a new application with
    CogniacConnection.create_application() or CogniacApplication.create()

    Get an existing application with
    CogniacConnection.get_application() or CogniacApplication.get()

    Get all tenant's applications with
    CogniacConnection.get_all_applications() or CogniacApplication.get_all()

    Writes to mutable CogniacApplication attributes are saved immediately via the Cogniac API.
    """

    ##
    #  create
    ##
    @classmethod
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def create(cls,
               connection,
               name,
               application_type,
               description=None,
               active=True,
               input_subjects=None,
               output_subjects=None):
        """
        Create a new CogniacApplication

        connnection (CogniacConnection):     Authenticated CogniacConnection object
        name (String):                       Name of new application
        application_type (String)            Cogniac Application Type name
        description (String):                Optional description of the application
        active (Boolean):                    Application operational state
        input_subjects ([CogniacSubjects]):  List of CogniacSubjects inputs to this application
        output_subjects ([CogniacSubjects]): List of CogniacSubjects outputs for this application
        """
        data = dict(name=name, active=active, type=application_type)

        if description:
            data['description'] = description
        if input_subjects:
            if type(input_subjects[0]) == str:
                data['input_subjects'] = input_subjects
            else:
                data['input_subjects'] = [s.subject_uid for s in input_subjects]
        if output_subjects:
            if type(output_subjects[0]) == str:
                data['output_subjects'] = output_subjects
            else:
                data['output_subjects'] = [s.subject_uid for s in output_subjects]

        resp = connection.session.post(url_prefix + "/applications", json=data, timeout=connection.timeout)
        raise_errors(resp)

        return CogniacApplication(connection, resp.json())

    ##
    #  get
    ##
    @classmethod
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def get(cls,
            connection,
            application_id):
        """
        return an existing CogniacApplication

        connnection (CogniacConnection):     Authenticated CogniacConnection object
        application_id (String):             The application_id of the Cogniac application to return
        """
        resp = connection.session.get(url_prefix + "/applications/%s" % application_id, timeout=connection.timeout)
        raise_errors(resp)
        return CogniacApplication(connection, resp.json())

    ##
    #  get_all
    ##
    @classmethod
    def get_all(cls, connection):
        """
        return CogniacApplications for all applications belonging to the currently authenticated tenant

        connnection (CogniacConnection):     Authenticated CogniacConnection object
        """
        resp = connection.session.get(url_prefix + '/tenants/%s/applications' % connection.tenant.tenant_id, timeout=connection.timeout)
        raise_errors(resp)
        apps = resp.json()['data']
        return [CogniacApplication(connection, appd) for appd in apps]

    ##
    #  __init__
    ##
    def __init__(self, connection, application_dict):
        """
        create a CogniacApplication

        This is not normally called directly by users, instead use:
        CogniacConnection.create_application() or
        CogniacApplication.create()
        """
        self._cc = connection
        self._app_keys = application_dict.keys()
        for k, v in application_dict.items():
            super(CogniacApplication, self).__setattr__(k, v)

    ##
    #  delete
    ##
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def delete(self):
        """
        Delete the application.
        This will delete existing models but will not delete associated subjects or media.
        """
        resp = self._cc.session.delete(url_prefix + "/applications/%s" % self.application_id, timeout=self._cc.timeout)
        raise_errors(resp)
        for k in self._app_keys:
            delattr(self, k)
        self._app_keys = None
        self.connection = None
        self.requests = None

    def __setattr__(self, name, value):
        if name in ['application_id', 'created_at', 'created_by', 'modified_at', 'modified_by']:
            raise AttributeError("%s is immutable" % name)
        if name in ['name', 'description', 'active', 'input_subjects', 'output_subjects']:
            data = {name: value}
            resp = self._cc.session.post(url_prefix + "/applications/%s" % self.application_id, json=data,  timeout=self._cc.timeout)
            raise_errors(resp)
            for k, v in resp.json().items():
                super(CogniacApplication, self).__setattr__(k, v)
            return
        super(CogniacApplication, self).__setattr__(name, value)

    def __str__(self):
        return "%s (%s)" % (self.name, self.application_id)

    def __repr__(self):
        return "%s (%s)" % (self.name, self.application_id)

    def add_output_subject(self, subject):
        """
        Add a the specified subject the the Application's outputs.

        subject (CogniacSubject):   the subject to add
        """
        self.output_subjects = self.output_subjects + [subject.subject_uid]

    def add_input_subject(self, subject):
        """
        Add a the specified subject the the Application's inputs.

        subject (CogniacSubject):   the subject to add
        """
        self.input_subjects = self.input_subjects + [subject.subject_uid]

    ##
    #  pending_feedback
    ##
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def pending_feedback(self):
        """
        Return the integer number of feedback requests pending for this application.
        This is useful for controlling the flow of images input into the system to avoid creating too many backlogged feedback requests.
        """
        resp = self._cc.session.get(url_prefix + "/applications/%s/feedback/pending" % self.application_id, timeout=self._cc.timeout)
        raise_errors(resp)

        return resp.json()['pending']

    ##
    #  get_feedback
    ##
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def get_feedback(self, limit=10):
        """
        returns a list of  up to {limit} feedback request messages for the application

        limit (Int):   Maximum number of feedback request messages to return
        """
        resp = self._cc.session.get(url_prefix + "/applications/%s/feedback?limit=%d" % (self.application_id, limit), timeout=self._cc.timeout)
        raise_errors(resp)
        return resp.json()

    ##
    #  post_feedback
    ##
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def post_feedback(self, subject_uid, media_id, result, app_data_type=None, app_data=None ):
        """
        Provides feedback to the application for a given subject-media assocation; returns None.

        subject_uid  (String):         Subject ID of the subject to associate with the media item
        media_id (String):             Media ID of the media to provide feedback on
        result (String):               One of 'True', 'False', 'Uncertain'; whether the subject is positively associated with the media
        app_data_type (String):        (Optional) Type of extra app-specific data for certain app types
        app_data (Object):             (Optional) Additional, app-specific, subject-media association data

        """
        feedback_response = {'media_id': media_id,
                             'subjects':
                             [
                                 {'subject_uid':    subject_uid,
                                  'media_id':       media_id,
                                  'result':         result,
                                  'app_data_type':  app_data_type,
                                  'app_data':       app_data}
                             ]}

        resp = self._cc.session.post(url_prefix + "/applications/%s/feedback" % self.application_id, json=feedback_response, timeout=self._cc.timeout)
        raise_errors(resp)
        return None

    ##
    #  model_name
    ##
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def model_name(self):
        """
        return the modelname for the current best model for this application
        """
        resp = self._cc.session.get(url_prefix + "/applications/%s/ccp" % self.application_id, timeout=self._cc.timeout)

        raise_errors(resp)
        resp = resp.json()

        url = resp['best_model_ccp_url']
        modelname = url.split('/')[-1]
        return modelname

    ##
    #  download_model
    ##
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def download_model(self):
        """
        Download the current active model for this application to a file in the current working directory and
        return the local filename which will be the same as the model name.
        """
        resp = self._cc.session.get(url_prefix + "/applications/%s/ccp" % self.application_id, timeout=self._cc.timeout)
        raise_errors(resp)

        resp = resp.json()
        url = resp['best_model_ccp_url']
        modelname = url.split('/')[-1]

        resp = self._cc.session.get(url, timeout=self._cc.timeout)
        raise_errors(resp)

        fp = open(modelname, "w")
        fp.write(resp.content)
        fp.close()
        return modelname

    ##
    #  media_associations
    ##
    def media_associations(self, start=None, end=None, reverse=True, probability_lower=0, probability_upper=1, consensus=None, only_user=False, only_model=False, limit=None):
        """
        yield media associations for the application sorted by last update timestamp. 

        start (float)          filter by last update timestamp > start (seconds since epoch)
        end (float)            filter by last update timestamp < end   (seconds since epoch)
        reverse (bool)         reverse the sorting order: sort high to low
        probability_lower:     filter by probability > probability_lower
        probability_upper:     filter by probability < probability_upper
        consensus (string):    filter by consensus label: "True", "False", or "Uncertain"
        only_user (bool):      sort subject media associations based on update by user feedback
        only_model (bool):     sort subject media associations based on update by model prediction
        limit (int)            yield maximum of limit results

        Returns (yield) association dictionary with the following fields:

        media_id        the media_id
        subject_uid		the subject_uid
        focus (dict)    Optional Focus of this association within the media
                           'frame'   Optional frame within a video media
                           'box'     Optional dictionary of bounding box pixel offsets (with keys x0, x1, y0, y1) within the frame
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
            assert(consensus in ['True', 'False', 'Uncertain'])
            args.append("consensus=%s" % consensus)
        if reverse:
            args.append('reverse=True')
        if only_user:
            args.append('only_user=True')
        if only_model:
            args.append('only_model=True')
        if limit:
            assert(limit > 0)
            args.append('limit=%d' % min(limit, 100))  # api support max limit of 100

        url = url_prefix + "/applications/%s/media?" % self.application_id
        url += "&".join(args)

        @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
        def get_next(url):
            resp = self._cc.session.get(url, timeout=self._cc.timeout)
            raise_errors(resp)
            return resp.json()

        count = 0
        while url:
            resp = get_next(url)
            #media_items = resp['media_items']
            for sma in resp['data']:
                yield sma
                count += 1
                if limit and count == limit:
                    return
            url = resp['paging'].get('next')
