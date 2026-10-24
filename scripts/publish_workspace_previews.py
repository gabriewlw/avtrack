"""Publish the requested app previews using only synthetic browser-test data."""
import base64
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

previews=[
    ('avtrack-home-desktop.png','avtrack-home-generic-examples.png'),
    ('avtrack-full-width-iptv.png','avtrack-iptv-generic-play.png'),
    ('avtrack-network-stream-popup.png','avtrack-network-stream-example.png'),
]
headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json'}
for source,destination in previews:
    url='https://api.github.com/repos/'+os.environ['GH_REPOSITORY']+'/contents/docs/screenshots/'+destination
    payload={'message':'Update requested AVTrack preview','branch':'main',
             'content':base64.b64encode((Path('work/screenshots')/source).read_bytes()).decode()}
    try:
        with urlopen(Request(url,headers=headers)) as response:payload['sha']=json.load(response)['sha']
    except HTTPError as error:
        if error.code!=404:raise
    with urlopen(Request(url,data=json.dumps(payload).encode(),headers=headers,method='PUT')) as response:
        result=json.load(response)
    print('External screenshot: '+result['content']['download_url'])
