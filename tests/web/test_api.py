"""API integration tests exercise real persistence and the existing CLI subprocess."""
import json
import time
from pathlib import Path
from unittest.mock import Mock
import pytest
pytest.importorskip('fastapi')
from fastapi.testclient import TestClient
from openpyxl import Workbook
from chemflow.web.server import create_app
from chemflow.web.storage import confined, preview
from chemflow.web.schema import build_arguments, schema
from chemflow.web.updates import UpdateChecker
from fastapi import HTTPException

PASSWORD = 'chemflow-test-password'

@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path / 'workspace', PASSWORD, ['testserver'], run_worker=False, check_updates=False)

@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client

@pytest.fixture
def logged(client):
    response = client.post('/api/login', json={'password': PASSWORD})
    assert response.status_code == 200
    client.headers['x-csrf-token'] = response.json()['csrf']
    return client


def test_auth_csrf_and_logout(client):
    assert client.get('/api/jobs').status_code == 401
    assert client.post('/api/login', json={'password':'wrong'}).status_code == 401
    r=client.post('/api/login',json={'password':PASSWORD})
    assert 'HttpOnly' in r.headers['set-cookie'] and 'SameSite=strict' in r.headers['set-cookie']
    assert client.get('/api/session').status_code==200
    assert client.post('/api/jobs',json={'command':'init'}).status_code==403
    client.headers['x-csrf-token']=r.json()['csrf']
    assert client.post('/api/logout').status_code==200
    assert client.get('/api/jobs').status_code==401


def test_origin_host_and_headers(logged):
    assert logged.get('/api/jobs',headers={'host':'evil.example'}).status_code==400
    assert logged.post('/api/jobs',json={'command':'init'},headers={'origin':'https://evil.example'}).status_code==403
    r=logged.get('/api/jobs')
    assert r.headers['x-content-type-options']=='nosniff'
    assert "object-src 'none'" in r.headers['content-security-policy']
    assert r.headers['cache-control']=='no-store'


def test_rate_limit(client):
    for _ in range(10):
        assert client.post('/api/login',json={'password':'wrong'}).status_code==401
    assert client.post('/api/login',json={'password':PASSWORD}).status_code==429


def test_expired_session(logged,app):
    for key,(csrf,_) in app.state.auth.sessions.items():
        app.state.auth.sessions[key]=(csrf,0)
    assert logged.get('/api/jobs').status_code==401


def test_schema_tracks_cli(logged):
    s=logged.get('/api/schema').json()
    assert s['version']=='3.0.0'
    assert set(s['commands'])=={'init','run','resume','similarity','gcms','interactions'}
    options=s['commands']['run']
    assert any(o['name']=='rmsd_only' for o in options)
    assert any(o['name']=='vina_executable' and o['kind']=='tool' for o in options)
    assert len(options)>45


def test_upload_validation_and_binding(logged,app):
    assert logged.post('/api/uploads?filename=evil.exe',content=b'payload').status_code==422
    assert logged.post('/api/uploads?filename=empty.csv',content=b'').status_code==422
    r=logged.post('/api/uploads?filename=ligands.csv',content=b'name,smiles\nEthanol,CCO')
    assert r.status_code==201
    upload=r.json()
    assert app.state.manager.resolve_input(upload['id']).read_bytes().startswith(b'name')
    assert len(logged.get('/api/uploads').json())==1
    assert logged.post('/api/jobs',json={'command':'run','options':{'ligands':upload['id'],'receptors':'../../secret.xlsx'}}).status_code==400


def test_upload_limit(logged,monkeypatch):
    monkeypatch.setattr('chemflow.web.server.MAX_UPLOAD',5)
    assert logged.post('/api/uploads?filename=data.csv',content=b'123456').status_code==413
    assert logged.get('/api/uploads').json()==[]

@pytest.mark.parametrize('options',[{'vina_executable':'evil.exe'},{'result_filename':'../../escape.xlsx'},{'result_filename':'C:\\escape.xlsx'},{'dpi':'nan'},{'figure_formats':['png','html']}])
def test_unsafe_options_rejected(logged,options):
    source=logged.post('/api/jobs',json={'command':'init','options':{'skip_check':True}}).json()['id']
    r=logged.post('/api/jobs',json={'command':'similarity','source_run':source,'options':options})
    assert r.status_code==422


