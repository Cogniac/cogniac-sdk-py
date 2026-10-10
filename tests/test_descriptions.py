"""
Smoke tests (no credentials) for cogniac.descriptions and the `cogniac descriptions` CLI, against a
fake connection that records every write.
"""
import json

import pytest
import yaml

import cogniac.cli as cli
from cogniac import descriptions
from cogniac.cli import build_parser, _resolve_positional_ids
from cogniac.common import ClientError


class _Obj:
    """A live tenant, application or subject: attributes plus a recorded update()."""

    def __init__(self, writes, kind, key, **fields):
        self._writes, self._kind, self._key = writes, kind, key
        self.__dict__.update(fields)

    def update(self, body):
        self._writes.append((self._kind, self._key, body))
        self.__dict__.update(body)
        return body


class _Conn:
    def __init__(self):
        self.writes = []
        self.tenant = _Obj(self.writes, 'tenant', 'T1', tenant_id='T1', name='Tenant One', description='Old tenant.')
        self.apps = {'A1': _Obj(self.writes, 'applications', 'A1', application_id='A1', name='inspection',
                                description='Reject defects.', input_subjects=['S0'], output_subjects=['S1']),
                     'A2': _Obj(self.writes, 'applications', 'A2', application_id='A2', name='other',
                                description=None, input_subjects=[], output_subjects=['S2'])}
        self.subjects = {uid: _Obj(self.writes, 'subjects', uid, subject_uid=uid, name=uid.lower(), description=d)
                         for uid, d in (('S0', 'Input.'), ('S1', 'A reject.'), ('S2', None))}

    def get_tenant(self):
        return self.tenant

    def get_application(self, key):
        if key not in self.apps:
            raise ClientError("ClientError (404): not found", 404)
        return self.apps[key]

    def get_subject(self, key):
        if key not in self.subjects:
            raise ClientError("ClientError (404): not found", 404)
        return self.subjects[key]

    def get_all_applications(self):
        return list(self.apps.values())

    def get_all_subjects(self):
        return list(self.subjects.values())

    def _post(self, url, json=None):
        assert url == '/1/tenants/T1'
        self.writes.append(('tenant', 'T1', json))
        self.tenant.__dict__.update(json)


def _doc(**sections):
    doc = {'tenant': {'tenant_id': 'T1'}}
    doc.update(sections)
    return doc


@pytest.mark.parametrize('doc, problem', [
    ({}, 'tenant.tenant_id is missing'),
    (_doc(applications={'A1': {'name': 'x'}}), 'applications.A1: no description key'),
    (_doc(subjects={'S1': {'description': 'x' * 8001}}), 'over 8000'),
    (_doc(subjects={'S1': {'description': 3}}), 'not text'),
    (_doc(apps={}), 'unknown top-level key'),
])
def test_validate_rejects(doc, problem):
    with pytest.raises(descriptions.DescriptionsError, match=problem):
        descriptions.validate(doc)


def test_validate_accepts_empty_description_and_unlisted_entries():
    descriptions.validate(_doc(subjects={'S1': {'description': ''}}))
    descriptions.validate(_doc())


def test_plan_reports_only_differences_and_never_applies_names():
    conn = _Conn()
    doc = _doc(applications={'A1': {'name': 'renamed', 'description': 'Reject defects.'},
                             'A2': {'description': ''}},          # None live == "" in the file
               subjects={'S1': {'description': 'A part to reject.'}})
    result = descriptions.plan(conn, doc)
    assert result['changes'] == [{'section': 'subjects', 'id': 'S1', 'live': 'A reject.', 'file': 'A part to reject.'}]
    assert result['name_changes'] == [{'section': 'applications', 'id': 'A1', 'live': 'inspection', 'file': 'renamed'}]
    assert result['unchanged'] == 2
    assert conn.writes == []


def test_plan_includes_tenant_only_when_its_description_is_listed():
    conn = _Conn()
    assert descriptions.plan(conn, _doc())['changes'] == []
    doc = {'tenant': {'tenant_id': 'T1', 'description': 'New tenant.'}}
    assert descriptions.plan(conn, doc)['changes'] == [
        {'section': 'tenant', 'id': 'T1', 'live': 'Old tenant.', 'file': 'New tenant.'}]


def test_plan_rejects_unknown_ids_and_another_tenant():
    conn = _Conn()
    with pytest.raises(descriptions.DescriptionsError, match='applications.NOPE, subjects.GONE'):
        descriptions.plan(conn, _doc(applications={'NOPE': {'description': 'x'}}, subjects={'GONE': {'description': 'x'}}))
    with pytest.raises(descriptions.DescriptionsError, match='for tenant T2'):
        descriptions.plan(conn, {'tenant': {'tenant_id': 'T2'}})


def test_apply_writes_each_difference_once_and_is_idempotent():
    conn = _Conn()
    doc = {'tenant': {'tenant_id': 'T1', 'description': 'New tenant.'},
           'applications': {'A1': {'description': 'Reject parts with defects.'}, 'A2': {'description': ''}},
           'subjects': {'S1': {'description': ''}}}
    written = descriptions.apply(conn, doc)
    assert [(w['section'], w['id']) for w in written] == [('tenant', 'T1'), ('applications', 'A1'), ('subjects', 'S1')]
    assert conn.writes == [('tenant', 'T1', {'description': 'New tenant.'}),
                           ('applications', 'A1', {'description': 'Reject parts with defects.'}),
                           ('subjects', 'S1', {'description': ''})]   # "" clears it
    assert descriptions.apply(conn, doc) == []
    assert len(conn.writes) == 3


