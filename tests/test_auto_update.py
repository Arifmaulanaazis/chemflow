"""The update protocol uses local release fixtures; it never updates this checkout."""
import base64
import hashlib
import io
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path
from unittest.mock import Mock
import pytest
from chemflow.auto_update import AutoUpdater,version

@pytest.fixture
def updater(tmp_path,monkeypatch):
    monkeypatch.delenv('CHEMFLOW_SKIP_UPDATE',raising=False)
    monkeypatch.delenv('CHEMFLOW_AUTO_UPDATE',raising=False)
    monkeypatch.setattr('chemflow.auto_update.dirty_checkout',lambda:False)
    return AutoUpdater(tmp_path/'updates')


def test_version_validation_rejects_non_release_paths():
    assert version('v3.0.1')==(3,0,1)
    for bad in ['../main','main','v3.0.0;cmd','3.0.0-rc1']:
        with pytest.raises(ValueError):version(bad)


def test_dirty_checkout_is_never_replaced(updater,monkeypatch):
    monkeypatch.setattr('chemflow.auto_update.dirty_checkout',lambda:True)
    check=Mock();monkeypatch.setattr(updater,'check',check)
    assert updater.maybe_update() is None
    assert updater.state()['status']=='deferred'
    check.assert_not_called()


def test_disabled_and_worker_skip_network(updater,monkeypatch):
    check=Mock();monkeypatch.setattr(updater,'check',check)
    monkeypatch.setenv('CHEMFLOW_AUTO_UPDATE','0');assert updater.maybe_update() is None
    monkeypatch.delenv('CHEMFLOW_AUTO_UPDATE');monkeypatch.setenv('CHEMFLOW_SKIP_UPDATE','1');assert updater.maybe_update() is None
    check.assert_not_called()


def test_check_cache_and_no_downgrade(updater,monkeypatch):
    response=Mock();response.json.return_value={'tag_name':'v2.0.0'};get=Mock(return_value=response);monkeypatch.setattr('chemflow.auto_update.requests.get',get)
    assert updater.maybe_update() is None
    assert updater.state()['status']=='current'
    updater.check();assert get.call_count==1


def test_failed_install_keeps_active_pointer_and_has_retry_backoff(updater,monkeypatch):
    updater.write('active.json',{'version':'2.0.0'})
    monkeypatch.setattr(updater,'check',lambda force=False:{'tag_name':'v9.9.9'})
    stage=Mock(side_effect=RuntimeError('simulated installation failure'));monkeypatch.setattr(updater,'stage',stage)
    assert updater.maybe_update() is None
    assert updater.read('active.json')=={'version':'2.0.0'}
    assert updater.state()['status']=='failed'
    updater.maybe_update();assert stage.call_count==1

@pytest.mark.parametrize('url',['https://evil.example/chemflow.whl','https://github.com/Other/chemflow/releases/download/v9.9.9/chemflow-9.9.9-py3-none-any.whl','https://github.com/Arifmaulanaazis/chemflow/archive/refs/tags/../../main.zip'])
def test_download_only_from_fixed_official_release_urls(updater,tmp_path,url):
    with pytest.raises(ValueError):updater.download(url,tmp_path/'package')


def test_checksum_failure_does_not_activate(updater,tmp_path,monkeypatch):
    response=Mock();response.__enter__=lambda self:response;response.__exit__=lambda *args:None;response.iter_content.return_value=[b'bad payload']
    monkeypatch.setattr('chemflow.auto_update.requests.get',lambda *args,**kw:response)
    with pytest.raises(ValueError):updater.download('https://github.com/Arifmaulanaazis/chemflow/releases/download/v9.9.9/chemflow-9.9.9-py3-none-any.whl',tmp_path/'file','sha256:wrong')
    assert updater.read('active.json')=={}


def test_pointer_rejects_cache_escape(updater):
    updater.write('active.json',{'version':'9.9.9','directory':'../../outside'})
    assert updater.active() is None


