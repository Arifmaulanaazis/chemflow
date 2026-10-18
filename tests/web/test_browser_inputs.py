"""Structured browser answers round-trip through the actual CLI prompt bridge."""
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient
from chemflow.web.server import create_app
from chemflow.web.schema import build_arguments, schema, BLOCKED, parsers, COMMANDS
from chemflow.web.prompts import validate_answer
from fastapi import HTTPException

@pytest.fixture
def context(tmp_path, monkeypatch):
    app=create_app(tmp_path,"browser-test-password",["testserver"],run_worker=False,check_updates=False)
    manager=app.state.manager
    job=manager.create("init",{},"Input bridge")
    with manager.connection() as db: db.execute("UPDATE jobs SET status='running' WHERE id=?",(job,))
    monkeypatch.setenv("CHEMFLOW_PROMPT_DIR",str(tmp_path/"prompts"/job))
    with TestClient(app) as client:
        csrf=client.post("/api/login",json={"password":"browser-test-password"}).json()["csrf"]
        client.headers["x-csrf-token"]=csrf
        yield app,client,job


def wait_input(client,job):
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        values=client.get(f"/api/jobs/{job}/inputs").json()
        if values:return values[0]
        time.sleep(.05)
    pytest.fail("No prompt from scientific child")


def test_smiles_prompt_roundtrip_validation_replay(context):
    from chemflow.chem.pubchem_client import prompt_manual_smiles
    app,client,job=context; result=[]
    thread=threading.Thread(target=lambda:result.append(prompt_manual_smiles("Ethanol")),daemon=True);thread.start()
    prompt=wait_input(client,job);url=f"/api/jobs/{job}/inputs/{prompt['id']}"
    assert prompt["compound"]=="Ethanol"
    assert client.get('/api/jobs').json()[0]['pending_input'] is True
    assert client.post(url,json={"smiles":"not-valid"}).status_code==422
    assert thread.is_alive()
    assert client.post(url,json={"smiles":"CCO"},headers={"x-csrf-token":"wrong"}).status_code==403
    assert client.post(url,json={"smiles":"CCO"}).status_code==200
    assert client.post(url,json={"smiles":"CCC"}).status_code==409
    thread.join(5); assert result==["CCO"]
    assert client.get(f"/api/jobs/{job}/inputs").json()==[]


def test_native_gridbox_roundtrip(context):
    from chemflow.io.pdb_fetcher import interactive_select_native_ligand
    app,client,job=context; result=[]
    ligand=SimpleNamespace(label="LIG A 1",atom_count=4,center_x=1,center_y=2,center_z=3,extent=5)
    receptor=SimpleNamespace(pdb_code="1HSG",native_ligands=[ligand])
    thread=threading.Thread(target=lambda:result.append(interactive_select_native_ligand(receptor)),daemon=True);thread.start()
    prompt=wait_input(client,job)
    assert prompt["choices"][0]["center"]==[1,2,3]
    url=f"/api/jobs/{job}/inputs/{prompt['id']}"
    reply={"native":"LIG A 1","center":[-1,2,3],"size":[22,23,24]}
    assert client.post(url,json={**reply,"size":[0,20,20]}).status_code==422
    assert client.post(url,json=reply).status_code==200
    thread.join(5); assert result[0]==(-1,2,3,22,23,24,ligand)


def test_manual_grid_and_skip(context):
    app,client,job=context
    from chemflow.interaction.web_prompt import request
    result=[];thread=threading.Thread(target=lambda:result.append(request("smiles","Skip this")),daemon=True);thread.start()
    p=wait_input(client,job)
    assert client.post(f"/api/jobs/{job}/inputs/{p['id']}",json={"smiles":""}).status_code==200
    thread.join(5); assert result==[{"smiles":""}]
    assert validate_answer({"kind":"gridbox","choices":[]},{"native":"manual","center":[0,0,0],"size":[20,20,20]})["native"]=="manual"

@pytest.mark.parametrize('answer',[{"center":[True,0,0],"size":[20,20,20]},{"center":[0,0],"size":[20,20,20]},{"center":[0,0,0],"size":[201,20,20]},{"center":[float('inf'),0,0],"size":[20,20,20]},{"center":[0,0,0],"size":[20,20,20],"native":"unknown"}])
def test_grid_rejects_invalid_answers(answer):
    with pytest.raises(HTTPException):validate_answer({"kind":"gridbox","choices":[]},answer)


def test_stopped_jobs_cannot_be_answered(context):
    app,client,job=context
    with app.state.manager.connection() as db: db.execute("UPDATE jobs SET status='cancelled' WHERE id=?",(job,))
    assert client.get(f"/api/jobs/{job}/inputs").json()==[]
    assert client.post(f"/api/jobs/{job}/inputs/anything",json={}).status_code==409
    assert client.get('/api/jobs/missing/inputs').status_code==404


