"""Fetch one exact immutable APK from an approved same-repository DRAFT."""
import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

REPO='mars-tw/taiwan-train-math'
def gh(*args):
 r=subprocess.run(['gh',*args],capture_output=True,timeout=300)
 if r.returncode:raise RuntimeError('Official GitHub input download failed; raw authenticated output suppressed')
 return r.stdout
def sha(raw):return hashlib.sha256(raw).hexdigest()
p=argparse.ArgumentParser();p.add_argument('--release-id',required=True);p.add_argument('--manifest-sha',required=True);p.add_argument('--project',required=True);p.add_argument('--directory',required=True);a=p.parse_args()
if os.environ.get('GITHUB_REPOSITORY')!=REPO or not a.release_id.isdigit() or not re.fullmatch('[0-9a-f]{64}',a.manifest_sha):raise SystemExit('Unapproved input identity')
base=Path(a.directory).resolve()
if not base.is_relative_to(Path(os.environ['RUNNER_TEMP']).resolve()):raise SystemExit('Input directory leaves own runner temp')
base.mkdir(mode=0o700,parents=True,exist_ok=True)
release=json.loads(gh('api','repos/'+REPO+'/releases/'+a.release_id))
if release.get('id')!=int(a.release_id) or release.get('draft') is not True or not release.get('tag_name','').startswith('android-native-capture-20261007-'):raise SystemExit('Exact capture DRAFT required')
assets={}
for x in release.get('assets',[]):
 if x['name'] in assets:raise SystemExit('Duplicate asset name')
 assets[x['name']]=x
def download(name,expected,maxbytes):
 item=assets.get(name)
 if not item or not isinstance(item.get('id'),int) or not 0<item.get('size',0)<=maxbytes:raise SystemExit('Missing or oversized approved asset')
 raw=gh('api','repos/'+REPO+'/releases/assets/'+str(item['id']),'-H','Accept: application/octet-stream')
 if len(raw)!=item['size'] or sha(raw)!=expected:raise SystemExit('Immutable input digest/bytes mismatch')
 (base/name).write_bytes(raw)
 return raw
manifest=json.loads(download('android-capture-manifest.json',a.manifest_sha,512*1024))
if manifest.get('schemaVersion')!=1 or manifest.get('repository')!=REPO:raise SystemExit('Unapproved capture manifest')
matches=[x for x in manifest['projects'] if x['projectId']==a.project]
if len(matches)!=1:raise SystemExit('Project missing/ambiguous in exact manifest')
item=matches[0];name=item['apkFile']
if not re.fullmatch(r'[a-z0-9-]+\.apk',name) or not re.fullmatch('[0-9a-f]{64}',item['apkSha256']):raise SystemExit('Invalid APK name/hash')
raw=download(name,item['apkSha256'],320*1024*1024)
if len(raw)!=item['apkBytes'] or item['debuggable'] is not False:raise SystemExit('Not approved release bytes')
provenance={'releaseId':release['id'],'draft':True,'repository':REPO,'manifestSha256':a.manifest_sha,'apkAssetId':assets[name]['id'],'projectId':a.project,'apkSha256':item['apkSha256'],'apkBytes':len(raw),'apkExecutedInFetchJob':False,'signerSecretsUsed':False}
(base/'fetch-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
print('One exact signed APK fetched and hashed; no game or signer code executed.')
