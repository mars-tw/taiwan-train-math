"""Unit checks for exact-run draft reconciliation; no GitHub mutation."""

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "archive-ios-store-release.py"
SPEC = importlib.util.spec_from_file_location("train_archive", SCRIPT)
archive = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(archive)

TAG = "trainmath-1.0.0-b2-38334544182"
SHA = "a9ad9c1375c493bda10777e8577289e039dab50d"


class DraftReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.evidence = Path(self.temp.name) / f"trainmath-1.0.0-b2-evidence-38334544182.zip"
        self.evidence.write_bytes(b"same-run signed evidence fixture")
        self.digest = hashlib.sha256(self.evidence.read_bytes()).hexdigest()
        self.notes = Path(self.temp.name) / "release-notes.txt"
        self.notes.write_text("review artifact", encoding="utf-8")
        self.release = {
            "id": 411178191, "tag_name": TAG, "draft": True,
            "target_commitish": SHA, "name": "Train Math 1.0.0 build 2 (38334544182)",
            "assets": [{"id": 635603800, "name": self.evidence.name,
                        "state": "uploaded", "size": self.evidence.stat().st_size,
                        "digest": "sha256:" + self.digest}],
        }

    def test_authenticated_list_finds_draft_that_tag_endpoint_misses(self):
        with patch.object(archive, "run_gh", return_value=json.dumps([[self.release]]).encode()) as gh:
            found = archive.find_exact_draft(TAG)
        self.assertEqual(found["id"], 411178191)
        self.assertIn("--paginate", gh.call_args.args)
        self.assertNotIn("/releases/tags/", " ".join(gh.call_args.args))

    def test_existing_exact_draft_is_reconciled_without_create(self):
        with patch.object(archive, "find_exact_draft", return_value=self.release), \
                patch.object(archive.subprocess, "run") as create:
            found, created = archive.create_or_reconcile_draft(
                TAG, SHA, self.evidence, self.notes, self.digest)
        self.assertEqual(found["id"], self.release["id"])
        self.assertFalse(created)
        create.assert_not_called()

    def test_mismatched_existing_asset_stops_without_create(self):
        changed = {**self.release, "assets": [{**self.release["assets"][0], "digest": "sha256:" + "0" * 64}]}
        with patch.object(archive, "find_exact_draft", return_value=changed), \
                patch.object(archive.subprocess, "run") as create:
            with self.assertRaises(SystemExit):
                archive.create_or_reconcile_draft(TAG, SHA, self.evidence, self.notes, self.digest)
        create.assert_not_called()

    def test_uncertain_create_reconciles_same_draft_without_retrying_create(self):
        with patch.object(archive, "find_exact_draft", side_effect=[None, self.release]), \
                patch.object(archive.subprocess, "run", return_value=SimpleNamespace(returncode=1)) as create:
            found, created = archive.create_or_reconcile_draft(
                TAG, SHA, self.evidence, self.notes, self.digest)
        self.assertEqual(found["id"], self.release["id"])
        self.assertFalse(created)
        create.assert_called_once()

    def test_successful_create_is_verified_from_draft_list(self):
        with patch.object(archive, "find_exact_draft", side_effect=[None, self.release]), \
                patch.object(archive.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as create:
            found, created = archive.create_or_reconcile_draft(
                TAG, SHA, self.evidence, self.notes, self.digest)
        self.assertEqual(found["id"], self.release["id"])
        self.assertTrue(created)
        create.assert_called_once()

    def test_published_tag_is_rejected(self):
        published = {**self.release, "draft": False}
        with patch.object(archive, "run_gh", return_value=json.dumps([[published]]).encode()):
            with self.assertRaises(SystemExit):
                archive.find_exact_draft(TAG)


if __name__ == "__main__":
    unittest.main()
