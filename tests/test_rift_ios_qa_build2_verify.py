"""Structural verifier tests use synthetic profiles and never sign an app."""

import argparse
import datetime
import json
import pathlib
import plistlib
import tempfile
import unittest
import zipfile

from scripts import rift_ios_qa_build2_verify as verify


class RiftIpaStructureTests(unittest.TestCase):
    def write_ipa(self, folder: pathlib.Path, bundle: str, build: str = "2", expired: bool = False) -> pathlib.Path:
        path = folder / "synthetic.ipa"
        info = {
            "CFBundleIdentifier": bundle,
            "CFBundleDisplayName": "Rift Forge 3D",
            "CFBundleShortVersionString": "1.0.0",
            "CFBundleVersion": build,
        }
        profile = {
            "TeamIdentifier": [verify.TEAM_ID],
            "Entitlements": {
                "application-identifier": verify.TEAM_ID + "." + verify.APP_ID,
                "get-task-allow": False,
            },
            "DeveloperCertificates": [b"synthetic-certificate"],
            "UUID": "00000000-0000-0000-0000-000000000001",
            "ExpirationDate": datetime.datetime(2020 if expired else 2099, 1, 1),
        }
        with zipfile.ZipFile(path, "x") as archive:
            prefix = "Payload/Rift.app/"
            archive.writestr(prefix + "Info.plist", plistlib.dumps(info))
            archive.writestr(prefix + "embedded.mobileprovision", plistlib.dumps(profile))
            archive.writestr(prefix + "Frameworks/UnityFramework.framework/UnityFramework", b"synthetic")
        return path

    def test_valid_unity_archive_shape_writes_structure_receipt(self):
        with tempfile.TemporaryDirectory(prefix="rift-ipa-test-") as temporary:
            root = pathlib.Path(temporary)
            ipa = self.write_ipa(root, verify.APP_ID)
            receipt = root / "receipt.json"
            verify.ipa(argparse.Namespace(ipa=str(ipa), receipt=str(receipt)))
            result = json.loads(receipt.read_text())
            self.assertEqual(result["status"], "IPA_STRUCTURE_AND_PROFILE_VERIFIED")
            self.assertEqual(result["appId"], verify.APP_ID)
            self.assertFalse(result["physicalDeviceTested"])

    def test_other_bundle_is_rejected_before_receipt(self):
        with tempfile.TemporaryDirectory(prefix="rift-ipa-test-") as temporary:
            root = pathlib.Path(temporary)
            ipa = self.write_ipa(root, "tw.mars.othergame")
            receipt = root / "receipt.json"
            with self.assertRaises(SystemExit):
                verify.ipa(argparse.Namespace(ipa=str(ipa), receipt=str(receipt)))
            self.assertFalse(receipt.exists())

    def test_old_build_number_is_rejected_before_receipt(self):
        with tempfile.TemporaryDirectory(prefix="rift-ipa-test-") as temporary:
            root = pathlib.Path(temporary)
            ipa = self.write_ipa(root, verify.APP_ID, build="1")
            receipt = root / "receipt.json"
            with self.assertRaises(SystemExit):
                verify.ipa(argparse.Namespace(ipa=str(ipa), receipt=str(receipt)))
            self.assertFalse(receipt.exists())

    def test_expired_profile_is_rejected_before_receipt(self):
        with tempfile.TemporaryDirectory(prefix="rift-ipa-test-") as temporary:
            root = pathlib.Path(temporary)
            ipa = self.write_ipa(root, verify.APP_ID, expired=True)
            receipt = root / "receipt.json"
            with self.assertRaises(SystemExit):
                verify.ipa(argparse.Namespace(ipa=str(ipa), receipt=str(receipt)))
            self.assertFalse(receipt.exists())


if __name__ == "__main__":
    unittest.main()
