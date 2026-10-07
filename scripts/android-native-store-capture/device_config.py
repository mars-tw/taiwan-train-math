"""Configure only the fresh CI-owned AVD before launch; no host AVD access."""
import argparse
import os
import re
from pathlib import Path

def configure(name,family,home,temp,ci_home):
 if not re.fullmatch(r'NativeCapture(?:Phone|Tablet)_[A-Za-z0-9_-]+',name):raise ValueError('CI-owned AVD required')
 home=Path(home).resolve();temp=Path(temp).resolve();standard=(Path(ci_home)/'.android/avd').resolve()
 # Verified pinned emulator-runner sdk-installer.ts resets AVD_HOME to this
 # fresh CI user's standard location. Permit only that exact root or own temp.
 if not(home.is_relative_to(temp) or home==standard):raise ValueError('AVD root is neither exact fresh CI home nor own runner temp')
 config=(home/(name+'.avd')/'config.ini').resolve()
 if not config.is_relative_to(home) or not config.is_file():raise ValueError('Missing own AVD config')
 settings={'hw.lcd.width':'1080' if family=='phone' else '1200','hw.lcd.height':'1920','hw.lcd.density':'320' if family=='phone' else '240','hw.initialOrientation':'Portrait','showDeviceFrame':'no','hw.keyboard':'no'}
 text=config.read_text(encoding='utf-8')
 for key,value in settings.items():
  pattern=r'(?m)^'+re.escape(key)+r'\s*=.*$'
  text=re.sub(pattern,key+'='+value,text) if re.search(pattern,text) else text+'\n'+key+'='+value
 config.write_text(text+'\n',encoding='utf-8')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--name',required=True);p.add_argument('--family',choices=['phone','tablet'],required=True);a=p.parse_args()
 if os.environ.get('GITHUB_ACTIONS')!='true':raise SystemExit('CI-owned AVD required')
 configure(a.name,a.family,os.environ['ANDROID_AVD_HOME'],os.environ['RUNNER_TEMP'],os.environ['HOME'])