def test_ligand_workbook_is_readable_and_validated(context):
    from chemflow.io.excel_ligands import read_ligands
    from openpyxl import load_workbook
    app,client,job=context
    response=client.post('/api/ligands',json={"rows":[{"name":"Ethanol","smiles":"CCO","group":"A"},{"name":"=Formula","smiles":"","group":"B"}]})
    assert response.status_code==200
    path=app.state.manager.resolve_input(response.json()['id'])
    records=read_ligands(path);assert len(records)==2 and records[0].smiles=='CCO' and records[1].needs_pubchem_lookup
    assert load_workbook(path).active['A3'].data_type=='s'
    assert client.post('/api/ligands',json={"rows":[{"name":"Bad","smiles":"invalid"}]}).status_code==422
    assert client.post('/api/ligands',json={"rows":[]}).status_code==422


def test_all_scientific_cli_arguments_are_exposed_and_optouts_work(tmp_path):
    exposed=schema()
    for command in COMMANDS:
        actions={a.dest for a in parsers()[command]._actions if a.dest!='help'}
        assert actions == {o['name'] for o in exposed[command]} | (actions & BLOCKED)
    argv=build_arguments('run',{'ligands':'a','receptors':'b','no_interactive_gridbox':True,'no_pubchem_interactive_fallback':True},tmp_path,lambda x:tmp_path/x)
    assert '--no-interactive-gridbox' in argv and '--no-pubchem-interactive-fallback' in argv


def test_vina_versions_use_existing_manager_and_cache(context,monkeypatch):
    app,client,job=context
    remote=Mock(return_value=[SimpleNamespace(version='1.2.7',label='Vina 1.2.7')]);monkeypatch.setattr('chemflow.docking.vina_manager.VinaReleaseManager.list_compatible',remote)
    assert client.get('/api/vina-versions').json()[0]['version']=='1.2.7'
    assert client.get('/api/vina-versions').status_code==200
    assert remote.call_count==1


def test_registered_executable_ids_are_the_only_accepted_paths(tmp_path,monkeypatch):
    import os
    from chemflow.web.tools import registered_tools
    path=tmp_path/'vina-custom';path.write_text('test');path.chmod(0o755)
    monkeypatch.setenv('CHEMFLOW_WEB_VINA_EXECUTABLE',str(path))
    tools=registered_tools('vina_executable');tool=next(t for t in tools if t['path']==str(path.resolve()))
    argv=build_arguments('run',{'ligands':'a','receptors':'b','vina_executable':tool['id']},tmp_path,lambda v:tmp_path/v)
    assert argv[argv.index('--vina-executable')+1]==str(path.resolve())
    with pytest.raises(HTTPException):build_arguments('run',{'ligands':'a','receptors':'b','vina_executable':str(path)},tmp_path,lambda v:tmp_path/v)


def test_real_worker_child_waits_for_api_answer(tmp_path,monkeypatch):
    import subprocess,sys
    from chemflow.web import jobs
    original=subprocess.Popen
    captured=[]
    def spawn(argv,**kwargs):
        if argv[1:3]!=['-m','chemflow']:
            return original(argv,**kwargs)
        captured.append(kwargs['env'])
        script="from chemflow.chem.pubchem_client import prompt_manual_smiles; print('ANSWER='+str(prompt_manual_smiles('Ethanol')),flush=True)"
        return original([sys.executable,'-c',script],**kwargs)
    monkeypatch.setattr(jobs.subprocess,'Popen',spawn)
    monkeypatch.setenv('CHEMFLOW_WEB_PASSWORD','never-pass-to-child')
    app=create_app(tmp_path,'browser-test-password',['testserver'],check_updates=False)
    with TestClient(app) as client:
        csrf=client.post('/api/login',json={'password':'browser-test-password'}).json()['csrf'];client.headers['x-csrf-token']=csrf
        job=client.post('/api/jobs',json={'command':'init','options':{'skip_check':True}}).json()['id']
        p=wait_input(client,job)
        assert 'CHEMFLOW_WEB_PASSWORD' not in captured[0]
        assert captured[0]['CHEMFLOW_PROMPT_DIR']==str(tmp_path/'prompts'/job)
        assert client.post(f"/api/jobs/{job}/inputs/{p['id']}",json={'smiles':'CCO'}).status_code==200
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            if app.state.manager.get(job)['status']=='succeeded':break
            time.sleep(.05)
        assert app.state.manager.get(job)['status']=='succeeded'
        assert 'ANSWER=CCO' in app.state.manager.logs(job)