def test_export_application_ids_takes_their_input_and_output_subjects():
    doc = descriptions.export(_Conn(), application_ids=['A1'])
    assert doc['tenant'] == {'tenant_id': 'T1', 'name': 'Tenant One', 'description': 'Old tenant.'}
    assert list(doc['applications']) == ['A1']
    assert doc['subjects'] == {'S0': {'name': 's0', 'description': 'Input.'}, 'S1': {'name': 's1', 'description': 'A reject.'}}


def test_export_defaults_to_everything_and_round_trips_through_yaml():
    conn = _Conn()
    conn.subjects['S1'].description = 'Line one.\nLine two.\n'
    doc = descriptions.export(conn)
    assert sorted(doc['applications']) == ['A1', 'A2'] and sorted(doc['subjects']) == ['S0', 'S1', 'S2']
    assert doc['subjects']['S2']['description'] == ''      # unset is written as ""
    text = descriptions.dump(doc)
    assert 'description: |\n      Line one.\n      Line two.\n' in text   # multi-line as a literal block
    reread = yaml.safe_load(text)
    descriptions.validate(reread)
    assert reread == doc
    assert descriptions.plan(conn, reread)['changes'] == []


def test_export_refresh_keeps_the_listed_entries():
    conn = _Conn()
    doc = descriptions.export(conn, doc=_doc(subjects={'S2': {'description': 'stale'}}))
    assert doc['applications'] == {} and doc['subjects'] == {'S2': {'name': 's2', 'description': ''}}


# -- CLI --------------------------------------------------------------------

def _run(monkeypatch, argv, conn, tty=False, answer=None):
    monkeypatch.setattr(cli, 'get_connection', lambda args=None: conn)
    monkeypatch.setattr('sys.stdin.isatty', lambda: tty)
    if answer is not None:
        monkeypatch.setattr('builtins.input', lambda prompt='': answer)
    p = build_parser()
    ns = p.parse_args(argv)
    _resolve_positional_ids(p, ns)
    with pytest.raises(SystemExit) as e:
        ns.func(ns)
        raise SystemExit(0)
    return e.value.code


def _file(tmp_path, doc):
    path = tmp_path / 'descriptions-T1.yaml'
    path.write_text(yaml.safe_dump(doc))
    return str(path)


def test_cli_plan_exit_codes(monkeypatch, tmp_path, capsys):
    same = _file(tmp_path, _doc(applications={'A1': {'description': 'Reject defects.'}}))
    assert _run(monkeypatch, ['descriptions', 'plan', same], _Conn()) == 0
    differs = _file(tmp_path, _doc(applications={'A1': {'description': 'Reject parts.'}}))
    assert _run(monkeypatch, ['descriptions', 'plan', differs], _Conn()) == 2


def test_cli_plan_output(monkeypatch, tmp_path, capsys):
    path = _file(tmp_path, _doc(applications={'A1': {'description': 'Reject parts.'}}))
    _run(monkeypatch, ['descriptions', 'plan', path], _Conn())
    result = json.loads(capsys.readouterr().out)
    assert result['changes'] == [{'section': 'applications', 'id': 'A1', 'live': 'Reject defects.', 'file': 'Reject parts.'}]


def test_cli_rejects_invalid_file_and_tenant_mismatch(monkeypatch, tmp_path, capsys):
    bad = _file(tmp_path, _doc(subjects={'S1': {'name': 'x'}}))
    assert _run(monkeypatch, ['descriptions', 'plan', bad], _Conn()) == 1
    assert 'no description key' in capsys.readouterr().err
    ok = _file(tmp_path, _doc())
    assert _run(monkeypatch, ['--tenant', 'T2', 'descriptions', 'plan', ok], _Conn()) == 1
    assert 'is for tenant T1, not T2' in capsys.readouterr().err


def test_cli_apply_needs_yes_without_a_terminal(monkeypatch, tmp_path, capsys):
    conn = _Conn()
    path = _file(tmp_path, _doc(applications={'A1': {'description': 'Reject parts.'}}))
    assert _run(monkeypatch, ['descriptions', 'apply', path], conn) == 1
    assert '--yes' in capsys.readouterr().err and conn.writes == []
    assert _run(monkeypatch, ['descriptions', 'apply', path, '--yes'], conn) == 0
    assert conn.writes == [('applications', 'A1', {'description': 'Reject parts.'})]
    assert json.loads(capsys.readouterr().out)['written'][0]['id'] == 'A1'


@pytest.mark.parametrize('answer, writes', [('n', 0), ('y', 1)])
def test_cli_apply_prompts_on_a_terminal(monkeypatch, tmp_path, capsys, answer, writes):
    conn = _Conn()
    path = _file(tmp_path, _doc(applications={'A1': {'description': 'Reject parts.'}}))
    _run(monkeypatch, ['descriptions', 'apply', path], conn, tty=True, answer=answer)
    assert len(conn.writes) == writes


def test_cli_export_writes_default_file_and_refuses_to_overwrite(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    assert _run(monkeypatch, ['descriptions', 'export', '--application-id', 'A1'], _Conn()) == 0
    doc = descriptions.load(str(tmp_path / 'descriptions-T1.yaml'))
    assert list(doc['applications']) == ['A1'] and sorted(doc['subjects']) == ['S0', 'S1']
    assert _run(monkeypatch, ['descriptions', 'export'], _Conn()) == 1
    assert 'exists' in capsys.readouterr().err
