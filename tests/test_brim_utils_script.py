"""Unit tests for scripts/brim_utils.py (the client CLI script)."""

import tempfile
from unittest import TestCase
from unittest.mock import MagicMock, patch

import requests
import brim_utils
from brim_utils import create_parser, main, upload_validation, wait_for_ready


def _response(status_code):
    response = MagicMock()
    response.status_code = status_code
    return response


class TestWaitForReady(TestCase):
    @patch("brim_utils.requests.get")
    def test_ready_immediately(self, mock_get):
        mock_get.return_value = _response(200)

        self.assertTrue(wait_for_ready("https://brim.example.com"))

        mock_get.assert_called_once()
        self.assertEqual(mock_get.call_args[0][0], "https://brim.example.com/-/health/")

    @patch("brim_utils.time.sleep")
    @patch("brim_utils.requests.get")
    def test_retries_5xx_until_ready(self, mock_get, mock_sleep):
        # nginx up but app still booting: 502s, then healthy.
        mock_get.side_effect = [_response(502), _response(502), _response(200)]

        self.assertTrue(wait_for_ready("https://brim.example.com", timeout=600))

        self.assertEqual(mock_get.call_count, 3)

    @patch("brim_utils.time.sleep")
    @patch("brim_utils.requests.get")
    def test_retries_connection_errors_until_ready(self, mock_get, mock_sleep):
        # Instance not up yet: connection refused, then healthy.
        mock_get.side_effect = [
            requests.exceptions.ConnectionError("refused"),
            requests.exceptions.ConnectTimeout("timeout"),
            _response(200),
        ]

        self.assertTrue(wait_for_ready("https://brim.example.com", timeout=600))

        self.assertEqual(mock_get.call_count, 3)

    @patch("brim_utils.requests.get")
    def test_times_out(self, mock_get):
        mock_get.return_value = _response(502)

        self.assertFalse(wait_for_ready("https://brim.example.com", timeout=0))

    @patch("brim_utils.time.sleep")
    @patch("brim_utils.time.monotonic")
    @patch("brim_utils.requests.get")
    def test_times_out_after_deadline(self, mock_get, mock_monotonic, mock_sleep):
        mock_get.side_effect = requests.exceptions.ConnectionError("refused")
        # Each loop iteration advances the clock past the next backoff check.
        mock_monotonic.side_effect = [0, 100, 200, 400, 700]

        self.assertFalse(wait_for_ready("https://brim.example.com", timeout=600))


class TestWaitForReadyArgs(TestCase):
    def test_defaults(self):
        args = create_parser().parse_args(["--project-id", "1"])
        self.assertFalse(args.wait_for_ready)
        self.assertEqual(args.ready_timeout, 600)

    def test_flags(self):
        args = create_parser().parse_args(
            ["--project-id", "1", "--wait-for-ready", "--ready-timeout", "900"]
        )
        self.assertTrue(args.wait_for_ready)
        self.assertEqual(args.ready_timeout, 900)


class TestValidationUpload(TestCase):
    def test_upload_sends_target_and_closes_file(self):
        with tempfile.NamedTemporaryFile() as source, patch(
            "brim_utils.requests.post"
        ) as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = {
                "message": "Queued",
                "data": {"upload_task_id": "42"},
            }
            result = upload_validation(
                source.name,
                1,
                "token",
                "https://brim.example.com",
                target="training",
                only_reviewed=True,
            )
            self.assertEqual(result["upload_task_id"], "42")
            self.assertEqual(
                post.call_args.args[0],
                "https://brim.example.com/api/v1/upload/validation/",
            )
            self.assertEqual(
                post.call_args.kwargs["data"],
                {"project_id": "1", "target": "training", "only_reviewed": True},
            )
            self.assertTrue(post.call_args.kwargs["files"]["csv_file"].closed)

    def test_cli_waits_for_notes_before_validation(self):
        events = []
        with patch(
            "sys.argv",
            [
                "brim_utils.py",
                "--api-token",
                "token",
                "--project-id",
                "1",
                "--notes-file",
                "notes.csv",
                "--validation-file",
                "labels.csv",
                "--validation-target",
                "training",
            ],
        ), patch.object(
            brim_utils, "upload_csv", return_value={"upload_task_id": "notes"}
        ), patch.object(
            brim_utils,
            "poll_task_status",
            side_effect=lambda task, *a, **k: events.append(task)
            or brim_utils.TaskStatus.COMPLETE,
        ), patch.object(
            brim_utils,
            "upload_validation",
            side_effect=lambda *a, **k: events.append(k["target"])
            or {"upload_task_id": "labels"},
        ), self.assertRaises(
            SystemExit
        ) as exited:
            brim_utils.main()
        self.assertEqual(exited.exception.code, 0)
        self.assertEqual(events, ["notes", "training", "labels"])

    def test_target_requires_file(self):
        with patch(
            "sys.argv",
            [
                "brim_utils.py",
                "--api-token",
                "token",
                "--project-id",
                "1",
                "--validation-target",
                "training",
            ],
        ), self.assertRaises(SystemExit) as exited:
            main()
        self.assertEqual(exited.exception.code, 2)

    def test_validation_file_rejects_generate_after_upload(self):
        with patch(
            "sys.argv",
            [
                "brim_utils.py",
                "--api-token",
                "token",
                "--project-id",
                "1",
                "--notes-file",
                "notes.csv",
                "--generate-after-upload",
                "--validation-file",
                "validation.csv",
            ],
        ), patch.object(brim_utils, "upload_csv") as upload_csv, self.assertRaises(
            SystemExit
        ) as exited:
            main()
        self.assertEqual(exited.exception.code, 2)
        upload_csv.assert_not_called()

    def test_validation_only_duplicate_does_not_poll(self):
        with patch(
            "sys.argv",
            [
                "brim_utils.py",
                "--api-token",
                "token",
                "--project-id",
                "1",
                "--validation-file",
                "labels.csv",
            ],
        ), patch.object(
            brim_utils,
            "upload_validation",
            return_value={"dataset_id": 1, "upload_task_id": None},
        ) as upload, patch.object(
            brim_utils, "poll_task_status"
        ) as poll, self.assertRaises(
            SystemExit
        ) as exited:
            brim_utils.main()
        self.assertEqual(exited.exception.code, 0)
        self.assertEqual(upload.call_args.kwargs["target"], "holdout")
        poll.assert_not_called()

    def test_failed_validation_processing_exits_with_error(self):
        with patch(
            "sys.argv",
            [
                "brim_utils.py",
                "--api-token",
                "token",
                "--project-id",
                "1",
                "--validation-file",
                "labels.csv",
            ],
        ), patch.object(
            brim_utils, "upload_validation", return_value={"upload_task_id": "labels"}
        ), patch.object(
            brim_utils, "poll_task_status", return_value=brim_utils.TaskStatus.ERROR
        ), self.assertRaises(
            SystemExit
        ) as exited:
            brim_utils.main()
        self.assertEqual(exited.exception.code, 1)
