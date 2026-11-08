"""Isolated transport/schema fixtures reuse existing words; no product translations."""
from __future__ import annotations

import copy
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from tools.lexicon import pipeline as legacy
from tools.lexicon_expand import catalog, generation, planning, provider, responses, sources
from tools.lexicon_expand.common import CACHE, DATA, Invalid, canonical, digest, read_json, word_key, write_json


class ExpansionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.legacy = legacy.validate()
        # Both words and their Chinese strings come from the existing review batch.
        cls.existing = cls.legacy.entries[0]
        cls.source = cls.legacy.sources[cls.existing["source_entry_sha256"]]

    def setUp(self):
        (CACHE / "tests").mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=CACHE / "tests")
        self.directory = Path(self.temporary.name)
        self.config_path = self.directory / "config.json"
        self.config = {"base_url": "https://provider.invalid/v1", "model": "test-model",
                       "api_key_env": "STUDYIME_TEST_ONLY_KEY", "max_output_tokens": 4096}
        write_json(self.config_path, self.config)
        reference = {"id": "test-reference", "chinese": self.existing["chinese"],
                     "pinyin": self.source["pinyin"], "source_row_sha256": self.existing["source_entry_sha256"]}
        self.target = {"target_id": "test-target", "english": self.existing["commit_english"],
                       "packs": ["test-only"], "source_refs": [], "dictionary_references": [reference]}
        self.job = planning.make_job("map_targets", [self.target], "TEST TRANSPORT FIXTURE ONLY")
        self.plan = {"schema_version": 2, "maximum_items": 1, "request_count": 1,
                     "prepared_directory": str(self.directory / "prepared"), "prompt_sha256": "test-prompt"}
        self.plan_directory = self.directory / "plan"
        self.output = self.directory / "results"
        self.reply = {"results": [{
            "target_id": self.target["target_id"], "english": self.target["english"],
            "senses": [{"chinese": self.existing["chinese"], "pinyin": self.source["pinyin"],
                        "pos": "phrase", "meaning_zh": self.existing["category"],
                        "source_ref_ids": ["test-reference"]}], "unresolved_reason": None}]}
        self.metadata = {"kind": "test-only", "model": "test-model"}
        self.key = "TEST-CREDENTIAL-FOR-TRANSPORT-ONLY"

    def tearDown(self):
        self.temporary.cleanup()

    def envelope(self, reply=None, finish_reason="stop"):
        return canonical({"model": "test-model", "choices": [{"finish_reason": finish_reason,
            "message": {"content": json.dumps(self.reply if reply is None else reply, ensure_ascii=False)}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 40, "total_tokens": 60}})

    def validate(self, reply=None, job=None):
        return responses.validate_reply(json.dumps(self.reply if reply is None else reply),
                                        self.job if job is None else job, self.metadata)

    def run_generation(self, raw=None, **kwargs):
        with patch.object(generation, "load_plan", return_value=(self.plan, [self.job])), \
             patch.object(provider, "read_key", return_value=self.key), \
             patch.object(provider, "complete", return_value=self.envelope() if raw is None else raw) as call:
            result = generation.generate(self.plan_directory, self.config_path, self.output,
                                          execute=True, **kwargs)
            return result, call.call_count

    def test_ecdict_projection_uses_exact_exam_tag_and_omits_definitions(self):
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=["word", "tag", "bnc", "frq", "translation"])
        writer.writeheader()
        writer.writerow({"word": self.target["english"], "tag": "ielts cet4", "bnc": "1", "frq": "2",
                         "translation": "TEST SOURCE CONTENT MUST NOT BE COPIED\nSECOND LINE"})
        writer.writerow({"word": "excluded", "tag": "notielts", "bnc": "", "frq": "", "translation": ""})
        rows = sources.project_ecdict(stream.getvalue().encode())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_row"], 1)
        self.assertNotIn("translation", rows[0])
        self.assertNotIn("TEST SOURCE CONTENT", json.dumps(rows))

    def test_pinned_source_facts_and_cefr_variants_are_preserved(self):
        targets, _ = sources.targets_from_sources()
        ielts = [target for target in targets if "ielts" in target["packs"]]
        cefr = [target for target in targets if "cefr" in target["packs"]]
        self.assertEqual(len(ielts), 5040)
        self.assertEqual(len(cefr), 8845)
        self.assertEqual(len(targets), 10625)
        by_word = {target["english"]: target for target in targets}
        self.assertIn("A.M.", by_word["a.m."]["source_forms"])
        self.assertTrue(all(target["source_refs"] for target in targets))

    def test_tampered_source_excerpt_is_rejected(self):
        data = self.directory / "data"
        data.mkdir()
        lock = read_json(DATA / "sources.lock.json")
        path = self.directory / "changed.jsonl"
        path.write_text("{}\n")
        lock["sources"][0]["local_file"] = path.relative_to(legacy.ROOT).as_posix()
        write_json(data / "sources.lock.json", lock)
        with self.assertRaisesRegex(Invalid, "Changed source excerpt"):
            sources.verify_sources(data)

    def test_reference_matching_does_not_invent_synonyms(self):
        keys = {key for key, _, _ in catalog.reference_keys("to book/volume; register/")}
        self.assertIn("book", keys)
        self.assertIn("volume; register", keys)
        self.assertNotIn("volume", keys)
        self.assertNotIn("reserve", keys)

    def test_rejected_existing_record_is_not_counted_as_a_draft(self):
        target = {"existing_entries": [{"review_status": "rejected", "input_dictionary_reachable": True}],
                  "dictionary_reference_count": 1, "reachable_reference_count": 1, "api_eligible": True}
        counts = catalog.coverage_counts([target])
        self.assertEqual(counts["with_existing_draft"], 0)
        self.assertEqual(counts["with_approved_existing_entry"], 0)
        self.assertEqual(counts["with_dictionary_reference"], 1)

    def test_chinese_reachability_matches_existing_filter(self):
        self.assertEqual(catalog.input_reading(self.existing["chinese"], self.source["pinyin"]), "ni hao")
        self.assertIsNone(catalog.input_reading("A股", "A gu3"))
        self.assertIsNone(catalog.input_reading("你好", "ni hao"))

    def test_real_catalog_and_default_plan_have_no_generated_translations(self):
        prepared = self.directory / "prepared"
        summary = catalog.prepare(prepared)
        self.assertEqual(summary["coverage"]["ielts"]["with_dictionary_reference"], 4130)
        self.assertEqual(summary["coverage"]["ielts"]["without_dictionary_reference"], 910)
        self.assertEqual(summary["coverage"]["all"]["with_approved_existing_entry"], 0)
        self.assertEqual(summary["generated_translations"], 0)
        first = planning.make_plan(prepared, self.plan_directory)
        before = (self.plan_directory / "requests.jsonl").read_bytes()
        second = planning.make_plan(prepared, self.plan_directory)
        self.assertEqual(first, second)
        self.assertEqual(before, (self.plan_directory / "requests.jsonl").read_bytes())
        plan, jobs = planning.load_plan(self.plan_directory)
        self.assertEqual(plan["maximum_items"], 300)
        self.assertEqual(plan["word_targets"], 200)
        self.assertEqual(plan["scene_slots"], 100)
        self.assertEqual(len(jobs), 40)
        self.assertTrue(all(t["english"] is None for j in jobs if j["task"] == "scene_terms"
                            for t in j["payload"]["targets"]))
        (self.plan_directory / "requests.jsonl").write_bytes(before + b"\n")
        with self.assertRaisesRegex(Invalid, "checksum"):
            planning.load_plan(self.plan_directory)

    def test_planner_rejects_empty_or_invalid_budgets(self):
        for words, scenes, batch in ((0, 0, 10), (-1, 10, 10), (1, 0, 0), (1, 0, 21)):
            with self.subTest(words=words, scenes=scenes, batch=batch), self.assertRaises(Invalid):
                planning.make_plan(word_count=words, scene_count=scenes, batch_size=batch)

    def test_endpoint_normalization(self):
        for base, suffix in (("https://provider.invalid", "/v1/chat/completions"),
                             ("https://provider.invalid/v1/", "/v1/chat/completions"),
                             ("https://provider.invalid/api", "/api/chat/completions"),
                             ("https://provider.invalid/v1/chat/completions", "/v1/chat/completions")):
            write_json(self.config_path, {**self.config, "base_url": base})
            self.assertEqual(provider.load_config(self.config_path)["endpoint"], "https://provider.invalid" + suffix)

    def test_config_rejects_embedded_keys_and_credential_urls(self):
        for changes in ({"api_key": self.key}, {"base_url": "http://provider.invalid/v1"},
                        {"base_url": "https://name:secret@provider.invalid/v1"},
                        {"base_url": "https://provider.invalid/v1?key=secret"}):
            write_json(self.config_path, {**self.config, **changes})
            with self.assertRaises(Invalid) as caught:
                provider.load_config(self.config_path)
            self.assertNotIn(self.key, str(caught.exception))

    def test_redirect_does_not_forward_request(self):
        self.assertIsNone(provider.NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.invalid"))

    def test_request_body_contains_no_api_key(self):
        body = provider.request_body(provider.load_config(self.config_path), self.job)
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertEqual(body["max_tokens"], 4096)
        self.assertNotIn(self.key, json.dumps(body))

    def test_explicit_reasoning_effort_is_forwarded_without_changing_old_configs(self):
        original = provider.load_config(self.config_path)
        self.assertNotIn("reasoning_effort", original)
        self.assertNotIn("reasoning_effort", provider.request_body(original, self.job))
        write_json(self.config_path, {**self.config, "reasoning_effort": "high"})
        configured = provider.load_config(self.config_path)
        self.assertEqual(provider.request_body(configured, self.job)["reasoning_effort"], "high")

    def test_http_failure_body_is_not_exposed(self):
        error = HTTPError("https://provider.invalid", 401, self.key, {}, io.BytesIO(self.key.encode()))
        with patch.object(provider, "build_opener") as build:
            build.return_value.open.side_effect = error
            with self.assertRaises(provider.ProviderFailure) as caught:
                provider.complete(provider.load_config(self.config_path), self.key, self.job)
        self.assertIn("401", str(caught.exception))
        self.assertNotIn(self.key, str(caught.exception))

    def test_json_provider_error_retains_reason_and_redacts_credentials(self):
        message = "No available model channel; " + self.key + " sk-OTHERTESTCREDENTIAL123"
        error = HTTPError("https://provider.invalid", 503, "Unavailable",
                          {"Content-Type": "application/json"},
                          io.BytesIO(canonical({"error": {"message": message}})))
        with patch.object(provider, "build_opener") as build:
            build.return_value.open.side_effect = error
            with self.assertRaises(provider.ProviderFailure) as caught:
                provider.complete(provider.load_config(self.config_path), self.key, self.job)
        self.assertIn("No available model channel", str(caught.exception))
        self.assertNotIn(self.key, str(caught.exception))
        self.assertNotIn("sk-OTHERTESTCREDENTIAL123", str(caught.exception))

    def test_non_json_provider_error_content_is_withheld(self):
        error = HTTPError("https://provider.invalid", 403, "Forbidden",
                          {"Content-Type": "text/html"}, io.BytesIO(self.key.encode()))
        with patch.object(provider, "build_opener") as build:
            build.return_value.open.side_effect = error
            with self.assertRaises(provider.ProviderFailure) as caught:
                provider.complete(provider.load_config(self.config_path), self.key, self.job)
        self.assertIn("response body withheld", str(caught.exception))
        self.assertNotIn(self.key, str(caught.exception))

    def test_valid_drafts_are_pending_and_have_no_selected_sense(self):
        record = self.validate()[0]
        self.assertEqual(record["review"]["status"], "pending")
        self.assertIsNone(record["review"]["reviewer"])
        self.assertIsNone(record["selected_sense_id"])
        self.assertFalse(record["release_ready"])
        self.assertEqual(record["senses"][0]["display_english"], record["senses"][0]["commit_english"])

    def test_model_cannot_inject_an_approval(self):
        self.reply["results"][0]["review"] = {"status": "approved-for-distribution"}
        with self.assertRaisesRegex(Invalid, "Unexpected result fields"):
            self.validate()

    def test_model_cannot_substitute_target_word(self):
        self.reply["results"][0]["english"] = "different"
        with self.assertRaisesRegex(Invalid, "substituted"):
            self.validate()

    def test_model_cannot_add_or_omit_target_ids(self):
        self.reply["results"].append(copy.deepcopy(self.reply["results"][0]))
        with self.assertRaisesRegex(Invalid, "omitted or added"):
            self.validate()

    def test_model_cannot_fabricate_source_reference(self):
        self.reply["results"][0]["senses"][0]["source_ref_ids"] = ["invented-reference"]
        with self.assertRaisesRegex(Invalid, "Unknown or repeated dictionary"):
            self.validate()

    def test_pinyin_and_trigger_must_be_complete(self):
        self.reply["results"][0]["senses"][0]["pinyin"] = "ni3"
        with self.assertRaisesRegex(Invalid, "one numbered syllable"):
            self.validate()

    def test_truncated_english_cannot_be_submitted(self):
        self.reply["results"][0]["english"] += "..."
        with self.assertRaisesRegex(Invalid, "truncated"):
            self.validate()

    def test_unresolved_target_is_preserved_without_a_translation(self):
        result = self.reply["results"][0]
        result.update(senses=[], unresolved_reason="TEST-ONLY UNRESOLVED FIXTURE")
        record = self.validate()[0]
        self.assertEqual(record["senses"], [])
        self.assertFalse(record["release_ready"])

    def test_duplicate_scene_terms_are_rejected(self):
        targets = [{**self.target, "target_id": f"slot-{number}", "english": None} for number in (1, 2)]
        job = planning.make_job("scene_terms", targets, "TEST ONLY")
        reply = {"results": [{**copy.deepcopy(self.reply["results"][0]), "target_id": target["target_id"]}
                             for target in targets]}
        with self.assertRaisesRegex(Invalid, "Repeated English term"):
            self.validate(reply, job)

    def test_truncated_provider_response_is_rejected(self):
        with self.assertRaisesRegex(Invalid, "incomplete or truncated"):
            provider.decode_response(self.envelope(finish_reason="length"))

    def test_dry_run_never_reads_key_or_calls_provider(self):
        with patch.object(generation, "load_plan", return_value=(self.plan, [self.job])), \
             patch.object(provider, "read_key") as key, patch.object(provider, "complete") as call:
            result = generation.generate(self.plan_directory, self.config_path, self.output)
        key.assert_not_called()
        call.assert_not_called()
        self.assertEqual(result["model_requests"], 0)
        self.assertFalse(self.output.exists())

    def test_completed_run_resumes_without_duplicate_call_or_key_access(self):
        summary, calls = self.run_generation()
        self.assertEqual(calls, 1)
        self.assertEqual(summary["resolved_draft_items"], 1)
        self.assertEqual(summary["status"], "pending-language-review")
        self.assertEqual(summary["human_approved_items"], 0)
        self.assertEqual(summary["provider_reported_usage"]["total_tokens"], 60)
        with patch.object(generation, "load_plan", return_value=(self.plan, [self.job])), \
             patch.object(provider, "read_key") as key, patch.object(provider, "complete") as call:
            resumed = generation.generate(self.plan_directory, self.config_path, self.output, execute=True)
        key.assert_not_called()
        call.assert_not_called()
        self.assertEqual(summary, resumed)
        for path in self.output.rglob("*"):
            if path.is_file():
                self.assertNotIn(self.key.encode(), path.read_bytes())

    def test_invalid_response_is_atomic_and_requires_explicit_retry(self):
        self.reply["results"][0]["review"] = {"status": "approved-for-distribution"}
        with self.assertRaises(Invalid):
            self.run_generation()
        self.assertEqual((self.output / "drafts.jsonl").read_bytes(), b"")
        self.assertEqual(read_json(self.output / "summary.json")["returned_items"], 0)
        self.assertEqual(read_json(self.output / "summary.json")["status"], "generation-incomplete")
        with self.assertRaisesRegex(Invalid, "retry-failed"):
            self.run_generation()

    def test_changed_saved_response_is_rejected_on_resume(self):
        self.run_generation()
        (self.output / "responses/00001.json").write_bytes(b"{}")
        with self.assertRaisesRegex(Invalid, "Saved provider response changed"):
            self.run_generation()

    def test_changed_model_cannot_reuse_existing_output(self):
        self.run_generation()
        write_json(self.config_path, {**self.config, "model": "another-test-model"})
        with self.assertRaisesRegex(Invalid, "another plan/configuration"):
            self.run_generation()

    def test_caps_prevent_provider_access(self):
        for changes in ({"max_items": 0}, {"max_requests": 0}, {"max_output_budget": 100}):
            with self.subTest(changes=changes), \
                 patch.object(generation, "load_plan", return_value=(self.plan, [self.job])), \
                 patch.object(provider, "read_key") as key, patch.object(provider, "complete") as call:
                with self.assertRaises(Invalid):
                    generation.generate(self.plan_directory, self.config_path, self.output, execute=True, **changes)
                call.assert_not_called()
                key.assert_not_called()

    def test_multiple_senses_are_preserved_without_automatic_selection(self):
        additional = copy.deepcopy(self.reply["results"][0]["senses"][0])
        additional["pos"] = "interj"
        additional["meaning_zh"] = self.existing["modification"]
        self.reply["results"][0]["senses"].append(additional)
        record = self.validate()[0]
        self.assertEqual(len(record["senses"]), 2)
        self.assertEqual(len({sense["id"] for sense in record["senses"]}), 2)
        self.assertIsNone(record["selected_sense_id"])

    def test_truncated_response_still_records_reported_token_usage(self):
        with self.assertRaises(Invalid):
            self.run_generation(raw=self.envelope(finish_reason="length"))
        summary = read_json(self.output / "summary.json")
        self.assertEqual(summary["provider_reported_usage"]["total_tokens"], 60)
        self.assertEqual(summary["returned_items"], 0)

    def test_uncertain_attempt_does_not_retry_automatically(self):
        self.run_generation()
        path = self.output / "attempts/00001.json"
        attempt = read_json(path)
        attempt["status"] = "started"
        for field in ("records", "generation", "usage", "response_sha256", "finished_at"):
            attempt.pop(field, None)
        write_json(path, attempt)
        with patch.object(generation, "load_plan", return_value=(self.plan, [self.job])), \
             patch.object(provider, "read_key") as key, patch.object(provider, "complete") as call:
            with self.assertRaisesRegex(Invalid, "retry-uncertain"):
                generation.generate(self.plan_directory, self.config_path, self.output, execute=True)
        key.assert_not_called()
        call.assert_not_called()

    def test_retry_caps_include_already_failed_attempt(self):
        with self.assertRaises(Invalid):
            self.run_generation(raw=self.envelope(finish_reason="length"))
        with patch.object(generation, "load_plan", return_value=(self.plan, [self.job])), \
             patch.object(provider, "read_key") as key, patch.object(provider, "complete") as call:
            with self.assertRaisesRegex(Invalid, "total attempt cap"):
                generation.generate(self.plan_directory, self.config_path, self.output, execute=True,
                                    retry_failed=True, max_requests=1)
        key.assert_not_called()
        call.assert_not_called()

    def test_partial_run_retries_only_the_failed_request(self):
        second_target = {**self.target, "target_id": "second-test-target"}
        second = planning.make_job("map_targets", [second_target], "TEST TRANSPORT FIXTURE ONLY")
        plan = {**self.plan, "maximum_items": 2, "request_count": 2}
        with patch.object(generation, "load_plan", return_value=(plan, [self.job, second])), \
             patch.object(provider, "read_key", return_value=self.key), \
             patch.object(provider, "complete", side_effect=[self.envelope(), provider.ProviderFailure("HTTP 503")]) as call:
            with self.assertRaises(Invalid):
                generation.generate(self.plan_directory, self.config_path, self.output, execute=True)
            self.assertEqual(call.call_count, 2)
        self.assertEqual(read_json(self.output / "summary.json")["status"], "generation-incomplete")
        reply = copy.deepcopy(self.reply)
        reply["results"][0]["target_id"] = second_target["target_id"]
        with patch.object(generation, "load_plan", return_value=(plan, [self.job, second])), \
             patch.object(provider, "read_key", return_value=self.key), \
             patch.object(provider, "complete", return_value=self.envelope(reply)) as call:
            summary = generation.generate(self.plan_directory, self.config_path, self.output,
                                          execute=True, retry_failed=True, max_requests=3)
            self.assertEqual(call.call_count, 1)
            self.assertEqual(call.call_args.args[2]["id"], second["id"])
        self.assertEqual(summary["returned_items"], 2)
        self.assertEqual(summary["attempts"], 3)

    def test_echoed_credential_is_not_written(self):
        with self.assertRaises(Invalid):
            self.run_generation(raw=canonical({"echo": self.key}))
        for path in self.output.rglob("*"):
            if path.is_file():
                self.assertNotIn(self.key.encode(), path.read_bytes())

    def test_selection_does_not_send_other_requests_and_preserves_resume_identity(self):
        second = planning.make_job('map_targets', [{**self.target, 'target_id': 'second'}], 'TEST ONLY')
        plan = {**self.plan, 'maximum_items': 2, 'request_count': 2}
        with patch.object(generation, 'load_plan', return_value=(plan, [self.job, second])), \
             patch.object(provider, 'read_key', return_value=self.key), \
             patch.object(provider, 'complete', return_value=self.envelope()) as call:
            generation.generate(self.plan_directory, self.config_path, self.output, execute=True, request_ids=[self.job['id']])
            self.assertEqual(call.call_count, 1)
            call.reset_mock()
            generation.generate(self.plan_directory, self.config_path, self.output, execute=True, request_ids=[self.job['id']])
            call.assert_not_called()
            with self.assertRaisesRegex(Invalid, 'Unknown selected'):
                generation.generate(self.plan_directory, self.config_path, self.output, execute=True, request_ids=['invalid'])
            call.assert_not_called()

    def test_run_lock_releases_after_failure(self):
        with generation.run_lock(self.output):
            with self.assertRaises(Invalid):
                with generation.run_lock(self.output):
                    pass
        with generation.run_lock(self.output):
            pass

    def test_parallel_owners_resume_without_duplicate_calls(self):
        from tools.lexicon_expand import parallel_run
        second = planning.make_job('map_targets', [{**self.target, 'target_id': 'second'}], 'TEST ONLY')
        plan = {**self.plan, 'maximum_items': 2, 'request_count': 2}
        write_json(self.directory / 'api.local.json', self.config)
        write_json(self.directory / 'api.grok.local.json', {**self.config, 'model': 'second-model', 'reasoning_effort': 'high'})
        def response(config, key, job):
            reply = copy.deepcopy(self.reply)
            reply['results'][0]['target_id'] = job['payload']['targets'][0]['target_id']
            return self.envelope(reply)
        with patch.object(parallel_run, 'CACHE', self.directory), \
             patch.object(parallel_run, 'load_plan', return_value=(plan, [self.job, second])), \
             patch.object(generation, 'load_plan', return_value=(plan, [self.job, second])), \
             patch.object(provider, 'read_key', return_value=self.key), \
             patch.object(provider, 'complete', side_effect=response) as call:
            summary = parallel_run.run(execute=True)
            self.assertEqual(summary['returned_items'], 2)
            self.assertEqual(summary['attempts_including_legacy'], 4)
            self.assertEqual(len(summary['items_by_model']), 2)
            self.assertEqual(call.call_count, 2)
            call.reset_mock()
            parallel_run.run(execute=True)
            call.assert_not_called()
            config = provider.load_config(self.directory / 'api.grok.local.json')
            self.assertEqual(provider.request_body(config, second)['reasoning_effort'], 'high')

    def test_parallel_provider_failure_stops_its_remaining_requests(self):
        from tools.lexicon_expand import parallel_run
        jobs = [planning.make_job('map_targets', [{**self.target, 'target_id': str(i)}], 'TEST ONLY') for i in range(4)]
        plan = {**self.plan, 'maximum_items': 4, 'request_count': 4}
        for name in ('api.local.json', 'api.grok.local.json'):
            write_json(self.directory / name, self.config)
        with patch.object(parallel_run, 'CACHE', self.directory), \
             patch.object(parallel_run, 'load_plan', return_value=(plan, jobs)), \
             patch.object(generation, 'load_plan', return_value=(plan, jobs)), \
             patch.object(provider, 'read_key', return_value=self.key), \
             patch.object(provider, 'complete', side_effect=provider.ProviderFailure('HTTP 504')) as call:
            summary = parallel_run.run(execute=True)
            self.assertEqual(call.call_count, 2)
            self.assertEqual(summary['attempts_including_legacy'], 4)
            self.assertEqual(summary['returned_items'], 0)


if __name__ == "__main__":
    unittest.main()