def test_jobs_cancel_and_shared_output(logged,app):
    root=logged.post('/api/jobs',json={'command':'init','name':'Templates','options':{'skip_check':True}}).json()['id']
    assert logged.get('/api/jobs').json()[0]['status']=='queued'
    assert logged.post(f'/api/jobs/{root}/cancel').status_code==200
    assert logged.post(f'/api/jobs/{root}/cancel').status_code==409
    child=logged.post('/api/jobs',json={'command':'resume','source_run':root}).json()['id']
    assert app.state.manager.output(root)==app.state.manager.output(child)
    assert logged.post('/api/jobs',json={'command':'resume'}).status_code==422


def test_artifacts_download_table_traversal(logged,app):
    job=logged.post('/api/jobs',json={'command':'init'}).json()['id']
    out=app.state.manager.output(job);out.mkdir()
    (out/'table.csv').write_text('ligand,score\nEthanol,-4.1')
    (out/'unsafe.svg').write_text('<svg onload="alert(1)"/>')
    r=logged.get(f'/api/jobs/{job}/artifacts');assert len(r.json())==2
    r=logged.get(f'/api/jobs/{job}/preview',params={'path':'table.csv'})
    assert r.json()['rows'][1]==['Ethanol','-4.1']
    r=logged.get(f'/api/jobs/{job}/file',params={'path':'unsafe.svg','download':'false'})
    assert r.headers['content-disposition'].startswith('attachment')
    assert logged.get(f'/api/jobs/{job}/file',params={'path':'../../../jobs.sqlite3'}).status_code==400
    assert logged.get(f'/api/jobs/{job}/file',params={'path':'missing.png'}).status_code==404


def test_workbook_preview_sheets_and_bounds(tmp_path):
    path=tmp_path/'results.xlsx';wb=Workbook();ws=wb.active;ws.title='Docking';ws.append(['name','score'])
    for i in range(250):ws.append([f'L{i}',-7.2])
    wb.create_sheet('Interactions').append(['residue','distance']);wb.save(path)
    p=preview(path);assert p['truncated'] and len(p['rows'])==201
    assert p['sheets']==['Docking','Interactions']
    assert preview(path,'Interactions')['sheet']=='Interactions'
    with pytest.raises(HTTPException):preview(path,'missing')


def test_confinement(tmp_path):
    for name in ('../secret','/etc/passwd',str(tmp_path)):
        with pytest.raises(HTTPException):confined(tmp_path,name)


def test_browser_interactive_and_argument_boundaries(tmp_path):
    argv=build_arguments('run',{'ligands':'a','receptors':'b','seed':-12,'similarity':False},tmp_path,lambda x:tmp_path/x)
    assert '--no-interactive-gridbox' not in argv and '--no-pubchem-interactive-fallback' not in argv
    assert '--admet-ssl-verify' in argv and '--no-similarity' in argv
    assert '-12' in argv


def test_receptor_workbook(logged,app):
    r=logged.post('/api/receptors',json={'rows':[{'pdb_code':'1HSG','center':[1,2,3],'size':[20,22,24]}]})
    assert r.status_code==200
    assert app.state.manager.resolve_input(r.json()['id']).is_file()
    assert logged.post('/api/receptors',json={'rows':[{'pdb_code':'1HSG','center':[1,2,3],'size':[0,20,20]}]}).status_code==422
    assert logged.get('/api/receptors/BAD').status_code in (404,422)


def test_resource_monitor(logged):
    r=logged.get('/api/resources');assert r.status_code==200
    data=r.json();assert 0<=data['cpu']<=100 and data['ram_total']>0 and data['disk_free']>0


def test_updates_cached_and_network_failure(monkeypatch):
    response=Mock();response.json.return_value={'tag_name':'v99.0.0'}
    get=Mock(return_value=response);monkeypatch.setattr('chemflow.web.updates.requests.get',get)
    monkeypatch.setattr('chemflow.web.updates.source_revision',lambda:None)
    checker=UpdateChecker();assert checker.check()['status']=='available'
    checker.check();assert get.call_count==1
    import requests
    get.side_effect=requests.ConnectionError('offline')
    assert checker.check(force=True)['status']=='unavailable'


def test_cli_subprocess_end_to_end(tmp_path):
    app=create_app(tmp_path/'real',PASSWORD,['testserver'],check_updates=False)
    with TestClient(app) as client:
        csrf=client.post('/api/login',json={'password':PASSWORD}).json()['csrf'];client.headers['x-csrf-token']=csrf
        job=client.post('/api/jobs',json={'command':'init','name':'Real template job','options':{'skip_check':True}}).json()['id']
        deadline=time.monotonic()+90
        while time.monotonic()<deadline:
            data=client.get('/api/jobs').json()[0]
            if data['status'] not in ('queued','running'):break
            time.sleep(.25)
        assert data['status']=='succeeded',client.get(f'/api/jobs/{job}/logs').json()
        files=client.get(f'/api/jobs/{job}/artifacts').json()
        assert len([f for f in files if f['extension']=='.xlsx'])==3
        assert 'Template Excel' in client.get(f'/api/jobs/{job}/logs').json()['text']
        p=client.get(f'/api/jobs/{job}/preview',params={'path':files[0]['path']})
        assert p.json()['kind']=='table'
        assert client.get(f'/api/jobs/{job}/file',params={'path':files[0]['path']}).content.startswith(b'PK')

