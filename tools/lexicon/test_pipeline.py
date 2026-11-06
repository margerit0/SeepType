"""Approval tests use isolated synthetic review records, never product approvals."""
import copy
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

import pipeline as p


class LexiconTests(unittest.TestCase):
    def setUp(self):
        parent = (p.ROOT / ".cache/lexicon-tests").resolve()
        parent.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=parent)
        self.directory = Path(self.temporary.name).resolve()
        self.assertTrue(self.directory.is_relative_to(parent))
        shutil.copytree(p.DATA, self.directory, dirs_exist_ok=True)
        self.lexicon = p.validate(self.directory)

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, data):
        p.atomic_write(self.directory / "entries.json", p.json_bytes(data))

    def review(self, entries=None, status="approved-for-distribution"):
        entries = self.lexicon.entries if entries is None else entries
        return {"schema_version": 1, "base_sha256": self.lexicon.content_hash, "method": "human",
                "reviewer": "SYNTHETIC TEST REVIEWER — not product approval",
                "reviewed_at": "2026-11-07T00:00:00+08:00",
                "decisions": [{"id": e["id"], "original_sha256": p.entry_hash(e, self.lexicon.lock),
                               "english": e["commit_english"], "status": status} for e in entries]}

    def approved(self):
        updated = p.apply_review(self.lexicon, self.review())
        return p.validate(self.directory, data_override=updated)

    def test_real_batch_has_no_human_approvals(self):
        self.assertEqual(len(self.lexicon.entries), 200)
        self.assertEqual(self.lexicon.counts["pending"], 200)
        self.assertEqual(self.lexicon.counts["approved-for-distribution"], 0)
        self.assertEqual(len(self.lexicon.sources), 202)

    def test_unreviewed_release_is_rejected_before_output(self):
        output = self.directory / "blocked-output"
        with self.assertRaisesRegex(p.Invalid, "200 entries await"):
            p.export(self.lexicon, output, "release")
        self.assertFalse(output.exists())

    def test_preview_remains_explicitly_development_data(self):
        files = p.build_files(self.lexicon, "preview")
        manifest = json.loads(files["manifest.json"])
        self.assertFalse(manifest["product_data"])
        self.assertFalse(manifest["release_ready"])
        self.assertEqual(manifest["exported_entries"], 200)
        self.assertIn(b"REVIEW PREVIEW", files["lexicon.lua"])

    def test_preview_is_reproducible_with_complete_attribution(self):
        first = p.build_files(self.lexicon, "preview")
        second = p.build_files(p.validate(self.directory), "preview")
        self.assertEqual(p.zip_bytes(first), p.zip_bytes(second))
        manifest = json.loads(first["manifest.json"])
        for name, digest in manifest["files"].items():
            self.assertEqual(p.sha256(first[name]), digest)
        with zipfile.ZipFile(io.BytesIO(p.zip_bytes(first))) as archive:
            self.assertIn("NOTICE.txt", archive.namelist())
            self.assertIn("licenses/CC-BY-SA-4.0.txt", archive.namelist())
            self.assertIn("sources/entries.json", archive.namelist())
            self.assertTrue(all(item.date_time == (1980, 1, 1, 0, 0, 0) for item in archive.infolist()))

    def test_altered_source_excerpt_is_rejected(self):
        source = self.directory / "sources/entries.json"
        source.write_bytes(source.read_bytes() + b" ")
        with self.assertRaisesRegex(p.Invalid, "hash mismatch"):
            p.validate(self.directory)

    def test_unverified_source_license_is_rejected(self):
        lock = copy.deepcopy(self.lexicon.lock)
        lock["license_review"]["status"] = "pending"
        p.atomic_write(self.directory / "source.lock.json", p.json_bytes(lock))
        with self.assertRaisesRegex(p.Invalid, "license has not been verified"):
            p.validate(self.directory)

    def test_wrong_source_word_cannot_be_attached(self):
        data = copy.deepcopy(self.lexicon.data)
        data["entries"][0]["source_entry_sha256"] = data["entries"][1]["source_entry_sha256"]
        with self.assertRaisesRegex(p.Invalid, "mismatched source"):
            p.validate(self.directory, data_override=data)

    def test_duplicate_chinese_words_are_rejected(self):
        data = copy.deepcopy(self.lexicon.data)
        data["entries"][1]["chinese"] = data["entries"][0]["chinese"]
        with self.assertRaisesRegex(p.Invalid, "Duplicate Chinese"):
            p.validate(self.directory, data_override=data)

    def test_duplicate_ids_are_rejected(self):
        data = copy.deepcopy(self.lexicon.data)
        data["entries"][1]["id"] = data["entries"][0]["id"]
        with self.assertRaisesRegex(p.Invalid, "Duplicate entry ID"):
            p.validate(self.directory, data_override=data)

    def test_dictionary_metadata_and_control_characters_cannot_commit(self):
        for value in ["CL: apples", "see also apple", "variant of apple", "hello...",
                      "(computing) mouse", "line\nbreak", "bad\0text", 'quote"escape', "中文"]:
            with self.subTest(value=value), self.assertRaises(p.Invalid):
                p.english(value)
        self.assertEqual(p.english("see you later"), "see you later")
        self.assertEqual(p.english("you're welcome"), "you're welcome")

    def test_v1_cannot_silently_export_different_display_and_commit(self):
        data = copy.deepcopy(self.lexicon.data)
        data["entries"][0]["display_english"] = "greeting"
        with self.assertRaisesRegex(p.Invalid, "identical display and commit"):
            p.validate(self.directory, data_override=data)

    def test_one_human_decision_does_not_approve_other_entries(self):
        updated = p.apply_review(self.lexicon, self.review(self.lexicon.entries[:1]))
        checked = p.validate(self.directory, data_override=updated)
        self.assertEqual(checked.counts["approved-for-distribution"], 1)
        self.assertEqual(checked.counts["pending"], 199)
        with self.assertRaisesRegex(p.Invalid, "199 entries await"):
            p.build_files(checked, "release")

    def test_human_edit_records_exact_new_text_and_provenance(self):
        review = self.review(self.lexicon.entries[:1])
        review["decisions"][0]["english"] = "hi"
        updated = p.apply_review(self.lexicon, review)
        checked = p.validate(self.directory, data_override=updated)
        entry = checked.entries[0]
        self.assertEqual(entry["commit_english"], "hi")
        self.assertEqual(entry["display_english"], "hi")
        self.assertIn("hello → hi", entry["modification"])
        self.assertEqual(entry["review"]["content_sha256"], p.entry_hash(entry, checked.lock))

    def test_changed_text_invalidates_prior_approval(self):
        checked = self.approved()
        checked.entries[0]["display_english"] = checked.entries[0]["commit_english"] = "hi"
        with self.assertRaisesRegex(p.Invalid, "Stale review"):
            p.build_files(checked, "release")

    def test_old_batch_review_is_rejected(self):
        review = self.review()
        review["base_sha256"] = "0" * 64
        with self.assertRaisesRegex(p.Invalid, "older or different"):
            p.apply_review(self.lexicon, review)

    def test_stale_entry_review_is_rejected(self):
        review = self.review()
        review["decisions"][0]["original_sha256"] = "0" * 64
        with self.assertRaisesRegex(p.Invalid, "Stale entry"):
            p.apply_review(self.lexicon, review)

    def test_duplicate_review_decision_is_rejected(self):
        review = self.review(self.lexicon.entries[:1])
        review["decisions"] *= 2
        with self.assertRaisesRegex(p.Invalid, "duplicate review entry"):
            p.apply_review(self.lexicon, review)

    def test_machine_method_cannot_become_human_approval(self):
        review = self.review()
        review["method"] = "automated"
        with self.assertRaisesRegex(p.Invalid, "Machine checks"):
            p.apply_review(self.lexicon, review)

    def test_reviewer_and_timezone_are_required(self):
        for key, value in [("reviewer", ""), ("reviewed_at", "2026-11-07T00:00:00")]:
            with self.subTest(key=key), self.assertRaises(p.Invalid):
                review = self.review()
                review[key] = value
                p.apply_review(self.lexicon, review)

    def test_pending_decision_clears_approval(self):
        checked = self.approved()
        self.lexicon = checked
        updated = p.apply_review(checked, self.review(checked.entries[:1], "pending"))
        checked = p.validate(self.directory, data_override=updated)
        self.assertEqual(checked.entries[0]["review"]["status"], "pending")
        self.assertIsNone(checked.entries[0]["review"]["reviewer"])
        self.assertFalse(p.summary(checked)["release_ready"])

    def test_rejected_entry_is_not_in_a_completed_release(self):
        review = self.review()
        review["decisions"][0]["status"] = "rejected"
        checked = p.validate(self.directory, data_override=p.apply_review(self.lexicon, review))
        files = p.build_files(checked, "release")
        self.assertNotIn('["你好"]', files["lexicon.lua"].decode("utf-8"))
        self.assertEqual(json.loads(files["manifest.json"])["exported_entries"], 199)
        self.assertTrue(json.loads(files["manifest.json"])["product_data"])

    def test_all_rejected_cannot_create_empty_release(self):
        checked = p.validate(self.directory, data_override=p.apply_review(
            self.lexicon, self.review(status="rejected")))
        with self.assertRaisesRegex(p.Invalid, "at least one approved"):
            p.build_files(checked, "release")

    def test_review_payload_cannot_close_script_element(self):
        self.lexicon.entries[0]["modification"] = "</script><img src=x onerror=alert(1)>"
        rendered = p.make_review(self.lexicon).decode("utf-8")
        self.assertNotIn("</script><img", rendered)
        self.assertIn("\\u003c/script>", rendered)

    def test_path_escape_and_duplicate_json_keys_are_rejected(self):
        with self.assertRaises(p.Invalid):
            p.inside(self.directory, "../outside")
        path = self.directory / "duplicate.json"
        path.write_text('{"status":"pending","status":"approved-for-distribution"}', encoding="utf-8")
        with self.assertRaisesRegex(p.Invalid, "Duplicate JSON"):
            p.read_json(path)

    def test_invalid_import_never_replaces_authoritative_file(self):
        data = copy.deepcopy(self.lexicon.data)
        data["entries"][0]["modification"] = "x" * 2040
        self.write(data)
        self.lexicon = p.validate(self.directory)
        review = self.review(self.lexicon.entries[:1])
        review["decisions"][0]["english"] = "hi"
        review_path = self.directory / "review-input.json"
        p.atomic_write(review_path, p.json_bytes(review))
        before = (self.directory / "entries.json").read_bytes()
        run = subprocess.run([sys.executable, str(Path(p.__file__)), "--data", str(self.directory),
                              "import-review", str(review_path)], capture_output=True, timeout=15)
        self.assertNotEqual(run.returncode, 0)
        self.assertEqual((self.directory / "entries.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
