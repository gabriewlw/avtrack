"""Publish the requested synthetic inventory preview, never user inventory data."""
import base64
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

url='https://api.github.com/repos/'+os.environ['GH_REPOSITORY']+'/contents/docs/screenshots/avtrack-inventory-status.png'
headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json'}
payload={'message':'Update inventory condition preview','branch':'main',
         'content':base64.b64encode(Path('work/screenshots/avtrack-inventory-status.png').read_bytes()).decode()}
try:
    with urlopen(Request(url,headers=headers)) as response:payload['sha']=json.load(response)['sha']
except HTTPError as error:
    if error.code!=404:raise
with urlopen(Request(url,data=json.dumps(payload).encode(),headers=headers,method='PUT')) as response:
    result=json.load(response)
print('External screenshot: '+result['content']['download_url'])