def test_recovery_and_workspace_exclusivity(tmp_path):
    from chemflow.web.jobs import JobManager
    a=JobManager(tmp_path/'work')
    job=a.create('init',{'skip_check':True},'Interrupted')
    with a.connection() as db:db.execute("UPDATE jobs SET status='running' WHERE id=?",(job,))
    a.start()
    try:
        assert a.get(job)['status']=='interrupted'
        b=JobManager(tmp_path/'work')
        with pytest.raises(RuntimeError,match='server lain'):b.start()
        assert a.get(job)['status']=='interrupted'
    finally:a.close()


def test_import_cli_run_preserves_source(tmp_path):
    from chemflow.web.jobs import JobManager
    legacy=tmp_path/'legacy';legacy.mkdir();(legacy/'scores.csv').write_text('name,score\nA,-6')
    manager=JobManager(tmp_path/'managed')
    job=manager.import_run(legacy)
    assert manager.get(job)['status']=='imported'
    assert (manager.output(job)/'scores.csv').read_bytes()==(legacy/'scores.csv').read_bytes()
    assert manager.get(job)['output']!=str(legacy)
    with pytest.raises(ValueError):manager.import_run(tmp_path)
    with pytest.raises(ValueError):manager.import_run(manager.workspace/"runs")


def test_process_tree_cancellation(tmp_path):
    import subprocess,sys,psutil
    from chemflow.web.jobs import JobManager
    manager=JobManager(tmp_path/'cancel')
    job=manager.create('init',{},'Cancellation')
    pid_file=tmp_path/'child.pid'
    code="import subprocess,sys,time;from pathlib import Path;p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(90)']);Path(sys.argv[1]).write_text(str(p.pid));time.sleep(90)"
    proc=subprocess.Popen([sys.executable,'-c',code,str(pid_file)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    manager.process=proc;manager.active_id=job
    with manager.connection() as db:db.execute("UPDATE jobs SET status='running' WHERE id=?",(job,))
    try:
        deadline=time.monotonic()+10
        while not pid_file.exists() and time.monotonic()<deadline:time.sleep(.05)
        assert pid_file.exists()
        child_pid=int(pid_file.read_text())
        manager.cancel(job)
        assert manager.get(job)['status']=='cancelled'
        assert proc.wait(timeout=5)!=0
        assert not psutil.pid_exists(child_pid) or psutil.Process(child_pid).status()==psutil.STATUS_ZOMBIE
    finally:
        if proc.poll() is None:proc.kill()
        manager.close()


def test_symlink_escape_rejected(tmp_path):
    outside=tmp_path/'outside';outside.mkdir();(outside/'secret.txt').write_text('secret')
    root=tmp_path/'root';root.mkdir()
    try:(root/'link').symlink_to(outside,target_is_directory=True)
    except OSError:pytest.skip('Creating symlinks requires platform permission')
    with pytest.raises(HTTPException):confined(root,'link/secret.txt')


def test_source_commit_check_reports_difference(monkeypatch):
    monkeypatch.setattr('chemflow.web.updates.source_revision',lambda:'a'*40)
    release=Mock();release.json.return_value={'tag_name':'v3.0.0'}
    commit=Mock();commit.json.return_value={'sha':'b'*40}
    get=Mock(side_effect=[release,commit]);monkeypatch.setattr('chemflow.web.updates.requests.get',get)
    value=UpdateChecker().check()
    assert value['status']=='current' and value['source_status']=='different'
    assert value['source_local']=='a'*40 and get.call_count==2


def test_generated_argv_is_accepted_by_cli_parser(tmp_path):
    """Argv bentukan server harus lolos parser CLI asli untuk setiap perintah WebUI."""
    from chemflow.cli import build_parser
    from chemflow.web.schema import COMMANDS, build_arguments
    minimal={'init':{}, 'run':{'receptors':'r.xlsx','ligands':'l.xlsx'}, 'resume':{}, 'similarity':{}, 'gcms':{'data':['a.txt']}, 'interactions':{}}
    for command in COMMANDS:
        argv=build_arguments(command, minimal[command], tmp_path, lambda value: tmp_path/value)
        build_parser().parse_args(argv)
