"""Deploy static Pages files without advertising unpublished download assets."""
import base64
from pathlib import Path
from github_api import GitHub, REPOSITORY
from build_client import PROJECT

def publish_site():
    gh=GitHub();gh.ensure_repository()
    ref=gh.request('GET','/repos/'+REPOSITORY+'/git/ref/heads/main')
    commit=gh.request('GET','/repos/'+REPOSITORY+'/git/commits/'+ref['object']['sha'])
    entries=[]
    for file in (PROJECT/'site').rglob('*'):
        if not file.is_file() or file.name=='latest.json':continue
        blob=gh.request('POST','/repos/'+REPOSITORY+'/git/blobs',{'content':base64.b64encode(file.read_bytes()).decode(),'encoding':'base64'})
        entries.append({'path':file.relative_to(PROJECT/'site').as_posix(),'mode':'100644','type':'blob','sha':blob['sha']})
    tree=gh.request('POST','/repos/'+REPOSITORY+'/git/trees',{'base_tree':commit['tree']['sha'],'tree':entries})
    new=gh.request('POST','/repos/'+REPOSITORY+'/git/commits',{'message':'Deploy release page and feedback form','tree':tree['sha'],'parents':[commit['sha']]})
    gh.request('PATCH','/repos/'+REPOSITORY+'/git/refs/heads/main',{'sha':new['sha'],'force':False})
    try:gh.request('GET','/repos/'+REPOSITORY+'/pages')
    except RuntimeError as error:
        if ': 404 ' not in str(error):raise
        gh.request('POST','/repos/'+REPOSITORY+'/pages',{'source':{'branch':'main','path':'/'},'build_type':'legacy'})
    print('Static site deployed: https://laomo-han.github.io/wildfire-downloads/')

if __name__=='__main__':publish_site()
