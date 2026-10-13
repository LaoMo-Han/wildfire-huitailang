"""Reproduce the verified offline client using a locally supplied original."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import struct
from xml.etree import ElementTree as ET
from marshal27 import MarshalReader, flatten_codes

PROJECT = Path(__file__).resolve().parent.parent
SPEC = json.loads((PROJECT / 'tools/client_spec.json').read_text(encoding='utf-8'))


def sha(data):
    return hashlib.sha256(data).hexdigest()


class LocatedReader(MarshalReader):
    def __init__(self, *args):
        super().__init__(*args)
        self.locations = []

    def value(self, depth=0):
        start = self.pos
        result = super().value(depth)
        self.locations.append((start, self.pos, result))
        return result


def patch_entities(original):
    if sha(original) != SPEC['entities_sha256']:
        raise ValueError('Unsupported entities.bag: SHA256 differs from client 1.0.192')
    output = bytearray(original)
    for module in SPEC['modules']:
        start, end = module['offset'], module['end']
        reader = LocatedReader(original, start)
        root = reader.value()
        if reader.pos != end:
            raise ValueError('Marshal module boundary mismatch')
        body = bytearray(original[start:end])
        codes = list(flatten_codes(root))
        if module['suffix'] == 'logic\\fsmgame.o':
            function = next(f for f in codes if f['name'] == b'__init__' and b'GameFsm' in f['names'])
            guard = bytes.fromhex('741500621600830000700301')
            if function['names'][21:24] != (b'BigWorld', b'isPublishedVersion', b'FsmManager'):
                raise ValueError('Unexpected FSM name table')
            index = original.find(function['code'], start, end)
            relative = function['code'].find(guard)
            if index < 0 or relative < 0:
                raise ValueError('FSM guard not found')
            body[index-start+relative+9] = 0x7e
        elif module['suffix'] == 'guis\\logon\\logonpanel.o':
            function = next(f for f in codes if f['name'] == b'init_ui' and b'debug_mode' in f['names'])
            guard = bytes.fromhex('743f006240008300000c')
            replacement = bytes.fromhex('7415000c741500150c0c')
            if function['names'][21] != b'False':
                raise ValueError('Unexpected login name table')
            index = original.find(function['code'], start, end)
            relative = function['code'].find(guard)
            if index < 0 or relative < 0:
                raise ValueError('Login guard not found')
            at = index-start+relative
            body[at:at+len(guard)] = replacement
        else:
            function = next(f for f in codes if f['name'] == b'enter')
            fstart, fend, _ = next(row for row in reader.locations if row[2] is function)
            scene = [row for row in reader.locations if fstart <= row[0] < fend and row[2] == b'zd_gangtyztest']
            position = [row for row in reader.locations if fstart <= row[0] < fend and isinstance(row[2], tuple) and row[2] == (0, 1, 0)]
            if len(scene) != 1 or len(position) != 1:
                raise ValueError('Ambiguous hall constants')
            a, b, _ = scene[0]
            old_scene = original[a:b]
            new_scene = old_scene[:1]+struct.pack('<i', 8)+b'zc_new01'
            c, d, _ = position[0]
            new_position = b'('+struct.pack('<i', 3)+b''.join(b'i'+struct.pack('<i', n) for n in SPEC['spawn'])
            for first, last, replacement in sorted([(a, b, new_scene), (c, d, new_position)], reverse=True):
                body[first-start:last-start] = replacement
            body.extend(b'\0'*(end-start-len(body)))
        verify = MarshalReader(bytes(body))
        verify.value()
        if any(body[verify.pos:]):
            raise ValueError('Unexpected bytes after marshalled root')
        header = start-24
        key = header ^ 0x00ae457c
        encode = lambda digest: struct.pack('<4I', *(n ^ key for n in struct.unpack('<4I', digest)))
        if original[header:header+16] != encode(hashlib.md5(original[start:end]).digest()):
            raise ValueError('Original BAG content checksum mismatch')
        output[start:end] = body
        output[header:header+16] = encode(hashlib.md5(body).digest())
    if sha(output) != SPEC['patched_entities_sha256']:
        raise ValueError('Reproduced archive differs from verified hall milestone')
    return bytes(output)


def patch_executable(original):
    if sha(original) != SPEC['wf_sha256']:
        raise ValueError('Unsupported wf.exe: SHA256 differs from verified client')
    old = b'level="requireAdministrator"'
    new = b'level="asInvoker"'+b' '*11
    if original.count(old) != 1:
        raise ValueError('Ambiguous requested privilege manifest')
    output = bytearray(original.replace(old, new))
    pe = struct.unpack_from('<I', output, 0x3c)[0]
    checksum_offset = pe+24+64
    value = 0
    for position in range(0, len(output), 2):
        if checksum_offset <= position < checksum_offset+4:
            continue
        value += output[position] | ((output[position+1] if position+1 < len(output) else 0) << 8)
        value = (value & 0xffff)+(value >> 16)
    value = (value & 0xffff)+(value >> 16)
    struct.pack_into('<I', output, checksum_offset, (value+len(output)) & 0xffffffff)
    if sha(output) != SPEC['patched_wf_sha256']:
        raise ValueError('Reproduced executable differs from verified hall milestone')
    return bytes(output)


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+'.building')
    with temporary.open('xb') as stream:
        stream.write(data)
    os.replace(temporary, path)


def stage(source, destination, executable, entities):
    if source.resolve() == destination.resolve() or source.resolve() in destination.resolve().parents or destination.resolve() in source.resolve().parents:
        raise ValueError('Output must be separate from the original client tree')
    if destination.exists():
        raise ValueError('Choose a new output directory; existing clients are never overwritten')
    game, res = destination/'game', destination/'res'
    game.mkdir(parents=True)
    res.mkdir()
    for path in (source/'game').iterdir():
        if path.is_file() and (path.suffix.lower() in {'.dll', '.xml', '.npk'} or path.name in {'WFMiniTray.exe', 'validation.data', 'tag.txt', 'update.info', 'compatiable.ident'}):
            shutil.copy2(path, game/path.name)
    shutil.copytree(source/'game/webproc', game/'webproc')
    for path in (source/'res').rglob('*'):
        if not path.is_file():
            continue
        relative = path.relative_to(source/'res')
        if relative.parts[0] in {'pic', 'uslogs', 'rep', 'editor'} or relative == Path('entities.bag'):
            continue
        target = res/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(path, target)
        except OSError:
            shutil.copy2(path, target)
    for name in ['pic', 'uslogs', 'rep']:
        (res/name).mkdir(exist_ok=True)
    atomic_write(game/'wf.exe', executable)
    atomic_write(res/'entities.bag', entities)
    tree = ET.parse(game/'conf.xml')
    for key, value in {'screen/width':'1280', 'screen/height':'720', 'screen/windowed':'1', 'login/ip':'127.0.0.1', 'login/servers/server0':'0 0 0 0 Offline Offline 127.0.0.1:20160 127.0.0.1:20160 127.0.0.1:20160'}.items():
        node = tree.find(key)
        if node is not None:
            node.text = value
    protocol = tree.find('UserProtocol')
    if protocol is not None:
        tree.getroot().remove(protocol)
    tree.write(game/'conf.xml', encoding='utf-8', xml_declaration=True)
    local = res/'editor/client'
    local.mkdir(parents=True)
    runtime = PROJECT/'runtime'
    for path in runtime.glob('*.py'):
        shutil.copy2(path, local/path.name)
    bootstrap = destination/'bootstrap'
    bootstrap.mkdir()
    shutil.copy2(runtime/'EditorConf.py', bootstrap/'EditorConf.py')
    (game/'log.txt').touch()
    (destination/'start_offline.cmd').write_bytes(b'@echo off\r\ncopy /y "%~dp0bootstrap\EditorConf.py" "%~dp0res\editor\client\EditorConf.py" >nul\r\nif errorlevel 1 exit /b 1\r\ncd /d "%~dp0game"\r\nstart "" "wf.exe"\r\n')
    report = {'profile':'formal-hero-stage', 'source':str(source), 'output':str(destination), 'scene':SPEC['scene'], 'wf_sha256':sha(executable), 'entities_sha256':sha(entities), 'assets':'Other resource files may be hardlinked; never edit them in place.', 'runtime_verified':False}
    (destination/'build_manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='Client root containing game/ and res/')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    executable = patch_executable((args.source/'game/wf.exe').read_bytes())
    entities = patch_entities((args.source/'res/entities.bag').read_bytes())
    if args.verify_only:
        report = {'verified':True, 'wf_sha256':sha(executable), 'entities_sha256':sha(entities)}
    else:
        if args.output is None:
            parser.error('--output is required without --verify-only')
        report = stage(args.source, args.output, executable, entities)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
