"""
CogniacApplication Object Client

Copyright (C) 2016 Cogniac Corporation
"""

from .common import retry, stop_after_attempt, wait_exponential, retry_if_exception, server_error


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
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def create(cls,
               connection,
               name,
               application_type,
               description=None,
               active=True,
               input_subjects=None,
               output_subjects=None,
               app_managers=None,
               app_type_config=None):
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
        app_type_config ({String: Any}):     Dict containing application-type-specific parameters
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

        if app_type_config is not None:
            data['app_type_config'] = app_type_config

        resp = connection._post("/1/applications", json=data)

        return CogniacApplication(connection, resp.json())

    ##
    #  get
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
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
    #  application types
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def get_all_types(cls, connection, production=None, deprecated=None, reverse=False):
        """
        Return the list of application types available to the authenticated tenant.

        production (bool):   optionally filter by the production flag
        deprecated (bool):   optionally filter by the deprecated flag
        reverse (bool):      reverse the (name-ascending) sort order

        See GET /1/applications/all/types.
        """
        params = {}
        if production is not None:
            params['production'] = production
        if deprecated is not None:
            params['deprecated'] = deprecated
        if reverse:
            params['reverse'] = True
        resp = connection._get("/1/applications/all/types", params=params)
        return resp.json()

    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def get_type(cls, connection, application_type):
        """
        Return a single application type.

        application_type (str):  the application-type name

        See GET /1/applications/all/types/{application_type}.
        """
        resp = connection._get("/1/applications/all/types/%s" % application_type)
        return resp.json()

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
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
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

    ##
    #  update
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def update(self, body):
        """
        Update this application's mutable fields with the given body dict and
        return the updated application JSON.

        body (dict):  fields to update

        See POST /1/applications/{application_id}.
        """
        resp = self._cc._post("/1/applications/%s" % self.application_id, json=body)
        result = resp.json()
        self.__parse_app_dict__(result)
        return result

    def __post_update__(self, data):
        resp = self._cc._post("/1/applications/%s" % self.application_id, json=data)
        self.__parse_app_dict__(resp.json())

    def __setattr__(self, name, value):
        if name in ['app_type_config']:
            raise AttributeError("Please modify {} by accessing its own attributes.".format(name))

        if name in ['application_id', 'created_at', 'created_by', 'modified_at', 'modified_by']:
            raise AttributeError("%s is immutable" % name)

        if name in ['name', 'description', 'active', 'input_subjects', 'output_subjects', 'app_managers',
                    'detection_post_urls', 'detection_thresholds', 'subject_weights', 'custom_fields',
                    'app_type_config', 'edgeflow_upload_policies', 'override_upstream_detection_filter',
                    'feedback_resample_ratio', 'reviewers', 'inference_execution_policies',
                    'primary_release_metric', 'secondary_evaluation_metrics']:
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
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
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
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
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
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def post_feedback(self, media_id, subjects, focus=None):
        """
        Provides feedback to the application for a given subject-media assocation; returns None.

        media_id (String):             Media ID of the media to provide feedback on
        subjects (list of dicts):      Subject-media association dictionaries of the form:

            subject_uid:               Subject UID
            result (str):              One of 'True', 'False', 'Sidelined'
            app_data_type (String):    (Optional) Type of extra app-specific data for certain app types
            app_data (Object):         (Optional) Additional, app-specific, subject-media association data

        focus (dict, optional):        Focus within the media this feedback applies to. Required when
                                       the output subject's labels carry per-ROI focus (e.g. box_detection
                                       apps or focus-aware classifiers). Shape:
                                       {'box': {'x0': int, 'x1': int, 'y0': int, 'y1': int}}
                                       (and/or 'frame' for video). Note: a 'focus' key placed inside a
                                       subject dict is NOT read by the server — it must be passed here.
        """
        # add media_id to each subject-media association dict
        # TODO: deprecate this
        for s in subjects:
            s['media_id'] = media_id

        feedback_response = {'media_id': media_id,
                             'subjects': subjects}
        if focus is not None:
            feedback_response['focus'] = focus

        self._cc._post("/21/applications/%s/feedback" % self.application_id, json=feedback_response)

    ##
    #  list of models released
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
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

        @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
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
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
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
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
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

        @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
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

    ##
    #  leaderboard
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def leaderboard(self,
                    set_assignment='validation',
                    snapshot_type='regular',
                    eval_metrics='primary'):
        """
        Return the most recent ranked snapshot of candidate models for this application,
        evaluated under the application's active evaluation metrics.

        set_assignment (str):  'validation' (default) or 'training'
        snapshot_type (str):   'regular' (default) or 'int8'
        eval_metrics (str):    'primary' (default) for the primary metric only, or 'all'
                               for results across all active metrics

        Returns the raw response dict including:
            app_id, leaderboard_timestamp, snapshot (list of ranked candidate models),
            evaluation_metrics, primary_evaluation_metric_hash,
            consensus_release_id, consensus_release_timestamp.

        If results are not yet available, returns a dict {'message': ...} from the
        202 response (e.g., when no consensus snapshot exists yet for the metric).
        """
        for arg, val, choices in [
                ('set_assignment', set_assignment, ('validation', 'training')),
                ('snapshot_type', snapshot_type, ('regular', 'int8')),
                ('eval_metrics', eval_metrics, ('primary', 'all'))]:
            if val not in choices:
                raise ValueError("%s must be one of %s" % (arg, choices))

        url = "/22/applications/%s/leaderboard/recent_consensus_snapshot" % self.application_id
        params = {
            'set_assignment': set_assignment,
            'snapshot_type': snapshot_type,
            'eval_metrics': eval_metrics,
        }
        resp = self._cc._get(url, params=params)
        return resp.json()

    ##
    #  evaluation_metrics
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def evaluation_metrics(self):
        """
        Return the list of active evaluation metrics for this application.

        Each entry includes the metric hash, name, parameters (e.g., subject weights),
        active flag, primary flag, and user_tag.
        """
        resp = self._cc._get("/22/applications/%s/evaluation_metrics" % self.application_id)
        return resp.json()

    def accumulate_usage(self, start, end):
        """
        return single cummulative app usage record for start to end epoch times
        """
        url = "/1/usage/app/%s?start=%d&end=%d&accumulate=True" % (self.application_id, start, end)
        resp = self._cc._get(url)
        data = resp.json()['data']
        return data[0] if len(data) else None

    ##
    #  classify
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def classify(self, image_file):
        """
        Run inference/classification on a single uploaded image and return the
        resulting detections.

        image_file (str):  path to a local image file (image/* content type)

        See POST /1/applications/{app_id}/classify.
        """
        with open(image_file, 'rb') as f:
            resp = self._cc._post("/1/applications/%s/classify" % self.application_id,
                                  files={'file': f})
        return resp.json()

    ##
    #  donate_model
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def donate_model(self, source_application_id):
        """
        Donate the active model of source_application_id into this (target) application.

        source_application_id (str):  application_id whose model should be donated

        See POST /1/applications/{app_id}/donateModel (this application is the target).
        """
        resp = self._cc._post("/1/applications/%s/donateModel" % self.application_id,
                              json={'source_application_id': source_application_id})
        return resp.json()

    ##
    #  export_model_to_meraki
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def export_model_to_meraki(self):
        """
        Export this application's active model to the tenant's Meraki organization.

        See POST /1/applications/{app_id}/exportModelToMeraki.
        """
        resp = self._cc._post("/1/applications/%s/exportModelToMeraki" % self.application_id)
        return resp.json()

    ##
    #  replay_status
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def replay_status(self, timeout=None):
        """
        Return the current replay status for this application.

        This endpoint long-polls: it blocks until the replay state changes (or
        the server's long-poll window elapses). Pass timeout (seconds) to bound
        the client-side wait.

        See GET /1/applications/{app_id}/replay.
        """
        resp = self._cc._get("/1/applications/%s/replay" % self.application_id, timeout=timeout)
        return resp.json()

    ##
    #  replay_start
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def replay_start(self, body=None):
        """
        Start an application replay.

        body (dict):  optional StartReplayRequest body controlling the replay scope.

        See POST /1/applications/{app_id}/replay.
        """
        resp = self._cc._post("/1/applications/%s/replay" % self.application_id,
                              json=body if body is not None else {})
        return resp.json()

    ##
    #  replay_stop
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def replay_stop(self):
        """
        Stop an in-progress application replay.

        See POST /1/applications/{app_id}/replay (with a stop request body).
        """
        resp = self._cc._post("/1/applications/%s/replay" % self.application_id,
                              json={'replay': False})
        return resp.json()

    ##
    #  detections_pending
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def detections_pending(self):
        """
        Return the count of pending (unreviewed) detections for this application.

        See GET /1/applications/{app_id}/detections/pending.
        """
        resp = self._cc._get("/1/applications/%s/detections/pending" % self.application_id)
        return resp.json()

    ##
    #  event_types
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def event_types(self):
        """
        Return the list of available event types for this application.

        See GET /1/applications/{app_id}/eventTypes.
        """
        resp = self._cc._get("/1/applications/%s/eventTypes" % self.application_id)
        return resp.json()

    ##
    #  events
    ##
    def events(self, start=None, end=None, limit=None, cursor=None, reverse=False, event_types=None):
        """
        Yield application events sorted by timestamp.

        start (float)        filter by timestamp > start (seconds since epoch)
        end (float)          filter by timestamp < end   (seconds since epoch)
        limit (int)          yield maximum of limit results
        cursor (float)       opaque pagination cursor (timestamp)
        reverse (bool)       reverse the sorting order: sort high to low
        event_types (list)   optional list of event-type names to filter by

        See GET /1/applications/{app_id}/events.
        """
        params = []
        if start is not None:
            params.append("start=%f" % start)
        if end is not None:
            params.append("end=%f" % end)
        if limit:
            assert(limit > 0)
            params.append('limit=%d' % limit)
        if cursor is not None:
            params.append("cursor=%s" % cursor)
        if reverse:
            params.append('reverse=True')
        if event_types:
            for et in event_types:
                params.append("event_types=%s" % et)

        url = "/1/applications/%s/events?" % self.application_id
        url += "&".join(params)

        @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
        def get_next(url):
            resp = self._cc._get(url)
            return resp.json()

        count = 0
        while url:
            resp = get_next(url)
            for item in resp['data']:
                yield item
                count += 1
                if limit and count == limit:
                    return
            url = resp.get('paging', {}).get('next')

    ##
    #  consensus_history
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def consensus_history(self, start=None, end=None, limit=None, subject_uid=None):
        """
        Return consensus-history counts for this application's output subjects.

        start (float)      filter by timestamp > start (seconds since epoch)
        end (float)        filter by timestamp < end   (seconds since epoch)
        limit (int)        maximum number of history points to return
        subject_uid (str)  optionally restrict to a single subject

        See GET /1/applications/{app_id}/consensusHistory.
        """
        params = {}
        if start is not None:
            params['start'] = start
        if end is not None:
            params['end'] = end
        if limit is not None:
            params['limit'] = limit
        if subject_uid is not None:
            params['subject_uid'] = subject_uid
        resp = self._cc._get("/1/applications/%s/consensusHistory" % self.application_id, params=params)
        return resp.json()

    def _performance(self, kind, start=None, end=None, limit=None, reverse=False, duration=None):
        """Shared helper for the performance/* endpoints."""
        params = {}
        if start is not None:
            params['start'] = start
        if end is not None:
            params['end'] = end
        if limit is not None:
            params['limit'] = limit
        if reverse:
            params['reverse'] = True
        if duration is not None:
            params['duration'] = duration
        resp = self._cc._get("/1/applications/%s/performance/%s" % (self.application_id, kind), params=params)
        return resp.json()

    ##
    #  performance_current_validation
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def performance_current_validation(self, start=None, end=None, limit=None, reverse=False, duration=None):
        """
        Return the current-validation performance series for this application.

        See GET /1/applications/{app_id}/performance/currentValidation.
        """
        return self._performance('currentValidation', start=start, end=end, limit=limit,
                                 reverse=reverse, duration=duration)

    ##
    #  performance_release_validation
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def performance_release_validation(self, start=None, end=None, limit=None, reverse=False, duration=None):
        """
        Return the release-validation performance series for this application.

        See GET /1/applications/{app_id}/performance/releaseValidation.
        """
        return self._performance('releaseValidation', start=start, end=end, limit=limit,
                                 reverse=reverse, duration=duration)

    ##
    #  performance_new_random
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def performance_new_random(self, limit=None):
        """
        Return the new-random test-set performance for this application.

        See GET /1/applications/{app_id}/performance/newRandom.
        """
        params = {}
        if limit is not None:
            params['limit'] = limit
        resp = self._cc._get("/1/applications/%s/performance/newRandom" % self.application_id, params=params)
        return resp.json()

    ##
    #  model_performance
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def model_performance(self, subject_uid, consensus=None, reverse=False,
                          probability_lower=None, probability_upper=None,
                          limit=None, cursor=None, set_assignment='validation'):
        """
        Return model performance data for a given subject of this application.

        subject_uid (str):       required output subject_uid to evaluate
        consensus (str):         optional consensus filter
        reverse (bool):          reverse the sorting order
        probability_lower:       filter by probability > probability_lower
        probability_upper:       filter by probability < probability_upper
        limit (int):             maximum number of results
        cursor (str):            opaque pagination cursor
        set_assignment (str):    'validation' (default) or 'training'

        This is an asynchronous endpoint; if the evaluation job is still
        running the response is a dict like {'type': 'results_pending', ...}.

        See GET /1/applications/{app_id}/modelPerformance.
        """
        params = {'subject_uid': subject_uid, 'set_assignment': set_assignment}
        if consensus is not None:
            params['consensus'] = consensus
        if reverse:
            params['reverse'] = True
        if probability_lower is not None:
            params['probability_lower'] = probability_lower
        if probability_upper is not None:
            params['probability_upper'] = probability_upper
        if limit is not None:
            params['limit'] = limit
        if cursor is not None:
            params['cursor'] = cursor
        resp = self._cc._get("/1/applications/%s/modelPerformance" % self.application_id, params=params)
        return resp.json()

    ##
    #  push notifications
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def push_notifications(self, device_id=None, app_bundle_id=None, event_type=None):
        """
        Return the push-notification subscription status for a device on this
        application. The endpoint identifies the subscription by device, so
        device_id and app_bundle_id are required by the API.

        device_id (str):      device identifier
        app_bundle_id (str):  app bundle id
        event_type (str):     optional event type filter

        See GET /1/applications/{app_id}/pushNotifications.
        """
        params = {}
        if device_id is not None:
            params['device_id'] = device_id
        if app_bundle_id is not None:
            params['app_bundle_id'] = app_bundle_id
        if event_type is not None:
            params['event_type'] = event_type
        resp = self._cc._get("/1/applications/%s/pushNotifications" % self.application_id, params=params)
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def subscribe_push(self, device_id=None, app_bundle_id=None, event_type=None, unsubscribe=False):
        """
        Subscribe (or unsubscribe) a device to this application's event topic.

        device_id (str):      device identifier
        app_bundle_id (str):  iOS app bundle id
        event_type (str):     event type to (un)subscribe to
        unsubscribe (bool):   True to unsubscribe instead of subscribe

        See POST /1/applications/{app_id}/pushNotifications.
        """
        data = {}
        if device_id is not None:
            data['device_id'] = device_id
        if app_bundle_id is not None:
            data['app_bundle_id'] = app_bundle_id
        if event_type is not None:
            data['event_type'] = event_type
        if unsubscribe:
            data['unsubscribe'] = True
        resp = self._cc._post("/1/applications/%s/pushNotifications" % self.application_id, json=data)
        return resp.json()

    ##
    #  feedback
    ##
    def feedback(self, limit=None, cursor=None):
        """
        Yield this application's feedback requests, following pagination.

        limit (int)    yield maximum of limit results
        cursor (str)   opaque pagination cursor to resume from

        See GET /21/applications/{app_id}/feedbackRequests.
        """
        params = []
        if limit:
            assert(limit > 0)
            params.append('limit=%d' % min(limit, 100))
        if cursor is not None:
            params.append("cursor=%s" % cursor)

        url = "/21/applications/%s/feedbackRequests?" % self.application_id
        url += "&".join(params)

        @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
        def get_next(url):
            resp = self._cc._get(url)
            return resp.json()

        count = 0
        while url:
            resp = get_next(url)
            data = resp['data'] if isinstance(resp, dict) and 'data' in resp else resp
            for item in data:
                yield item
                count += 1
                if limit and count == limit:
                    return
            url = resp.get('paging', {}).get('next') if isinstance(resp, dict) else None

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def feedback_request(self, feedback_id):
        """
        Return a single feedback request for this application.

        See GET /21/applications/{app_id}/feedbackRequests/{feedback_id}.
        """
        resp = self._cc._get("/21/applications/%s/feedbackRequests/%s" % (self.application_id, feedback_id))
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def submit_feedback(self, body):
        """
        Submit feedback for a feedback request.

        body (dict):  SubmitFeedbackRequest body

        See POST /21/applications/{app_id}/feedback.
        """
        resp = self._cc._post("/21/applications/%s/feedback" % self.application_id, json=body)
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def feedback_request_count(self):
        """
        Return the count of feedback requests pending for the requesting user.

        See GET /21/applications/{app_id}/feedbackRequests/count.
        """
        resp = self._cc._get("/21/applications/%s/feedbackRequests/count" % self.application_id)
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def pending_feedback_requests(self, limit=1):
        """
        Return pending (unsatisfied) feedback requests for the caller.

        See GET /21/applications/{app_id}/feedbackRequests/pending.
        """
        resp = self._cc._get("/21/applications/%s/feedbackRequests/pending?limit=%d" % (self.application_id, limit))
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def purge_feedback(self):
        """
        Purge feedback requests for this application.

        See POST /1/applications/{app_id}/feedback/purge.
        """
        self._cc._post("/1/applications/%s/feedback/purge" % self.application_id)

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def delete_feedback_requests(self):
        """
        Delete all feedback requests for this application.

        See DELETE /21/applications/{app_id}/feedbackRequests.
        """
        resp = self._cc._delete("/21/applications/%s/feedbackRequests" % self.application_id)
        try:
            return resp.json()
        except Exception:
            return None

    ##
    #  evaluation metrics (configuration; versioned /22/)
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def create_evaluation_metric(self, body):
        """
        Create an evaluation metric for this application.

        body (dict):  PostEvaluationMetricRequest body

        See POST /22/applications/{application_id}/evaluation_metrics.
        """
        resp = self._cc._post("/22/applications/%s/evaluation_metrics" % self.application_id, json=body)
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def register_default_evaluation_metric(self, body=None):
        """
        Register the default evaluation metric for a newly-created application.

        See POST /22/applications/{application_id}/evaluation_metrics/register_new_app_default.
        """
        resp = self._cc._post(
            "/22/applications/%s/evaluation_metrics/register_new_app_default" % self.application_id,
            json=body if body is not None else {})
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def copy_evaluation_metrics(self, target_application_id, body=None):
        """
        Copy this application's evaluation metrics into a target application.

        target_application_id (str):  destination application_id (sent in the body)

        This application is the *source*; see
        POST /22/applications/{source_application_id}/evaluation_metrics/copy.
        """
        data = dict(body) if body else {}
        data.setdefault('target_application_id', target_application_id)
        resp = self._cc._post("/22/applications/%s/evaluation_metrics/copy" % self.application_id, json=data)
        return resp.json()

    ##
    #  consensus releases (versioned /22/)
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def consensus_releases(self):
        """
        List consensus releases for this application.

        See GET /22/applications/{app_id}/consensus_release.
        """
        resp = self._cc._get("/22/applications/%s/consensus_release" % self.application_id)
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def consensus_release(self, consensus_release_id):
        """
        Return metadata/statistics for a single consensus release.

        See GET /22/applications/{app_id}/consensus_release/{consensus_release_id}.
        """
        resp = self._cc._get("/22/applications/%s/consensus_release/%s" % (self.application_id, consensus_release_id))
        return resp.json()

    def consensus_release_items(self, consensus_release_id, limit=None, cursor=None):
        """
        Yield the consensus items for a consensus release, following pagination.

        limit (int)    yield maximum of limit results
        cursor (str)   opaque pagination cursor to resume from

        See GET /22/applications/{app_id}/consensus_release/{consensus_release_id}/consensus_items.
        """
        return self._paged_release_items(consensus_release_id, 'consensus_items', limit, cursor)

    def consensus_release_upstream_assertions(self, consensus_release_id, limit=None, cursor=None):
        """
        Yield the upstream assertions for a consensus release, following pagination.

        limit (int)    yield maximum of limit results
        cursor (str)   opaque pagination cursor to resume from

        See GET /22/applications/{app_id}/consensus_release/{consensus_release_id}/upstream_assertions.
        """
        return self._paged_release_items(consensus_release_id, 'upstream_assertions', limit, cursor)

    def _paged_release_items(self, consensus_release_id, kind, limit=None, cursor=None):
        """Shared generator draining a paged consensus_release sub-collection."""
        params = []
        if limit:
            assert(limit > 0)
            params.append('limit=%d' % min(limit, 100))
        if cursor is not None:
            params.append("cursor=%s" % cursor)

        url = "/22/applications/%s/consensus_release/%s/%s?" % (self.application_id, consensus_release_id, kind)
        url += "&".join(params)

        @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
        def get_next(url):
            resp = self._cc._get(url)
            return resp.json()

        count = 0
        while url:
            resp = get_next(url)
            data = resp['data'] if isinstance(resp, dict) and 'data' in resp else resp
            for item in data:
                yield item
                count += 1
                if limit and count == limit:
                    return
            url = resp.get('paging', {}).get('next') if isinstance(resp, dict) else None

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def consensus_detection_release(self):
        """
        Return combined consensus detections for this application's output subjects.

        See GET /22/applications/{app_id}/consensus_detection_release.
        """
        resp = self._cc._get("/22/applications/%s/consensus_detection_release" % self.application_id)
        return resp.json()

    ##
    #  labeling embedding model helpers (media-embedding; versioned /22/)
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def labeling_image_encoder(self, body):
        """
        Get an image embedding from this application's labeling image-encoder model.

        body (dict):  GetAppMediaEmbeddingRequest body (e.g. {'media_id': ..., 'focus': {...}})

        See POST /22/applications/{app_id}/labelingImageEncoderModel.
        """
        resp = self._cc._post("/22/applications/%s/labelingImageEncoderModel" % self.application_id, json=body)
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def labeling_mask_decoder(self, filep=None):
        """
        Retrieve this application's labeling mask-decoder model (ONNX).

        filep:  open file object (wb) to write the model into; if None the raw
                bytes are returned.

        See GET /22/applications/{application_id}/labelingMaskDecoderModel.
        """
        resp = self._cc._get("/22/applications/%s/labelingMaskDecoderModel" % self.application_id)
        if filep is None:
            return resp.content
        filep.write(resp.content)

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def labeling_mask_decoder_head(self):
        """
        Return the response headers for this application's labeling mask-decoder
        model without downloading the body (HEAD request).

        See HEAD /22/applications/{application_id}/labelingMaskDecoderModel.
        """
        resp = self._cc._head("/22/applications/%s/labelingMaskDecoderModel" % self.application_id)
        return dict(resp.headers)

    def usage(self, start, end):
        """
        yield sparse app usage records in order between start and end epoch times
        """
        url = "/1/usage/app/%s?start=%d&end=%d" % (self.application_id, start, end)

        @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.005), retry=retry_if_exception(server_error))
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
