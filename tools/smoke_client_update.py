"""Exercise a disposable running client via its existing JSON test bridge.

Calls the same Updates.install handler as the UI button, using a temporary
hero-stage test hook that restores its source before the game quits normally.
Never use against a player's primary client.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
import xml.etree.ElementTree as ET
from build_client import atomic_write

def read(path):return json.loads(path.read_text(encoding='utf8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def screen(root):return {n.tag:(n.text or '').strip() for n in ET.parse(root/'game/conf.xml').find('screen')}
def wait(predicate,seconds,label):
    end=time.monotonic()+seconds;last=0
    while time.monotonic()<end:
        value=predicate()
        if value:return value
        if time.monotonic()-last>15:print('Waiting: '+label,flush=True);last=time.monotonic()
        time.sleep(.5)
    raise TimeoutError(label)
def run(root,version,build,expected):
    root=root.resolve()
    if 'analysis' not in root.parts:raise ValueError('Use a disposable client under analysis')
    before=read(root/'version.json');original={name:sha(root/name) for c in before['components'] for name in c['files']}
    old_screen=screen(root);profile=root/'game/offline_profile.json';old_profile=sha(profile) if profile.exists() else None
    # HTTPS checks can finish before the native engine loads its Python runtime.
    # A harmless command acknowledgement proves the game is ready before hooks.
    probe=None;last_probe=0
    def runtime_ready():
        nonlocal probe,last_probe
        try:
            data=read(root/'game/offline_status.json')
            if probe and data.get('command_completed_id')==probe:
                assert data['last_error'] is None,data['last_error']
                return True
        except (FileNotFoundError,json.JSONDecodeError):pass
        if time.monotonic()-last_probe>3:
            probe=str(time.time())+'-runtime-ready'
            atomic_write(root/'game/offline_command.json',json.dumps({'id':probe,'action':'practice','operation':'inspect'}).encode())
            last_probe=time.monotonic()
        return None
    wait(runtime_ready,120,'native runtime ready')
    def request(action):
        marker=str(time.time())+'-'+action
        atomic_write(root/'game/update_request.json',json.dumps({'id':marker,'action':action}).encode())
        return marker
    def status():
        try:return read(root/'game/update_status.json')
        except (FileNotFoundError,json.JSONDecodeError):return {}
    marker=request('check')
    last_check=time.monotonic()
    def offered():
        nonlocal marker,last_check
        s=status()
        if s.get('request_id')==marker and s.get('state')=='available' and s.get('version')==version:return s
        if time.monotonic()-last_check>5 and s.get('state')!='checking':
            marker=request('check');last_check=time.monotonic()
        return None
    offer=wait(offered,120,'update offer')
    print('PASS running client offered '+offer['version']+' with release notes: '+offer['notes'].splitlines()[0],flush=True)
    marker=request('download')
    wait(lambda:status().get('state')=='ready' and status().get('request_id')==marker,180,'download ready')
    assert all(sha(root/name)==digest for name,digest in original.items()),'Running game files changed during download'
    stages=[p for p in (root/'.updates').iterdir() if p.is_dir() and (p/'manifest.json').exists() and read(p/'manifest.json')['build']==build]
    stage=max(stages,key=lambda p:p.stat().st_mtime)
    downloads=sorted(p.name for p in stage.glob('*.zip'))
    assert downloads==sorted(expected),downloads
    print('PASS downloaded only changed components '+str(downloads)+'; running files unchanged',flush=True)
    hero=root/'res/editor/client/hero_stage.py';saved=root/'game/qa-hero-original.py';saved.write_bytes(hero.read_bytes())
    hook=b'''\n_qa_original_install = install
def install(hall, runtime, log):
    with open('../game/qa-hero-original.py','rb') as src:
        original = src.read()
    with open('../res/editor/client/hero_stage.py','wb') as dst:
        dst.write(original)
    result = _qa_original_install(hall, runtime, log)
    runtime.updates.install()
    return result
'''
    atomic_write(hero,saved.read_bytes()+hook)
    atomic_write(root/'game/offline_command.json',json.dumps({'id':str(time.time())+'-normal-quit','action':'reload_stage'}).encode())
    wait(lambda:read(root/'version.json')['build']==build,90,'normal exit and installation')
    wait(lambda:status().get('state')=='current' and status().get('current_version')==version,90,'restarted launcher check')
    native=wait(lambda:read(root/'game/offline_status.json') if read(root/'game/offline_status.json').get('command_completed_id') is None else None,60,'restarted offline runtime')
    assert native['state']==2 and native['last_error'] is None and not native['hall_errors'],native
    assert screen(root)==old_screen,'Graphics settings changed'
    assert (sha(profile) if profile.exists() else None)==old_profile,'Personal profile changed'
    installed=read(root/'version.json')
    assert all(sha(root/name)==digest for c in installed['components'] for name,digest in c['files'].items())
    result={'from_version':before['version'],'to_version':version,'build':build,'downloaded_components':downloads,'download_bytes':sum(p.stat().st_size for p in stage.glob('*.zip')),'settings_preserved':True,'profile_preserved':True,'native_restart':True}
    (root.parent/'update-smoke-result.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    saved.unlink()
    print('PASS installed and restarted; player profile and graphics settings preserved',flush=True)
    print(json.dumps(result),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--client',required=True,type=Path);p.add_argument('--version',required=True);p.add_argument('--build',required=True,type=int);p.add_argument('--expected-components',nargs='+',default=['launcher.zip','runtime.zip']);a=p.parse_args();run(a.client,a.version,a.build,a.expected_components)
