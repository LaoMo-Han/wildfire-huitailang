"""Build verified public downloads; publish assets before the update manifest."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from github_api import GitHub, REPOSITORY
from build_client import PROJECT, SPEC
from deploy_runtime import deploy
from package_friend_patch import GUIDE

SITE='https://laomo-han.github.io/wildfire-downloads/'

def file_hash(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def asset(path,tag):
    return {'name':path.name,'url':'https://github.com/'+REPOSITORY+'/releases/download/'+tag+'/'+path.name,
            'size':path.stat().st_size,'sha256':file_hash(path)}

def previous_manifest():
    try:
        request=urllib.request.Request(SITE+'latest.json',headers={'User-Agent':'Wildfire-Publisher'})
        with urllib.request.urlopen(request,timeout=20) as response:return json.load(response)
    except Exception:
        local=PROJECT/'site/latest.json'
        if local.exists():return json.loads(local.read_text(encoding='utf8'))
        return {}

def full_stage(client,destination,manifest):
    if destination.exists():raise ValueError('Refusing to reuse a full client staging directory')
    destination.mkdir(parents=True)
    root_files=['launch.exe','update.exe','开始游戏.exe','start_offline.cmd','launch.exe.config','update.exe.config','开始游戏.exe.config']
    for path in client.rglob('*'):
        if not path.is_file():continue
        relative=path.relative_to(client);parts=relative.parts
        if parts[0]=='game':
            if len(parts)==2 and not(path.suffix.lower() in {'.dll','.xml','.npk'} or path.name in {'wf.exe','WFMiniTray.exe','validation.data','tag.txt','update.info','compatiable.ident'}):continue
            if path.suffix.lower() in {'.log','.pyc','.tmp','.dmp'} or '__pycache__' in parts:continue
        elif parts[0]=='res':
            if parts[1] in {'pic','uslogs','rep'}:continue
            if 'editor' in parts and relative.as_posix() not in {f for c in manifest['components'] for f in c['files']}:continue
        elif relative.as_posix()!='bootstrap/EditorConf.py' and relative.as_posix() not in root_files:continue
        target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True)
        if path.suffix.lower() in {'.bag','.pak','.webm'}:
            try:os.link(path,target)
            except OSError:shutil.copy2(path,target)
        else:shutil.copy2(path,target)
    for folder in ['pic','uslogs','rep']:(destination/'res'/folder).mkdir(exist_ok=True)
    config=ET.parse(destination/'game/conf.xml')
    for key,value in {'screen/width':'1280','screen/height':'720','screen/windowed':'1'}.items():
        node=config.find(key)
        if node is not None:node.text=value
    config.write(destination/'game/conf.xml',encoding='utf-8',xml_declaration=True)
    # This original file stores per-account UI preferences; ship an empty default.
    (destination/'game/personal.xml').write_text('<root/>\n',encoding='utf8')
    (destination/'version.json').write_text(json.dumps(manifest,ensure_ascii=False),encoding='utf8')
    (destination/'使用说明.txt').write_text(GUIDE,encoding='utf-8-sig')

def sevenzip(arguments):
    binary=Path(r'C:/Program Files/7-Zip/7z.exe')
    if not binary.exists():raise RuntimeError('7-Zip is required for full client volumes')
    process=subprocess.Popen([str(binary),*map(str,arguments)],stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    start=time.monotonic();last=start
    try:
        while process.poll() is None:
            time.sleep(2)
            if time.monotonic()-last>20:print('7-Zip working: '+str(int(time.monotonic()-start))+' seconds',flush=True);last=time.monotonic()
    except BaseException:
        process.terminate();process.wait();raise
    if process.returncode:raise RuntimeError('7-Zip failed: '+process.stderr.read().decode(errors='replace')[:700])

def prepare(client,version,build,notes,include_base,previous):
    deploy(client)
    if file_hash(client/'game/wf.exe')!=SPEC['patched_wf_sha256'] or file_hash(client/'res/entities.bag')!=SPEC['patched_entities_sha256']:raise ValueError('Unsupported client')
    if build<=int(previous.get('build',0)):raise ValueError('Build must increase')
    directory=PROJECT/'artifacts/releases'/version;directory.mkdir(parents=True,exist_ok=True)
    tag='v'+version
    groups={'core':['game/wf.exe','res/entities.bag'],
        'runtime':['bootstrap/EditorConf.py']+['res/editor/client/'+p.name for p in sorted((PROJECT/'runtime').glob('*.py'))],
        'launcher':['launch.exe','update.exe','开始游戏.exe','start_offline.cmd','launch.exe.config','update.exe.config','开始游戏.exe.config']}
    manifest={'schema_version':1,'version':version,'build':build,'base_client':'1.0.192',
        'notes':notes,'published_at':datetime.now(timezone.utc).isoformat(),'components':[],'remove':[],
        'base_downloads':previous.get('base_downloads',[])}
    assets=[]
    for name,files in groups.items():
        hashes={f:file_hash(client/f) for f in files}
        old=next((c for c in previous.get('components',[]) if c['id']==name and c['files']==hashes),None)
        if old:manifest['components'].append(old);continue
        target=directory/(name+'-'+version+'.zip')
        with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as archive:
            for f in files:archive.write(client/f,f)
        record=asset(target,tag);record.update(id=name,files=hashes);manifest['components'].append(record);assets.append(target)
    manual=directory/('wildfire-patch-'+version+'.zip')
    with zipfile.ZipFile(manual,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as archive:
        for files in groups.values():
            for f in files:archive.write(client/f,f)
        archive.writestr('version.json',json.dumps(manifest,ensure_ascii=False).encode('utf8'))
        archive.writestr('使用说明.txt',GUIDE.encode('utf-8-sig'))
    manifest['manual_patch']=asset(manual,tag);assets.append(manual)
    if include_base:
        stage=directory/'staging/wildfire-offline';full_stage(client,stage,manifest)
        archive=directory/'wildfire-offline-1.0.192.7z'
        sevenzip(['a','-t7z','-mx=1','-mmt=2','-v1500m',archive,stage])
        volumes=sorted(directory.glob(archive.name+'.*'))
        if not volumes:raise RuntimeError('No base volumes produced')
        sevenzip(['t',volumes[0]])
        manifest['base_downloads']=[asset(p,tag) for p in volumes];assets+=volumes
    if not manifest['base_downloads']:raise ValueError('Initial release must include a full base client')
    (directory/'latest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    (directory/'publish-state.json').write_text(json.dumps({'tag':tag,'assets':[p.name for p in assets]}),encoding='utf8')
    print('Prepared '+version,flush=True)
    return directory

def publish(directory):
    gh=GitHub();gh.ensure_repository()
    manifest=json.loads((directory/'latest.json').read_text(encoding='utf8'))
    state=json.loads((directory/'publish-state.json').read_text())
    release_id=state.get('release_id')
    if release_id:release=gh.request('GET','/repos/'+REPOSITORY+'/releases/'+str(release_id))
    else:
        release=gh.request('POST','/repos/'+REPOSITORY+'/releases',{'tag_name':state['tag'],'name':'无尽战区单机版 '+manifest['version'],'body':manifest['notes'],'draft':True})
        state['release_id']=release['id'];(directory/'publish-state.json').write_text(json.dumps(state))
    uploaded={a['name']:a for a in gh.request('GET','/repos/'+REPOSITORY+'/releases/'+str(release['id'])+'/assets?per_page=100')}
    def upload_one(name):
        path=directory/name
        if name in uploaded:
            existing=uploaded[name]
            digest='sha256:'+file_hash(path)
            if existing['size']==path.stat().st_size and existing.get('digest')==digest and existing['state']=='uploaded':
                print('Reusing verified '+name,flush=True);return
            if not release['draft']:raise RuntimeError('Published asset differs: '+name)
            gh.request('DELETE','/repos/'+REPOSITORY+'/releases/assets/'+str(existing['id']))
        result=gh.upload(release,path)
        if result.get('digest')!='sha256:'+file_hash(path) or result['size']!=path.stat().st_size:
            raise RuntimeError('GitHub asset checksum mismatch: '+name)
        print('Uploaded and verified '+name,flush=True)
    # Different attachment names can upload independently. Bounded concurrency
    # keeps memory below a few MiB, even for the full-client volumes.
    with ThreadPoolExecutor(max_workers=3) as pool:
        for result in pool.map(upload_one,state['assets']):pass
    if release['draft']:gh.request('PATCH','/repos/'+REPOSITORY+'/releases/'+str(release['id']),{'draft':False})
    # One Git tree/commit publishes website and manifest together, after assets.
    branch=gh.request('GET','/repos/'+REPOSITORY+'/git/ref/heads/main')
    commit=gh.request('GET','/repos/'+REPOSITORY+'/git/commits/'+branch['object']['sha'])
    entries=[]
    for path in (PROJECT/'site').rglob('*'):
        if path.is_file() and path.name!='latest.json':
            blob=gh.request('POST','/repos/'+REPOSITORY+'/git/blobs',{'content':base64.b64encode(path.read_bytes()).decode(),'encoding':'base64'})
            entries.append({'path':path.relative_to(PROJECT/'site').as_posix(),'mode':'100644','type':'blob','sha':blob['sha']})
    blob=gh.request('POST','/repos/'+REPOSITORY+'/git/blobs',{'content':base64.b64encode((directory/'latest.json').read_bytes()).decode(),'encoding':'base64'})
    entries.append({'path':'latest.json','mode':'100644','type':'blob','sha':blob['sha']})
    tree=gh.request('POST','/repos/'+REPOSITORY+'/git/trees',{'base_tree':commit['tree']['sha'],'tree':entries})
    new=gh.request('POST','/repos/'+REPOSITORY+'/git/commits',{'message':'Publish '+manifest['version'],'tree':tree['sha'],'parents':[commit['sha']]})
    gh.request('PATCH','/repos/'+REPOSITORY+'/git/refs/heads/main',{'sha':new['sha'],'force':False})
    try:gh.request('GET','/repos/'+REPOSITORY+'/pages')
    except RuntimeError as error:
        if ': 404 ' not in str(error):raise
        gh.request('POST','/repos/'+REPOSITORY+'/pages',{'source':{'branch':'main','path':'/'},'build_type':'legacy'})
    (PROJECT/'site/latest.json').write_bytes((directory/'latest.json').read_bytes())
    print('Published '+manifest['version']+': '+SITE,flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client',type=Path,default=Path(r'C:/wildfire-gpt/offline_client'))
    parser.add_argument('--version');parser.add_argument('--build',type=int);parser.add_argument('--notes',type=Path)
    parser.add_argument('--include-base',action='store_true');parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--resume',type=Path);parser.add_argument('--previous',type=Path)
    args=parser.parse_args()
    if args.resume:directory=args.resume
    else:
        if not args.version or not args.build or not args.notes:parser.error('--version, --build and --notes are required')
        previous=json.loads(args.previous.read_text(encoding='utf8')) if args.previous else previous_manifest()
        directory=prepare(args.client,args.version,args.build,args.notes.read_text(encoding='utf8'),args.include_base,previous)
    if not args.prepare_only:publish(directory)
