"""GitHub publishing client; existing Git credentials stay in process memory."""
import http.client
import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

OWNER = 'LaoMo-Han'
REPOSITORY = OWNER+'/wildfire-downloads'

class GitHub:
    def __init__(self):
        env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='never')
        result = subprocess.run(['git', 'credential', 'fill'],
            input='protocol=https\nhost=github.com\n\n', text=True,
            capture_output=True, env=env, check=True)
        values = dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
        self.token = values['password']

    def headers(self):
        return {'Authorization':'Bearer '+self.token, 'Accept':'application/vnd.github+json',
                'User-Agent':'Wildfire-Publisher', 'X-GitHub-Api-Version':'2022-11-28'}

    def request(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request('https://api.github.com'+path, data=data,
            headers=dict(self.headers(), **{'Content-Type':'application/json'}), method=method)
        retryable=method=='GET' or '/git/' in path
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    content = response.read()
                    return json.loads(content) if content else None
            except urllib.error.HTTPError as error:
                if retryable and error.code in (429,500,502,503,504) and attempt<2:
                    time.sleep(2*(attempt+1));continue
                # Never include request headers or tokens in diagnostics.
                raise RuntimeError('GitHub '+method+' '+path+': '+str(error.code)+' '+error.read().decode()[:800]) from None
            except (urllib.error.URLError,TimeoutError,OSError):
                if not retryable or attempt==2:raise
                time.sleep(2*(attempt+1))

    def ensure_repository(self):
        try:
            repo = self.request('GET','/repos/'+REPOSITORY)
        except RuntimeError as error:
            if ': 404 ' not in str(error):
                raise
            repo = self.request('POST','/user/repos', {'name':'wildfire-downloads',
                'description':'无尽战区单机版下载、更新公告与问题反馈', 'private':False,
                'auto_init':True, 'has_issues':False, 'has_projects':False, 'has_wiki':False})
        if repo['private']:
            raise RuntimeError('Download repository exists but is private; refusing to change visibility')
        print('Public download repository ready: '+repo['html_url'], flush=True)
        return repo

    def upload(self, release, path):
        path = Path(path)
        size = path.stat().st_size
        if size >= 2*1024**3:
            raise ValueError('Release asset must be smaller than 2 GiB')
        url = release['upload_url'].split('{')[0]+'?name='+urllib.parse.quote(path.name)
        parsed = urllib.parse.urlsplit(url)
        connection = http.client.HTTPSConnection(parsed.hostname, timeout=300)
        connection.putrequest('POST', parsed.path+'?'+parsed.query)
        for key, value in dict(self.headers(), **{'Content-Type':'application/octet-stream',
                'Content-Length':str(size)}).items():
            connection.putheader(key,value)
        connection.endheaders()
        sent, last = 0, 0
        with path.open('rb') as stream:
            while True:
                chunk = stream.read(1024*1024)
                if not chunk: break
                connection.send(chunk)
                sent += len(chunk)
                if time.monotonic()-last > 20:
                    print('Uploading '+path.name+': '+str(round(sent/size*100,1))+'%',flush=True)
                    last = time.monotonic()
        response = connection.getresponse()
        content = response.read()
        connection.close()
        if response.status != 201:
            raise RuntimeError('Asset upload failed '+str(response.status)+': '+content.decode()[:500])
        result = json.loads(content)
        assert result['size'] == size and result['state'] == 'uploaded'
        return result

if __name__ == '__main__':
    GitHub().ensure_repository()
