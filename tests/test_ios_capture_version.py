"""Exercise the workflow's real payload validator locally; never call GitHub."""
import ast
import hashlib
import json
from pathlib import Path
import plistlib
import re
import tempfile
import unittest
import zipfile

WORKFLOW = Path(__file__).resolve().parents[1] / '.github/workflows/ios-store-screenshots.yml'


class CurrentVersionTests(unittest.TestCase):
    def setUp(self):
        self.source = WORKFLOW.read_text(encoding='utf-8')
        block = self.source.split("          APP_ID = 'tw.mars.trainmath'", 1)[1].split('          def select_model', 1)[0]
        self.validator = "APP_ID = 'tw.mars.trainmath'" + '\n' + '\n'.join(line[10:] if line.startswith('          ') else line for line in block.splitlines())
        self.tree = ast.parse(self.validator)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def payload(self, web_version):
        archive = self.root / 'app.zip'
        files = [{'path': f'asset-{i}.txt', 'bytes': 1, 'sha256': hashlib.sha256(b'x').hexdigest()} for i in range(165)]
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('App.app/Info.plist', plistlib.dumps({
                'CFBundleIdentifier': 'tw.mars.trainmath', 'CFBundleShortVersionString': '1.0.0',
                'CFBundleVersion': '1', 'CFBundleSupportedPlatforms': ['iPhoneSimulator'],
                'DTXcodeBuild': '17C529', 'DTSDKName': 'iphonesimulator26.2'}))
            for f in files:
                z.writestr('App.app/public/' + f['path'], b'x')
        manifest = self.root / 'manifest.json'
        manifest.write_text(json.dumps({'appId': 'tw.mars.trainmath', 'remoteServer': False,
            'webSourceVersion': web_version, 'webDir': 'dist-native', 'files': files, 'bytes': 165}))
        return archive, manifest

    def validator_for(self, version, archive, manifest):
        function = next(n for n in self.tree.body if isinstance(n, ast.FunctionDef) and n.name == 'verify_payload')
        import stat
        scope = dict(hashlib=hashlib, json=json, pathlib=__import__('pathlib'), plistlib=plistlib,
            re=re, stat=stat, zipfile=zipfile, APP_ID='tw.mars.trainmath', EXPECTED_WEB_VERSION=version,
            ZIP_SHA=hashlib.sha256(archive.read_bytes()).hexdigest(), MANIFEST_SHA=hashlib.sha256(manifest.read_bytes()).hexdigest())
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(WORKFLOW), 'exec'), scope)
        return scope['verify_payload']

    def test_current_version_read_from_source_and_actual_version_reported(self):
        self.assertIn("pathlib.Path('package.json').read_text(encoding='utf-8')", self.source)
        self.assertIn('actions/checkout@', self.source)
        self.assertNotIn('1.11.0', self.source)
        for version in ['1.13.0', '2.5.0']:
            archive, manifest = self.payload(version)
            result = self.validator_for(version, archive, manifest)(archive, manifest)
            self.assertEqual(result['webVersion'], version)
            self.assertEqual(result['verifiedPayloadFiles'], 165)

    def test_old_artifact_is_rejected_for_current_source(self):
        archive, manifest = self.payload('1.11.0')
        with self.assertRaisesRegex(ValueError, 'Unexpected native payload manifest'):
            self.validator_for('1.13.0', archive, manifest)(archive, manifest)

    def test_hash_tampering_still_rejected(self):
        archive, manifest = self.payload('1.13.0')
        verify = self.validator_for('1.13.0', archive, manifest)
        archive.write_bytes(archive.read_bytes() + b'tamper')
        with self.assertRaisesRegex(ValueError, 'Simulator ZIP differs'):
            verify(archive, manifest)


if __name__ == '__main__':
    unittest.main()
