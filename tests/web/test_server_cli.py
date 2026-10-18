"""Web launch configuration checks do not open a network listener."""
from unittest.mock import Mock
import pytest
pytest.importorskip('fastapi')
from chemflow.cli import build_parser
from chemflow.web.server import serve


def test_explicit_remote_host_and_proxy(monkeypatch,tmp_path):
    from types import SimpleNamespace
    configs=[];run=Mock()
    def server(config):configs.append(config);return SimpleNamespace(run=run)
    monkeypatch.setattr('uvicorn.Server',server)
    monkeypatch.setenv('CHEMFLOW_WEB_PASSWORD','operator-test-password')
    args=build_parser().parse_args(['web','--host','0.0.0.0','--workspace',str(tmp_path),'--allowed-host','chemflow.example.com','--secure-cookie','--trusted-proxy','172.17.0.1'])
    assert serve(args)==0
    config=configs[0]
    assert config.host=='0.0.0.0' and config.workers==1
    assert config.timeout_graceful_shutdown==10
    assert config.forwarded_allow_ips=='127.0.0.1,::1,172.17.0.1'
    run.assert_called_once()



@pytest.mark.parametrize('flag,value',[('--allowed-host','*'),('--trusted-proxy','*')])
def test_reject_wildcard_trust(monkeypatch,tmp_path,flag,value):
    run=Mock();monkeypatch.setattr('uvicorn.run',run)
    monkeypatch.setenv('CHEMFLOW_WEB_PASSWORD','operator-test-password')
    args=build_parser().parse_args(['web','--workspace',str(tmp_path),flag,value])
    assert serve(args)==1
    run.assert_not_called()


def test_short_server_password_rejected(monkeypatch,tmp_path):
    monkeypatch.setenv('CHEMFLOW_WEB_PASSWORD','short')
    run=Mock();monkeypatch.setattr('uvicorn.run',run)
    args=build_parser().parse_args(['web','--workspace',str(tmp_path)])
    assert serve(args)==1
    run.assert_not_called()

def test_imported_resume_accepts_browser_inputs_and_verifies_tls(monkeypatch,tmp_path):
    from types import SimpleNamespace
    from chemflow.cli import main
    from chemflow.web.schema import build_arguments
    monkeypatch.setenv("CHEMFLOW_PROMPT_DIR",str(tmp_path/"prompts"))
    cfg=SimpleNamespace(interactive_gridbox=False,interactive_pubchem_fallback=False,admet_ssl_verify=False)
    state=Mock();state.load_config.return_value=cfg;state.read_progress.return_value={}
    monkeypatch.setattr('chemflow.state.RunState',lambda output:state)
    pipeline=Mock();pipeline.return_value.run.return_value=0
    monkeypatch.setattr('chemflow.cli.Pipeline',pipeline)
    argv=build_arguments('resume',{},tmp_path,lambda path:path)
    assert main(argv)==0
    assert cfg.interactive_gridbox is True
    assert cfg.interactive_pubchem_fallback is True
    assert cfg.admet_ssl_verify is True
