"""Update only local runtime scripts in an existing verified client copy."""
from pathlib import Path
import argparse
from build_client import PROJECT, SPEC, sha, atomic_write


def deploy(client):
    if sha((client/'game/wf.exe').read_bytes()) != SPEC['patched_wf_sha256']:
        raise ValueError('Target is not the independent verified client executable')
    if sha((client/'res/entities.bag').read_bytes()) != SPEC['patched_entities_sha256']:
        raise ValueError('Target archive differs from the verified hall patch')
    source = PROJECT/'runtime'
    for path in source.glob('*.py'):
        atomic_write(client/'res/editor/client'/path.name, path.read_bytes())
    atomic_write(client/'bootstrap/EditorConf.py', (source/'EditorConf.py').read_bytes())
    for obsolete in ['offline_ui.py', 'offline_hero_page.py', 'offline_hall.enabled']:
        path = client/'res/editor/client'/obsolete
        if path.exists():
            path.unlink()
    command = b'@echo off\r\ncopy /y "%~dp0bootstrap\EditorConf.py" "%~dp0res\editor\client\EditorConf.py" >nul\r\nif errorlevel 1 exit /b 1\r\ncd /d "%~dp0game"\r\nstart "" "wf.exe"\r\n'
    atomic_write(client/'start_offline.cmd', command)
    legacy = client/'start_offline_test.cmd'
    if legacy.exists():
        atomic_write(legacy, command)
    print('Runtime and persistent startup template deployed: '+str(client))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client', type=Path, required=True)
    args = parser.parse_args()
    deploy(args.client)
