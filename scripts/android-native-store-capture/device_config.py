"""Configure only the fresh CI-owned AVD before launch; no host AVD access."""
import argparse
import os
import re
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('--name',required=True);p.add_argument('--family',choices=['phone','tablet'],required=True);a=p.parse_args()
if os.environ.get('GITHUB_ACTIONS')!='true' or not re.fullmatch(r'NativeCapture(?:Phone|Tablet)_[A-Za-z0-9_-]+',a.name):raise SystemExit('CI-owned AVD required')
home=Path(os.environ['ANDROID_AVD_HOME']).resolve();temp=Path(os.environ['RUNNER_TEMP']).resolve()
if not home.is_relative_to(temp):raise SystemExit('AVD root must be inside this runner temp')
config=(home/(a.name+'.avd')/'config.ini').resolve()
if not config.is_relative_to(home) or not config.is_file():raise SystemExit('Missing own AVD config')
settings={'hw.lcd.width':'1080' if a.family=='phone' else '1200','hw.lcd.height':'1920','hw.lcd.density':'320' if a.family=='phone' else '240','hw.initialOrientation':'Portrait','showDeviceFrame':'no','hw.keyboard':'no'}
text=config.read_text()
for key,value in settings.items():
 pattern=r'(?m)^'+re.escape(key)+r'\s*=.*$'
 text=re.sub(pattern,key+'='+value,text) if re.search(pattern,text) else text+'\n'+key+'='+value
config.write_text(text+'\n')
