from IPython.core.magic import (register_line_magic, register_cell_magic,
                                register_line_cell_magic)

import cogniac
from tabulate import tabulate
import datetime
import os

cc = None
S = None

try:
    username = os.environ['COG_USER']
    password = os.environ['COG_PASS']
except:
    print "No Cogniac Credentials. Specify username and password or set COG_USER and COG_PASS environment variables."
    os._exit(1)


def print_tenants(tenants):
    tenants.sort(key=lambda x: x['name'])
    data = [['tenant_id', 'name']]
    for tenant in tenants:
        data.append([tenant['tenant_id'], tenant['name']])
    print tabulate(data, headers='firstrow')


@register_line_magic
def tenants(line):
    tenants = cogniac.CogniacConnection.get_all_authorized_tenants(username, password)['tenants']
    print_tenants(tenants)
print "added %tenants ipython magic command"


class Subjects(object):
    def __init__(self):
        count = 0
        for subject in cc.get_all_subjects():
            key = subject.subject_uid.replace('-', '_')  # workaround for some unclean legacy subject_uid
            self.__setattr__(key, subject)
            count += 1
        print 'added', count, 'subjects'


@register_line_magic
def authenticate(tenant_id):
    """
    authenticate to the specified tenant_id
    store CogniacConnection in cc object
    load all Cogniac Subjects into S object
    """
    global cc
    global S
    print "Authenticating..."
    cc = cogniac.CogniacConnection(tenant_id=tenant_id)
    print cc.tenant
    print "Adding all subjects to S"
    S = Subjects()
    print "Type S.<tab> to autocomplete subjects"
print "added %authenticate ipython magic command"


def print_detections(detections):
    # remove None values from dict
    detections = [{k: v for k, v in d.iteritems() if v is not None} for d in detections]

    detections.sort(key=lambda x: x['created_at'])

    for d in detections:
        if 'activation' in d:
            del d['activation']
        value = datetime.datetime.fromtimestamp(d['created_at'])
        d['created_at'] = value.strftime('%Y-%m-%d %H:%M:%S')
    print tabulate(detections, headers='keys')


@register_line_magic
def media_detections(media_id):
    "print media detections for the specified media_id"
    try:
        media = cc.get_media(media_id)
    except:
        print "media_id %s not found" % media_id
        return
    print_detections(media.detections())
print "added %media_detections ipython magic command"


def print_subjects(media_subjects):
    subjects = [ms['subject'] for ms in media_subjects]
    subjects = [{k: v for k, v in s.iteritems() if v is not None} for s in subjects]
    subjects.sort(key=lambda x: x['updated_at'])
    for s in subjects:
        if 'timestamp' in s:
            del s['timestamp']
        value = datetime.datetime.fromtimestamp(s['updated_at'])
        s['updated_at'] = value.strftime('%Y-%m-%d %H:%M:%S')
    print tabulate(subjects, headers='keys')


@register_line_magic
def media_subjects(media_id):
    "print subject media associations for the specified media_id"
    try:
        media = cc.get_media(media_id)
    except:
        print "media_id %s not found" % media_id
        return

    print_subjects(media.subjects())
print "added %media_subjects ipython magic command"


if 'COG_TENANT' in os.environ:
    authenticate(os.environ['COG_TENANT'])
else:
    tenants("")