def local_wheel(path):
    package={
      'chemflow/__init__.py':b'__version__="9.9.9"\n',
      'chemflow/cli.py':b'def main(): return 0\n',
      'chemflow/__main__.py':b'from chemflow import __version__;print(__version__)\n',
      'chemflow/web/__init__.py':b'',
      'chemflow/web/server.py':b'# fixture server module\n',
      'chemflow/web/static/index.html':b'<html>staged fixture</html>',
      'chemflow-9.9.9.dist-info/METADATA':b'Metadata-Version: 2.1\nName: chemflow\nVersion: 9.9.9\nProvides-Extra: web\n',
      'chemflow-9.9.9.dist-info/WHEEL':b'Wheel-Version: 1.0\nGenerator: update-test\nRoot-Is-Purelib: true\nTag: py3-none-any\n',
    }
    record=''.join(name+',sha256='+base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode()+','+str(len(data))+'\n' for name,data in package.items())
    package['chemflow-9.9.9.dist-info/RECORD']=(record+'chemflow-9.9.9.dist-info/RECORD,,\n').encode()
    with zipfile.ZipFile(path,'w') as z:
        for name,data in package.items():z.writestr(name,data)


def test_real_venv_install_probe_atomic_activation_and_launch(updater,tmp_path,monkeypatch):
    wheel=tmp_path/'chemflow-9.9.9-py3-none-any.whl';local_wheel(wheel)
    release={'tag_name':'v9.9.9','assets':[{'name':wheel.name,'browser_download_url':'https://github.com/Arifmaulanaazis/chemflow/releases/download/v9.9.9/'+wheel.name}]}
    monkeypatch.setattr(updater,'check',lambda force=False:release)
    monkeypatch.setattr(updater,'download',lambda url,path,digest=None:shutil.copy2(wheel,path))
    executable=updater.maybe_update()
    assert executable is not None,updater.state()
    assert updater.active()==executable
    assert updater.state()['status']=='ready'
    value=subprocess.check_output([str(executable),'-I','-m','chemflow'],timeout=30).decode().strip()
    assert value=='9.9.9'
    # Aktivasi memilih runtime bertahap; versi sumber/lingkungan tetap 3.1.0.
    import chemflow
    assert chemflow.__version__=='3.1.0'


def test_failed_stage_removes_only_unpublished_runtime(updater, monkeypatch):
    previous=updater.root/'versions'/'3.0.0-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
    previous.mkdir(parents=True);(previous/'keep.txt').write_text('keep')
    updater.write('active.json',{'version':'3.0.0','directory':previous.name})
    def fail(args, **kw):
        folder=Path(args[-1]);folder.mkdir();(folder/'partial').write_text('incomplete')
        raise RuntimeError('failed virtual environment')
    monkeypatch.setattr(updater,'command',fail)
    with pytest.raises(RuntimeError):updater.stage({'tag_name':'v9.9.9'})
    assert list((updater.root/'versions').iterdir())==[previous]
    assert (previous/'keep.txt').read_text()=='keep'

@pytest.mark.parametrize('entry',['../escape','/absolute','release/C:/evil','release\\evil','release/link'])
def test_source_archive_rejects_traversal_and_symlinks(updater,tmp_path,monkeypatch,entry):
    archive=tmp_path/'malicious.zip'
    with zipfile.ZipFile(archive,'w') as z:
        info=zipfile.ZipInfo(entry)
        info.filename=entry  # Preserve malicious backslashes even on Windows.
        if entry=='release/link':info.external_attr=(0o120777 << 16)
        z.writestr(info,'payload')
    monkeypatch.setattr(updater,'command',lambda args,**kw:Path(args[-1]).mkdir())
    monkeypatch.setattr(updater,'download',lambda url,path,digest=None:shutil.copy2(archive,path))
    with pytest.raises(ValueError,match='Path arsip'):updater.stage({'tag_name':'v9.9.9'})
    assert updater.read('active.json')=={}
    assert list((updater.root/'versions').iterdir())==[]
