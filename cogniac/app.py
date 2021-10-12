"""
CogniacApplication Object Client

Copyright (C) 2016 Cogniac Corporation
"""

from retrying import retry
import six
from .common import server_error


@six.python_2_unicode_compatible
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
               output_subjects=None,
               app_managers=None):
        """
        Create a new CogniacApplication

        connnection (CogniacConnection):     Authenticated CogniacConnection object
        name (String):                       Name of new application
        application_type (String)            Cogniac Application Type name
        description (String):                Optional description of the application
        active (Boolean):                    Application operational state
        input_subjects ([CogniacSubjects]):  List of CogniacSubjects inputs to this application
        output_subjects ([CogniacSubjects]): List of CogniacSubjects outputs for this application
        app_managers ([String]):             List of email addresses authorized to be Application Managers
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

        if app_managers is not None:
            data['app_managers'] = app_managers

        resp = connection._post("/1/applications", json=data)

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
        resp = connection._get("/1/applications/%s" % application_id)
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
        resp = connection._get('/1/tenants/%s/applications' % connection.tenant.tenant_id)
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
        self.__parse_app_dict__(application_dict)

    def __parse_app_dict__(self, application_dict):
        for k, v in application_dict.items():

            if k == "app_type_config":
                app_type_config = CogniacApplication._CogniacAppTypeConfig(app=self, app_type_config_dict=v)
                super(CogniacApplication, self).__setattr__("app_type_config", app_type_config)
            else:
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
        self._cc._delete("/1/applications/%s" % self.application_id)

        for k in self._app_keys:
            delattr(self, k)

        self._app_keys = None
        self.connection = None

    def __post_update__(self, data):
        resp = self._cc._post("/1/applications/%s" % self.application_id, json=data)
        self.__parse_app_dict__(resp.json())

    def __setattr__(self, name, value):
        if name in ['app_type_config']:
            raise AttributeError("Please modify {} by accessing its own attributes.".format(name))

        if name in ['application_id', 'created_at', 'created_by', 'modified_at', 'modified_by']:
            raise AttributeError("%s is immutable" % name)

        if name in ['name', 'description', 'active', 'input_subjects', 'output_subjects', 'app_managers',
                    'detection_post_urls', 'detection_thresholds', 'custom_fields', 'app_type_config',
                    'edgeflow_upload_policies', 'override_upstream_detection_filter', 'feedback_resample_ratio',
                    'reviewers', 'inference_execution_policies', 'primary_release_metric', 'secondary_evaluation_metrics']:
            data = {name: value}
            self.__post_update__(data)
            return

        super(CogniacApplication, self).__setattr__(name, value)

    def __str__(self):
        return "%s (%s)" % (self.name, self.application_id)

    def __repr__(self):
        return self.__str__()

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
        resp = self._cc._get("/1/applications/%s/feedback/pending" % self.application_id)
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
        resp = self._cc._get("/1/applications/%s/feedback?limit=%d" % (self.application_id, limit))
        return resp.json()

    ##
    #  post_feedback
    ##
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def post_feedback(self, media_id, subjects):
        """
        Provides feedback to the application for a given subject-media assocation; returns None.

        media_id (String):             Media ID of the media to provide feedback on
        subjects (list of dicts):      Subject-media association dictionaries of the form:

            subject_uid:               Subject UID
            result (str):              Either 'True', 'False', 'Uncertain'
            app_data_type (String):    (Optional) Type of extra app-specific data for certain app types
            app_data (Object):         (Optional) Additional, app-specific, subject-media association data

        """
        # add media_id to each subject-media association dict
        # TODO: deprecate this
        for s in subjects:
            s['media_id'] = media_id

        feedback_response = {'media_id': media_id,
                             'subjects': subjects}

        self._cc._post("/1/applications/%s/feedback" % self.application_id, json=feedback_response)

    ##
    #  list of models released
    ##
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def models(self, start=None, end=None, limit=None, reverse=True):
        """
        return a list of models
        """
        # build the search args
        # perform only one search at a time
        args = []
        if start is not None:
            args.append("start=%f" % start)
        if end is not None:
            args.append("end=%f" % end)

        if reverse:
            args.append('reverse=True')
        if limit:
            assert(limit > 0)
            args.append('limit=%d' % min(limit, 100))  # api support max limit of 100

        url = "/1/applications/%s/models?" % self.application_id
        url += "&".join(args)

        @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
        def get_next(url):
            resp = self._cc._get(url)
            return resp.json()

        # due to one model_id can have multiple runtimes, we want to return them together
        # the limit is applied on number of model_ids, not model runtimes
        model_ids = set()
        previous_model_id = None
        while url:
            resp = get_next(url)
            for det in resp['data']:
                model_id = det['model_id']
                model_ids.add(model_id)
                yield det

                if limit and len(model_ids) >= limit:
                    if previous_model_id is not None and model_id != previous_model_id:
                        return
                previous_model_id = model_id
            url = resp['paging'].get('next')
    ##
    #  model_name
    ##
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def model_name(self):
        """
        return the modelname for the current best model for this application
        """
        resp = self._cc._get("/1/applications/%s/ccp" % self.application_id)
        resp = resp.json()

        url = resp['best_model_ccp_url']
        modelname = url.split('/')[-1]
        return modelname

    ##
    #  download_model
    ##
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def download_model(self, model_id=None):
        """
        Download the current active model for this application to a file in the current working directory and
        return the local filename which will be the same as the model name.
        """
        if model_id is None:
            resp = self._cc._get("/1/applications/%s/ccp" % self.application_id)
            resp = resp.json()
            url = resp['best_model_ccp_url']
            modelname = url.split('/')[-1]
        else:
            modelname = model_id.split('/')[-1]

        resp = self._cc._get("/1/applications/%s/ccppkg" % self.application_id, json={"ccp_filename": modelname})

        fp = open(modelname, "wb")
        fp.write(resp.content)
        fp.close()
        return modelname

    ##
    #  detections
    ##
    def detections(self, start=None, end=None, reverse=True, probability_lower=None, probability_upper=None,  limit=None, consensus_none=False, only_user=False, only_model=False, abridged_media=True):
        """
        Yield application output assertions (model predictions and/or user feedback) sorted by timestamp.


        start (float)          filter by last update timestamp > start (seconds since epoch)
        end (float)            filter by last update timestamp < end   (seconds since epoch)
        reverse (bool)         reverse the sorting order: sort high to low
        probability_lower:     filter by probability > probability_lower
        probability_upper:     filter by probability < probability_upper
        limit (int)            yield maximum of limit results
        consensus_none (bool): only return items that have not reached consensus.
                               This is useful for alternate feedback interfaces where it is
                               undesirable to display items that have already reached consensus
        only_user (bool):      If True, only return feedback assertions from users, not model predictions
        only_model (bool);     If True, only return model prediction assertions, not feedback assertions from users
        abridged_media (bool)  return full media items if False (slower), otherwise return just media_id's for each media_item


        Returns (yield) association dictionary with the following fields:

        media(dict):  { system media dictionary}

        focus(dict):  { system focus context (box, segment, etc) dictionary}

        updated_at(float):  epoch timstamp of model prediction or user feedback

        detections : list of dictionaries as follows:
             detection_id:     internal detection_id
             user_id:          a user_id if this was from a user
             model_id:         a model_id if this was from an app w/model
             uncal_prob:       the raw uncalibrated user or model confidence (if any)
             timestamp:        the time of this detection
             prev_prob:        subject-media probability before this detection (if any)
             probability:      the resulting probability after this detection
             app_data_type     Optional type of extra app-specific data
             app_data          Optional extra app-specific data

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
        if reverse:
            args.append('reverse=True')
        if limit:
            assert(limit > 0)
            args.append('limit=%d' % min(limit, 100))  # api support max limit of 100
        if consensus_none:
            args.append("consensus_none=True")
        if only_user:
            args.append("only_user=True")
        if only_model:
            args.append("only_model=True")
        if abridged_media:
            args.append('abridged_media=True')

        url = "/1/applications/%s/detections?" % self.application_id
        url += "&".join(args)

        @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
        def get_next(url):
            resp = self._cc._get(url)
            return resp.json()

        count = 0
        while url:
            resp = get_next(url)
            for det in resp['data']:
                yield det
                count += 1
                if limit and count == limit:
                    return
            url = resp['paging'].get('next')

    def accumulate_usage(self, start, end):
        """
        return single cummulative app usage record for start to end epoch times
        """
        url = "/1/usage/app/%s?start=%d&end=%d&accumulate=True" % (self.application_id, start, end)
        resp = self._cc._get(url)
        data = resp.json()['data']
        return data[0] if len(data) else None

    def usage(self, start, end):
        """
        yield sparse app usage records in order between start and end epoch times
        """
        url = "/1/usage/app/%s?start=%d&end=%d" % (self.application_id, start, end)

        @retry(stop_max_attempt_number=8, wait_exponential_multiplier=5, retry_on_exception=server_error)
        def get_next(url):
            resp = self._cc._get(url)
            return resp.json()

        while url:
            resp = get_next(url)
            for record in resp['data']:
                yield record
            url = resp['paging'].get('next')

    class _CogniacAppTypeConfig(object):
        def __init__(self, app, app_type_config_dict):
            super(CogniacApplication._CogniacAppTypeConfig, self).__setattr__(
                "_app_type_config_keys", app_type_config_dict.keys())
            self._app = app

            for k, v in app_type_config_dict.items():
                super(CogniacApplication._CogniacAppTypeConfig, self).__setattr__(k, v)

        def __get_app_type_config_dict__(self):
            d = {}

            for k, v in self.__dict__.items():
                if k in self._app_type_config_keys:
                    d[k] = v

            return d

        def __setattr__(self, name, value):
            if name in self._app_type_config_keys:
                d = self.__get_app_type_config_dict__()
                d[name] = value

                data = {"app_type_config": d}
                self._app.__post_update__(data)
            else:
                super(CogniacApplication._CogniacAppTypeConfig, self).__setattr__(name, value)

        def __repr__(self):
            d = self.__get_app_type_config_dict__()
            return repr(d)
