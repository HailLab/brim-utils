"""Offline client contract tests for the standalone Brim CLI."""

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests
import brim_utils as client


def response(code=200, data=None, text="", content_type="application/json"):
    result = Mock(status_code=code, text=text, headers={"Content-Type": content_type})
    result.json.return_value = {"data": data}
    return result


class PatientClientTests(unittest.TestCase):
    def setUp(self):
        self.request = patch.object(client.requests, "request").start()
        self.addCleanup(patch.stopall)

    def test_list_encodes_filters_and_auth(self):
        self.request.return_value = response(data={"patients": [], "count": 0})
        result = client.list_patients_by_last_document_load(
            7,
            "secret",
            "http://example/",
            days=0,
            limit=2,
            reference_date="2026-09-20T01:00:00+05:30",
            verify_ssl=False,
        )
        self.assertEqual(result["count"], 0)
        self.request.assert_called_once_with(
            "GET",
            "http://example/api/v1/projects/7/patients/by-last-document-load/",
            headers={"Authorization": "Bearer secret"},
            verify=False,
            timeout=60,
            params={
                "days": 0,
                "limit": 2,
                "reference_date": "2026-09-20T01:00:00+05:30",
            },
        )

    def test_list_defaults_do_not_send_reference_date(self):
        self.request.return_value = response(data={"patients": []})
        client.list_patients_by_last_document_load(7, "secret", "http://example")
        self.assertEqual(
            self.request.call_args.kwargs["params"], {"days": 14, "limit": 1000}
        )

    def test_delete_uses_mrns_preserves_leading_zeroes_and_deduplicates(self):
        self.request.return_value = response(202, {"task_id": "celery-id"})
        self.assertEqual(
            client.delete_patients(
                7, [" 001 ", "a,b", "001"], "secret", "http://example"
            ),
            {"task_id": "celery-id"},
        )
        self.assertEqual(
            self.request.call_args.args,
            ("DELETE", "http://example/api/v1/projects/7/patients/"),
        )
        self.assertEqual(
            self.request.call_args.kwargs["json"], {"patient_ids": ["001", "a,b"]}
        )

    def test_invalid_patient_inputs_never_send_a_request(self):
        for ids in ([], "001", [None], [1], [" "]):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                client.delete_patients(7, ids, "secret", "http://example")
        for kwargs in (
            {"days": -1},
            {"days": 1.5},
            {"days": True},
            {"limit": 0},
            {"limit": "2"},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                client.list_patients_by_last_document_load(
                    7, "secret", "http://example", **kwargs
                )
        self.request.assert_not_called()

    def test_http_and_transport_errors_are_not_success(self):
        for code in (200, 400, 401, 403, 404, 422, 500):
            with self.subTest(code=code):
                self.request.return_value = response(code, {"task_id": "wrong"})
                self.assertIsNone(
                    client.delete_patients(7, ["001"], "secret", "http://example")
                )
        for exc in (requests.Timeout("timed out"), requests.ConnectionError("offline")):
            self.request.side_effect = exc
            self.assertIsNone(
                client.list_patients_by_last_document_load(
                    7, "secret", "http://example"
                )
            )

    def test_malformed_success_responses_are_rejected(self):
        for data in (None, [], {}, {"patients": "not a list"}):
            self.request.return_value = response(data=data)
            self.assertIsNone(
                client.list_patients_by_last_document_load(
                    7, "secret", "http://example"
                )
            )
        self.request.return_value.json.side_effect = ValueError("invalid JSON")
        self.assertIsNone(
            client.list_patients_by_last_document_load(7, "secret", "http://example")
        )
        self.request.return_value = response(202, {})
        self.assertIsNone(
            client.delete_patients(7, ["001"], "secret", "http://example")
        )

    def test_listing_preserves_null_loads_order_and_limit_metadata(self):
        data = {
            "patients": [
                {"id": 9, "patient_id": "empty", "last_loaded_at": None},
                {
                    "id": 10,
                    "patient_id": "001",
                    "last_loaded_at": "2026-01-01T00:00:00Z",
                },
            ],
            "count": 2,
            "limit": 2,
            "days": 14,
            "cutoff": "2026-01-02T00:00:00Z",
        }
        self.request.return_value = response(data=data)
        self.assertEqual(
            client.list_patients_by_last_document_load(
                7, "secret", "http://example", limit=2
            ),
            data,
        )
        self.request.assert_called_once()  # no implicit pagination or deletion

    def test_get_rejects_http_errors_and_unexpected_success_codes(self):
        for code in (201, 202, 204, 301, 400, 403, 404, 422, 429, 500):
            with self.subTest(code=code):
                self.request.return_value = response(code, {"patients": []})
                self.assertIsNone(
                    client.list_patients_by_last_document_load(
                        7, "secret", "http://example"
                    )
                )

    def test_delete_connection_failure_is_not_retried(self):
        self.request.side_effect = requests.Timeout("response lost")
        self.assertIsNone(
            client.delete_patients(7, ["001"], "secret", "http://example")
        )
        self.request.assert_called_once()

    def test_delete_keeps_input_list_unchanged_and_forwards_tls(self):
        ids = [" 001 ", "001"]
        self.request.return_value = response(202, {"task_id": "task"})
        client.delete_patients(7, ids, "secret", "http://example/", verify_ssl=False)
        self.assertEqual(ids, [" 001 ", "001"])
        self.assertFalse(self.request.call_args.kwargs["verify"])
        self.assertEqual(
            self.request.call_args.kwargs["headers"], {"Authorization": "Bearer secret"}
        )
        self.assertEqual(self.request.call_args.kwargs["timeout"], 60)


class PatientCLITests(unittest.TestCase):
    def run_cli(self, *args):
        with patch.dict(os.environ, {"BRIM_API_TOKEN": "secret"}, clear=True), patch(
            "sys.argv", ["brim_utils", *args]
        ), contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(
            io.StringIO()
        ):
            client.main()
            return out.getvalue()

    def test_token_precedence(self):
        with patch.dict(
            os.environ, {"BRIM_API_TOKEN": "new", "API_TOKEN": "old"}, clear=True
        ):
            self.assertEqual(client.create_parser().parse_args([]).api_token, "new")
            self.assertEqual(
                client.create_parser()
                .parse_args(["--api-token", "explicit"])
                .api_token,
                "explicit",
            )
        with patch.dict(os.environ, {"API_TOKEN": "old"}, clear=True):
            self.assertEqual(client.create_parser().parse_args([]).api_token, "old")
        with patch.dict(
            os.environ, {"BRIM_API_TOKEN": "", "API_TOKEN": "old"}, clear=True
        ):
            self.assertEqual(client.create_parser().parse_args([]).api_token, "old")

    @patch.object(client, "delete_patients")
    @patch.object(client, "list_patients_by_last_document_load")
    def test_list_zero_days_writes_json(self, listing, delete):
        listing.return_value = {"patients": [], "count": 0}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "patients.json"
            printed = self.run_cli(
                "--project-id",
                "7",
                "--list-patients-by-last-document-load",
                "0",
                "--output-file",
                str(output),
            )
            self.assertEqual(json.loads(printed), json.loads(output.read_text()))
        self.assertEqual(listing.call_args.kwargs["days"], 0)
        delete.assert_not_called()

    @patch.object(client, "list_patients_by_last_document_load")
    @patch.object(client, "poll_task_status")
    @patch.object(client, "delete_patients", return_value={"task_id": "celery-id"})
    def test_delete_acceptance_does_not_poll_summit_task(self, delete, poll, listing):
        result = self.run_cli("--project-id", "7", "--delete-patients", "001", "002")
        self.assertEqual(json.loads(result), {"task_id": "celery-id"})
        self.assertEqual(delete.call_args.args[1], ["001", "002"])
        poll.assert_not_called()
        listing.assert_not_called()

    @patch.object(client, "delete_patients", return_value=None)
    def test_request_failure_is_nonzero(self, delete):
        with self.assertRaises(SystemExit) as error:
            self.run_cli("--project-id", "7", "--delete-patients", "001")
        self.assertEqual(error.exception.code, 1)

    @patch.object(client.requests, "request")
    def test_conflicting_or_invalid_commands_never_reach_network(self, request):
        combinations = [
            ["--delete-patients", "001", "--list-patients-by-last-document-load", "1"],
            ["--delete-patients", "001", "--notes-file", "notes.csv"],
            ["--delete-patients", "001", "--reference-date", "2026-01-01"],
            ["--list-patients-by-last-document-load", "-1"],
            ["--list-patients-by-last-document-load", "0", "--patient-limit", "0"],
            ["--delete-patients", " "],
            ["--patient-limit", "5"],
        ]
        for args in combinations:
            with self.subTest(args=args), self.assertRaises(SystemExit):
                self.run_cli("--project-id", "7", *args)
        request.assert_not_called()

    @patch.object(
        client, "list_patients_by_last_document_load", return_value={"patients": []}
    )
    def test_list_forwards_all_options(self, listing):
        self.run_cli(
            "--project-id",
            "7",
            "--url",
            "https://example/",
            "--api-token",
            "explicit",
            "--list-patients-by-last-document-load",
            "14",
            "--patient-limit",
            "25",
            "--reference-date",
            "2026-09-20",
            "--no-verify-ssl",
        )
        listing.assert_called_once_with(
            7,
            "explicit",
            "https://example/",
            days=14,
            limit=25,
            reference_date="2026-09-20",
            verify_ssl=False,
        )

    @patch.object(client, "list_patients_by_last_document_load", return_value=None)
    def test_list_failure_exits_nonzero_without_output_file(self, listing):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "missing.json"
            with self.assertRaises(SystemExit) as error:
                self.run_cli(
                    "--project-id",
                    "7",
                    "--list-patients-by-last-document-load",
                    "1",
                    "--output-file",
                    str(output),
                )
            self.assertEqual(error.exception.code, 1)
            self.assertFalse(output.exists())

    @patch.object(
        client, "list_patients_by_last_document_load", return_value={"patients": []}
    )
    def test_output_write_failure_exits_nonzero(self, listing):
        with patch.object(
            Path, "write_text", side_effect=OSError("permission denied")
        ), self.assertRaises(SystemExit) as error:
            self.run_cli(
                "--project-id",
                "7",
                "--list-patients-by-last-document-load",
                "1",
                "--output-file",
                "output.json",
            )
        self.assertEqual(error.exception.code, 1)

    @patch.object(client, "delete_patients")
    @patch.object(client, "wait_for_ready", return_value=False)
    def test_readiness_failure_prevents_deletion(self, ready, delete):
        with self.assertRaises(SystemExit) as error:
            self.run_cli(
                "--project-id", "7", "--delete-patients", "001", "--wait-for-ready"
            )
        self.assertEqual(error.exception.code, 1)
        delete.assert_not_called()

    @patch.object(client, "create_project")
    @patch.object(client, "delete_patients")
    def test_delete_cannot_create_a_project(self, delete, create):
        with self.assertRaises(SystemExit):
            self.run_cli("--create-project", "accidental", "--delete-patients", "001")
        delete.assert_not_called()
        create.assert_not_called()

    def test_token_is_required_before_any_action(self):
        with patch.dict(os.environ, {}, clear=True), patch(
            "sys.argv", ["brim_utils", "--project-id", "7", "--delete-patients", "001"]
        ), patch.object(
            client, "delete_patients"
        ) as delete, contextlib.redirect_stdout(
            io.StringIO()
        ), self.assertRaises(
            SystemExit
        ) as error:
            client.main()
        self.assertEqual(error.exception.code, 1)
        delete.assert_not_called()

    @patch.object(
        client, "list_patients_by_last_document_load", return_value={"patients": []}
    )
    def test_readiness_and_tls_messages_do_not_corrupt_json(self, listing):
        def ready(*args, **kwargs):
            print("Waiting for server...")
            return True

        with patch.object(client, "wait_for_ready", side_effect=ready):
            output = self.run_cli(
                "--project-id",
                "7",
                "--list-patients-by-last-document-load",
                "0",
                "--wait-for-ready",
                "--no-verify-ssl",
            )
        self.assertEqual(json.loads(output), {"patients": []})

    @patch.object(client, "delete_patients", return_value={"task_id": "accepted"})
    def test_delete_json_can_be_saved(self, delete):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "delete.json"
            self.run_cli(
                "--project-id",
                "7",
                "--delete-patients",
                "001",
                "--output-file",
                str(output),
            )
            self.assertEqual(json.loads(output.read_text()), {"task_id": "accepted"})


class ExistingClientContractTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.file = Path(self.directory.name) / "fixture.csv"
        self.file.write_text("header\nvalue\n")
        self.output = Path(self.directory.name) / "output.csv"
        self.post = patch.object(client.requests, "post").start()
        self.sleep = patch.object(client.time, "sleep").start()
        self.addCleanup(patch.stopall)

    def test_create_and_existing_project(self):
        for created in (True, False):
            self.post.return_value = response(201, {"id": 7, "created": created})
            self.assertEqual(
                client.create_project("fixture", "secret", "http://example"),
                (7, created),
            )
            self.assertEqual(self.post.call_args.kwargs["json"], {"name": "fixture"})
        self.post.return_value = response(403)
        self.assertEqual(
            client.create_project("fixture", "secret", "http://example"), (None, False)
        )

    def test_all_upload_helpers_send_and_close_files_on_success_and_failure(self):
        cases = [
            (
                "csv/",
                lambda: client.upload_csv(
                    str(self.file), 7, "secret", "http://example", False
                ),
            ),
            (
                "structured-data/",
                lambda: client.upload_structured_data(
                    str(self.file), 7, "secret", "http://example"
                ),
            ),
            (
                "variables/",
                lambda: client.upload_variables_decisions(
                    str(self.file), str(self.file), 7, "secret", "http://example"
                ),
            ),
        ]
        payload = {
            "original_filename": "fixture.csv",
            "upload_task_id": "task",
            "has_variables": True,
            "has_decisions": True,
        }
        for suffix, call in cases:
            for code in (200, 400, 500):
                with self.subTest(suffix=suffix, code=code):
                    self.post.return_value = response(code, payload)
                    self.assertEqual(call(), payload if code == 200 else None)
                    self.assertTrue(
                        self.post.call_args.args[0].endswith("/upload/" + suffix)
                    )
                    self.assertTrue(
                        all(
                            f.closed
                            for f in self.post.call_args.kwargs["files"].values()
                        )
                    )
            self.post.side_effect = requests.ConnectionError("offline")
            self.assertIsNone(call())
            self.assertTrue(
                all(f.closed for f in self.post.call_args.kwargs["files"].values())
            )
            self.post.side_effect = None

    def test_polling_terminal_states_and_retry_limit(self):
        for terminal in (2, 3, 4):
            self.post.side_effect = [
                response(data={"task_status": 1, "task_status_display": "Running"}),
                response(data={"task_status": terminal, "task_status_display": "Done"}),
            ]
            self.assertEqual(
                client.poll_task_status(
                    "task", 7, "secret", "http://example", max_retries=2
                ),
                terminal,
            )
        self.post.side_effect = None
        self.post.return_value = response(
            data={"task_status": 1, "task_status_display": "Running"}
        )
        self.assertIsNone(
            client.poll_task_status(
                "task", 7, "secret", "http://example", max_retries=2
            )
        )

    def test_results_poll_export_handle_and_write_exact_csv(self):
        self.post.side_effect = [
            response(data={"export_task_id": "export", "status": 1}),
            response(text="PATIENT_ID,value\n001,yes\n", content_type="text/csv"),
        ]
        self.assertTrue(
            client.fetch_results(
                "generation",
                7,
                "secret",
                "http://example",
                self.output,
                export_type="detailed",
            )
        )
        self.assertEqual(self.output.read_text(), "PATIENT_ID,value\n001,yes\n")
        first, second = self.post.call_args_list
        self.assertTrue(first.kwargs["json"]["detailed_export"])
        self.assertEqual(second.kwargs["json"]["task_id"], "export")

    def test_export_failure_does_not_write_file(self):
        self.post.return_value = response(
            data={"status": 3, "is_complete": True, "message": "failed"}
        )
        self.assertFalse(
            client.fetch_results(None, 7, "secret", "http://example", self.output)
        )
        self.assertFalse(self.output.exists())

    def test_invitation_is_mocked_and_preserves_permission(self):
        self.post.return_value = response()
        self.assertTrue(
            client.invite_user(
                "fixture@example.invalid",
                7,
                "secret",
                "http://example",
                can_upload_permission=True,
            )
        )
        self.assertTrue(self.post.call_args.kwargs["json"]["can_upload_permission"])
        self.post.return_value = response(400)
        self.assertFalse(client.invite_user("invalid", 7, "secret", "http://example"))
