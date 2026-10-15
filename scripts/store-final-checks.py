"""Local evidence checks. Never reads global credentials or prints matching secret text."""
import hashlib
import json
import plistlib
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'docs/evidence/r3-store'
OUT.mkdir(parents=True, exist_ok=True)
pkg = json.loads((ROOT / 'package.json').read_text(encoding='utf-8'))
assert pkg['version'] == '1.14.0'
lock = json.loads((ROOT / 'package-lock.json').read_text(encoding='utf-8'))
assert lock['version'] == lock['packages']['']['version'] == pkg['version']
project = (ROOT / 'ios/App/App.xcodeproj/project.pbxproj').read_text(encoding='utf-8')
assert project.count('MARKETING_VERSION = 1.14.0;') == 2
assert project.count('CURRENT_PROJECT_VERSION = 4;') == 2
android = (ROOT / 'android/app/build.gradle').read_text(encoding='utf-8')
assert 'versionName "1.14.0"' in android and 'versionCode 4' in android
privacy = plistlib.loads((ROOT / 'ios/App/App/PrivacyInfo.xcprivacy').read_bytes())
assert privacy['NSPrivacyTracking'] is False
assert privacy['NSPrivacyTrackingDomains'] == privacy['NSPrivacyCollectedDataTypes'] == []
assert privacy['NSPrivacyAccessedAPITypes'] == [{'NSPrivacyAccessedAPIType': 'NSPrivacyAccessedAPICategoryUserDefaults', 'NSPrivacyAccessedAPITypeReasons': ['CA92.1']}]
for file in ['ios/App/App/Base.lproj/LaunchScreen.storyboard', 'android/app/src/main/res/drawable-v24/ic_launcher_foreground.xml']:
    ET.parse(ROOT / file)
permissions = ET.parse(ROOT / 'android/app/src/main/AndroidManifest.xml').getroot().findall('uses-permission')
assert permissions == []
listing = (ROOT / 'docs/store/LISTING_ZH_TW.md').read_text(encoding='utf-8')
name = re.search(r'名稱（\d+ 字）：(.+)', listing)[1]
subtitle = re.search(r'副標題（\d+ 字）：(.+)', listing)[1]
keywords = re.search(r'關鍵字：(.+)', listing)[1]
assert len(name) <= 30 and len(subtitle) <= 30 and len(keywords.encode('utf-8')) <= 100
result = subprocess.run(['rg', '--hidden', '--no-ignore', '-l', '-e', r'sk-proj-[A-Za-z0-9_-]{20}|sk-[a-z0-9]{40}', '-g', '!**/.git/**', '-g', '!**/node_modules/**', '.'], cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=120)
assert result.returncode in [0, 1], 'Secret scan tool failed; inspect stderr without printing secret matches'
paths = result.stdout.splitlines()
(OUT / 'secret-scan.json').write_text(json.dumps({'status': 'VERIFIED' if not paths else 'BLOCKED', 'matches': len(paths), 'paths_only': paths, 'scope': 'Repository including hidden/ignored files, excludes .git and node_modules; no global credentials accessed'}, ensure_ascii=False, indent=2), encoding='utf-8')
assert not paths, 'Secret scan found matching files; values not printed'
runtime = [ROOT / 'index.html', *list((ROOT / 'src').glob('*.js')), *list((ROOT / 'src').glob('*.css'))]
residue = [str(p.relative_to(ROOT)) for p in runtime if re.search(r'Lorem|TODO|>\s*Sample(?:\s|<)|敬請期待|\?{5,}', p.read_text(encoding='utf-8'), re.I)]
assert not residue, residue
stale = []
for p in [ROOT / 'package.json', ROOT / 'package-lock.json', ROOT / 'index.html', ROOT / 'README.md', *list((ROOT / 'src').glob('*.js'))]:
    for n, line in enumerate(p.read_text(encoding='utf-8').splitlines(), 1):
        if '1.13.0' in line and not (p.name == 'trip-session.js' and '[GAME_VERSION,' in line): stale.append({'file': str(p.relative_to(ROOT)), 'line': n})
assert stale == [], stale
report = {'status': 'VERIFIED', 'webVersion': pkg['version'], 'nativeSourceVersion': '1.14.0', 'nativeSourceBuild': 4, 'nameCharacters': len(name), 'subtitleCharacters': len(subtitle), 'keywordUtf8Bytes': len(keywords.encode('utf-8')), 'privacyPlistParsed': True, 'nativeXmlParsed': True, 'androidSourcePermissions': [], 'runtimeTemplateResidue': residue, 'oldActiveVersionHits': stale, 'legacyVersionException': 'trip-session.js accepted historical 1.13.0 saves', 'archivePipeline': 'BLOCKED: historical iOS signing/capture workflows remain pinned to 1.0.0 build 3 and old artifact hashes; no new archive built'}
(OUT / 'final-checks.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=True))
