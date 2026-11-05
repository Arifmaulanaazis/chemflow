import json
import shutil
import io
import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from fastapi.testclient import TestClient
from chemflow.web.server import create_app

@pytest.fixture
def context(tmp_path,monkeypatch):
    monkeypatch.setenv("CHEMFLOW_UPDATE_HOME",str(tmp_path/"updater"))
    app=create_app(tmp_path/"workspace","interactive-test-password",["testserver"],run_worker=False,check_updates=False)
    with TestClient(app) as client:
        csrf=client.post('/api/login',json={'password':'interactive-test-password'}).json()['csrf'];client.headers['x-csrf-token']=csrf
        yield app,client


def test_packaged_materials_and_citations_are_authenticated(context):
    app,client=context
    assert len(client.get('/api/citations').json())==8
    bib=client.get('/api/citations/bibtex');assert '@misc{chemflow' in bib.text and '10.1021/acs.jcim.1c00203' in bib.text
    pdf=client.get('/api/library/guide/file');assert pdf.content.startswith(b'%PDF')
    ppt=client.get('/api/library/guide/file?format=pptx');assert ppt.content.startswith(b'PK')
    assert client.get('/api/library/nope/file').status_code==404
    assert client.get('/api/library/guide/file?format=exe').status_code==404
    client.post('/api/logout')
    for url in ['/api/library','/api/library/guide/file','/api/citations','/api/citations/bibtex']:
        assert client.get(url).status_code==401


def test_real_structure_native_coordinates_and_gridbox(context):
    app,client=context
    from chemflow.io.pdb_fetcher import fetch_pdb
    folder=app.state.manager.workspace/'receptor-cache';folder.mkdir()
    shutil.copy2(Path(__file__).resolve().parents[1]/'fixtures/1HSG.pdb',folder/'1HSG.pdb')
    fetched=fetch_pdb('1HSG',folder)
    result=client.get('/api/receptors/1HSG');assert result.status_code==200
    assert len(result.json()['ligands'])==len(fetched.native_ligands)>0
    for native,real in zip(result.json()['ligands'],fetched.native_ligands):
        assert native['center']==[real.center_x,real.center_y,real.center_z]
        assert 'hetero' in native['selection']
        coords=[[float(line[30:38]),float(line[38:46]),float(line[46:54])] for line in real.atom_lines]
        for point in coords:
            for axis in range(3):assert abs(point[axis]-native['center'][axis])<=native['size'][axis]/2
    structure=client.get('/api/receptors/1HSG/structure');assert structure.status_code==200 and b'HETATM' in structure.content
    assert client.get('/api/receptors/BAD/structure').status_code==422
    client.post('/api/logout');assert client.get('/api/receptors/1HSG/structure').status_code==401


def test_maintenance_only_when_idle_and_enqueue_is_blocked(context):
    app,client=context;m=app.state.manager
    job=m.create('init',{},'Queued')
    assert m.begin_maintenance() is False
    m.cancel(job)
    assert m.begin_maintenance() is True
    assert client.post('/api/jobs',json={'command':'init'}).status_code==503
    m.maintenance=False
    assert client.post('/api/jobs',json={'command':'init'}).status_code==201


def test_cli_citations_and_bibtex(capsys):
    from chemflow.cli import main
    assert main(['citations'])==0
    assert 'AutoDock Vina' in capsys.readouterr().out
    assert main(['citations','--format','bibtex'])==0
    value=capsys.readouterr().out
    assert value.startswith('@misc{chemflow') and 'doi =' in value


def test_update_state_is_visible_without_applying_release(context,monkeypatch):
    app,client=context
    monkeypatch.setattr(app.state.updates,'check',lambda:{'status':'current','current':'3.0.0'})
    value=client.get('/api/updates').json()
    assert value['automatic']['mode']=='automatic'
    assert client.get('/api/session').headers['X-ChemFlow-Version']=='3.1.0'


@pytest.mark.parametrize('success',[True,False])
def test_background_updater_restarts_only_after_verified_activation(tmp_path,monkeypatch,success):
    from threading import Event
    import time
    started=Event();restarted=Event()
    runtime=tmp_path/'managed-python'
    def install(self):
        started.set()
        return runtime if success else None
    monkeypatch.setattr('chemflow.auto_update.AutoUpdater.maybe_update',install)
    monkeypatch.setenv('CHEMFLOW_UPDATE_HOME',str(tmp_path/'updates'))
    app=create_app(tmp_path/'workspace','interactive-test-password',['testserver'],run_worker=False)
    monkeypatch.setattr(app.state.updates,'check',lambda:{'status':'available','latest':'9.9.9'})
    app.state.request_update_restart=restarted.set
    with TestClient(app):
        assert started.wait(3)
        if success:
            assert restarted.wait(3)
            assert app.state.update_runtime==runtime
            assert app.state.manager.maintenance
        else:
            deadline=time.monotonic()+3
            while app.state.manager.maintenance and time.monotonic()<deadline:time.sleep(.01)
            assert not app.state.manager.maintenance
            assert app.state.update_runtime is None
            assert not restarted.is_set()


def test_successful_multi_device_logins_do_not_consume_failed_password_budget(context):
    app,client=context
    for _ in range(14):assert client.post('/api/login',json={'password':'interactive-test-password'}).status_code==200
    for _ in range(10):assert client.post('/api/login',json={'password':'incorrect'}).status_code==401
    assert client.post('/api/login',json={'password':'incorrect'}).status_code==429


def test_live_stream_finishes_for_update_instead_of_blocking_restart(context):
    import asyncio
    from unittest.mock import AsyncMock
    app,client=context
    app.state.update_runtime=Path('verified-runtime')
    endpoint=next(route.endpoint for route in app.routes if route.path=='/api/events')
    async def read():
        response=await endpoint(SimpleNamespace(is_disconnected=AsyncMock(return_value=False)))
        return [chunk async for chunk in response.body_iterator]
    assert asyncio.run(read())==['event: updating\ndata: {}\n\n']
