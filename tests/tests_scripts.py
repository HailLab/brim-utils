import os
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest import mock

import pandas as pd

from convert_omop_to_brim import (
    build_enrichment_header,
    build_person_lookup,
    build_provider_lookup,
    build_visit_lookup,
    convert_omop_to_brim,
    format_datetime,
    load_csv_if_exists,
)

from brim_utils import (
    TaskStatus,
    create_parser,
    create_project,
    fetch_results,
    invite_user,
    main,
    poll_task_status,
    upload_csv,
    upload_structured_data,
)

# Path to sample files
SAMPLE_FILES_DIR = Path(__file__).parent / "sample_files"


class TestArgumentParsing(unittest.TestCase):
    """Test command-line argument parsing."""

    def test_default_is_notes_upload(self):
        """Default behavior should be notes upload when neither flag is set."""
        with mock.patch(
            "sys.argv",
            ["brim_utils.py", "--csv-file", "test.csv", "--project-id", "123"],
        ):
            parser = create_parser()
            args = parser.parse_args()
            self.assertFalse(args.notes)
            self.assertFalse(args.structured_data)

    def test_notes_flag(self):
        """--notes flag should be recognized."""
        with mock.patch(
            "sys.argv",
            [
                "brim_utils.py",
                "--csv-file",
                "test.csv",
                "--notes",
                "--project-id",
                "123",
            ],
        ):
            parser = create_parser()
            args = parser.parse_args()
            self.assertTrue(args.notes)
            self.assertFalse(args.structured_data)

    def test_structured_data_flag(self):
        """--structured-data flag should be recognized."""
        with mock.patch(
            "sys.argv",
            [
                "brim_utils.py",
                "--csv-file",
                "test.csv",
                "--structured-data",
                "--project-id",
                "123",
            ],
        ):
            parser = create_parser()
            args = parser.parse_args()
            self.assertFalse(args.notes)
            self.assertTrue(args.structured_data)

    def test_notes_and_structured_data_mutually_exclusive(self):
        """--notes and --structured-data should be mutually exclusive."""
        with mock.patch(
            "sys.argv",
            [
                "brim_utils.py",
                "--csv-file",
                "test.csv",
                "--notes",
                "--structured-data",
                "--project-id",
                "123",
            ],
        ):
            parser = create_parser()
            with self.assertRaises(SystemExit):
                parser.parse_args()

    def test_fetch_results_flag(self):
        """--fetch-results flag should be recognized."""
        with mock.patch(
            "sys.argv",
            [
                "brim_utils.py",
                "--csv-file",
                "test.csv",
                "--generate-after-upload",
                "--fetch-results",
                "--project-id",
                "123",
            ],
        ):
            parser = create_parser()
            args = parser.parse_args()
            self.assertTrue(args.fetch_results)
            self.assertTrue(args.generate_after_upload)


class TestValidationErrors(unittest.TestCase):
    """Test validation of argument combinations."""

    def test_fetch_results_without_generate_fails(self):
        """--fetch-results without --generate-after-upload should fail."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            f.write(b"test,data\n")
            filepath = f.name
        self.addCleanup(os.unlink, filepath)

        with mock.patch(
            "sys.argv",
            [
                "brim_utils.py",
                "--csv-file",
                filepath,
                "--project-id",
                "123",
                "--api-token",
                "test-token",
                "--fetch-results",
            ],
        ):
            captured_output = StringIO()
            with mock.patch("sys.stdout", captured_output):
                with self.assertRaises(SystemExit) as cm:
                    main()
                self.assertEqual(cm.exception.code, 1)
            self.assertIn(
                "--fetch-results requires --generate-after-upload",
                captured_output.getvalue(),
            )

    def test_structured_data_with_generate_fails(self):
        """--structured-data with --generate-after-upload should fail."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            f.write(b"test,data\n")
            filepath = f.name
        self.addCleanup(os.unlink, filepath)

        with mock.patch(
            "sys.argv",
            [
                "brim_utils.py",
                "--csv-file",
                filepath,
                "--project-id",
                "123",
                "--api-token",
                "test-token",
                "--structured-data",
                "--generate-after-upload",
            ],
        ):
            captured_output = StringIO()
            with mock.patch("sys.stdout", captured_output):
                with self.assertRaises(SystemExit) as cm:
                    main()
                self.assertEqual(cm.exception.code, 1)
            self.assertIn(
                "--structured-data cannot be used with --generate-after-upload",
                captured_output.getvalue(),
            )

    def test_fetch_results_without_output_file_fails(self):
        """--fetch-results without --output-file should fail."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            f.write(b"test,data\n")
            filepath = f.name
        self.addCleanup(os.unlink, filepath)

        with mock.patch(
            "sys.argv",
            [
                "brim_utils.py",
                "--csv-file",
                filepath,
                "--project-id",
                "123",
                "--api-token",
                "test-token",
                "--generate-after-upload",
                "--fetch-results",
            ],
        ):
            captured_output = StringIO()
            with mock.patch("sys.stdout", captured_output):
                with self.assertRaises(SystemExit) as cm:
                    main()
                self.assertEqual(cm.exception.code, 1)
            self.assertIn(
                "--fetch-results requires --output-file",
                captured_output.getvalue(),
            )


class TestUploadCSV(unittest.TestCase):
    """Test upload_csv function."""

    @mock.patch("brim_utils.requests.post")
    def test_upload_csv_success(self, mock_post):
        """Test successful notes CSV upload."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "upload_task_id": "task-123",
                "original_filename": "test.csv",
                "generation_task_id": None,
            },
        }
        mock_post.return_value = mock_response

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            f.write(b"note_id,person_id,note_text\n1,P1,Test note\n")
            filepath = f.name
        self.addCleanup(os.unlink, filepath)

        result = upload_csv(
            filepath,
            project_id=123,
            api_token="test-token",
            api_url="http://localhost:8000",
            generate_after_upload=False,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["upload_task_id"], "task-123")

        # Verify correct endpoint was called
        call_args = mock_post.call_args
        self.assertIn("/api/v1/upload/csv/", call_args[0][0])
        self.assertEqual(call_args[1]["headers"]["Authorization"], "Bearer test-token")
        self.assertEqual(call_args[1]["data"]["project_id"], "123")

    @mock.patch("brim_utils.requests.post")
    def test_upload_csv_with_generation(self, mock_post):
        """Test notes CSV upload with generation."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "upload_task_id": "task-123",
                "original_filename": "test.csv",
                "generation_task_id": "task-123",
            },
        }
        mock_post.return_value = mock_response

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            f.write(b"note_id,person_id,note_text\n1,P1,Test note\n")
            filepath = f.name
        self.addCleanup(os.unlink, filepath)

        result = upload_csv(
            filepath,
            project_id=123,
            api_token="test-token",
            api_url="http://localhost:8000",
            generate_after_upload=True,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["generation_task_id"], "task-123")
        self.assertTrue(mock_post.call_args[1]["data"]["generate_after_upload"])

    @mock.patch("brim_utils.requests.post")
    def test_upload_csv_failure(self, mock_post):
        """Test failed notes CSV upload."""
        mock_response = mock.Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad request"
        mock_post.return_value = mock_response

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            f.write(b"bad,data\n")
            filepath = f.name
        self.addCleanup(os.unlink, filepath)

        result = upload_csv(
            filepath,
            project_id=123,
            api_token="test-token",
            api_url="http://localhost:8000",
            generate_after_upload=False,
        )

        self.assertIsNone(result)

    def test_upload_csv_file_not_found(self):
        """Test upload with non-existent file."""
        result = upload_csv(
            "/nonexistent/path/test.csv",
            project_id=123,
            api_token="test-token",
            api_url="http://localhost:8000",
            generate_after_upload=False,
        )
        self.assertIsNone(result)


class TestUploadStructuredData(unittest.TestCase):
    """Test upload_structured_data function."""

    @mock.patch("brim_utils.requests.post")
    def test_upload_structured_data_success(self, mock_post):
        """Test successful structured data upload."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "upload_task_id": "task-456",
                "original_filename": "structured.csv",
            },
        }
        mock_post.return_value = mock_response

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            f.write(
                b"NAME,SCOPE,TYPE,PATIENT_ID,NOTE_ID,NOTE_DATETIME,VALUE\n"
                b"var1,one_per_patient,text,P1,,,value1\n"
            )
            filepath = f.name
        self.addCleanup(os.unlink, filepath)

        result = upload_structured_data(
            filepath,
            project_id=123,
            api_token="test-token",
            api_url="http://localhost:8000",
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["upload_task_id"], "task-456")

        # Verify correct endpoint was called
        call_args = mock_post.call_args
        self.assertIn("/api/v1/upload/structured-data/", call_args[0][0])
        self.assertEqual(call_args[1]["headers"]["Authorization"], "Bearer test-token")

    @mock.patch("brim_utils.requests.post")
    def test_upload_structured_data_failure(self, mock_post):
        """Test failed structured data upload."""
        mock_response = mock.Mock()
        mock_response.status_code = 400
        mock_response.text = "Validation error"
        mock_post.return_value = mock_response

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            f.write(b"bad,data\n")
            filepath = f.name
        self.addCleanup(os.unlink, filepath)

        result = upload_structured_data(
            filepath,
            project_id=123,
            api_token="test-token",
            api_url="http://localhost:8000",
        )

        self.assertIsNone(result)

    def test_upload_structured_data_file_not_found(self):
        """Test structured data upload with non-existent file."""
        result = upload_structured_data(
            "/nonexistent/path/structured.csv",
            project_id=123,
            api_token="test-token",
            api_url="http://localhost:8000",
        )
        self.assertIsNone(result)


class TestCreateProject(unittest.TestCase):
    """Test create_project function."""

    @mock.patch("brim_utils.requests.post")
    def test_create_project_success(self, mock_post):
        """Test successful project creation."""
        mock_response = mock.Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "id": 456,
                "name": "My New Project",
                "created": True,
            },
        }
        mock_post.return_value = mock_response

        project_id, created = create_project(
            project_name="My New Project",
            api_token="test-token",
            api_url="http://localhost:8000",
        )

        self.assertEqual(project_id, 456)
        self.assertTrue(created)

        # Verify correct endpoint and payload
        call_args = mock_post.call_args
        self.assertIn("/api/v1/projects/", call_args[0][0])
        self.assertEqual(call_args[1]["json"]["name"], "My New Project")

    @mock.patch("brim_utils.requests.post")
    def test_create_project_already_exists(self, mock_post):
        """Test project creation when project already exists."""
        mock_response = mock.Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "id": 789,
                "name": "Existing Project",
                "created": False,
            },
        }
        mock_post.return_value = mock_response

        project_id, created = create_project(
            project_name="Existing Project",
            api_token="test-token",
            api_url="http://localhost:8000",
        )

        self.assertEqual(project_id, 789)
        self.assertFalse(created)

    @mock.patch("brim_utils.requests.post")
    def test_create_project_api_error(self, mock_post):
        """Test project creation with API error."""
        mock_response = mock.Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad request"
        mock_post.return_value = mock_response

        project_id, created = create_project(
            project_name="Test Project",
            api_token="test-token",
            api_url="http://localhost:8000",
        )

        self.assertIsNone(project_id)
        self.assertFalse(created)


class TestCreateProjectValidation(unittest.TestCase):
    """Test validation for --create-project argument combinations."""

    @mock.patch("brim_utils.create_project")
    def test_create_project_exists_without_continue_flag(self, mock_create):
        """--create-project with existing project should exit with code 2."""
        mock_create.return_value = (123, False)  # Exists, not created

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            f.write(b"test,data\n")
            filepath = f.name
        self.addCleanup(os.unlink, filepath)

        with mock.patch(
            "sys.argv",
            [
                "brim_utils.py",
                "--csv-file",
                filepath,
                "--create-project",
                "Existing Project",
                "--api-token",
                "test-token",
            ],
        ):
            captured_output = StringIO()
            with mock.patch("sys.stdout", captured_output):
                with self.assertRaises(SystemExit) as cm:
                    main()
                self.assertEqual(cm.exception.code, 2)
            self.assertIn(
                "Project already exists",
                captured_output.getvalue(),
            )

    @mock.patch("brim_utils.upload_csv")
    @mock.patch("brim_utils.create_project")
    def test_create_project_exists_with_continue_flag(self, mock_create, mock_upload):
        """--create-project with --continue-if-project-exists should proceed."""
        mock_create.return_value = (123, False)  # Exists, not created
        mock_upload.return_value = {"upload_task_id": "task-123"}

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            f.write(b"test,data\n")
            filepath = f.name
        self.addCleanup(os.unlink, filepath)

        with mock.patch(
            "sys.argv",
            [
                "brim_utils.py",
                "--csv-file",
                filepath,
                "--create-project",
                "Existing Project",
                "--continue-if-project-exists",
                "--api-token",
                "test-token",
            ],
        ):
            with self.assertRaises(SystemExit) as cm:
                main()
            # Should exit with 0 (success)
            self.assertEqual(cm.exception.code, 0)
            # upload_csv should have been called with project_id 123
            mock_upload.assert_called_once()
            self.assertEqual(mock_upload.call_args[0][1], 123)

    def test_continue_if_project_exists_without_create_project(self):
        """--continue-if-project-exists without --create-project should fail."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            f.write(b"test,data\n")
            filepath = f.name
        self.addCleanup(os.unlink, filepath)

        with mock.patch(
            "sys.argv",
            [
                "brim_utils.py",
                "--csv-file",
                filepath,
                "--project-id",
                "123",
                "--continue-if-project-exists",
                "--api-token",
                "test-token",
            ],
        ):
            captured_output = StringIO()
            with mock.patch("sys.stdout", captured_output):
                with self.assertRaises(SystemExit) as cm:
                    main()
                self.assertEqual(cm.exception.code, 1)
            self.assertIn(
                "--continue-if-project-exists requires --create-project",
                captured_output.getvalue(),
            )

    def test_both_project_id_and_create_project(self):
        """Cannot use both --project-id and --create-project."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            f.write(b"test,data\n")
            filepath = f.name
        self.addCleanup(os.unlink, filepath)

        with mock.patch(
            "sys.argv",
            [
                "brim_utils.py",
                "--csv-file",
                filepath,
                "--project-id",
                "123",
                "--create-project",
                "My Project",
                "--api-token",
                "test-token",
            ],
        ):
            captured_output = StringIO()
            with mock.patch("sys.stdout", captured_output):
                with self.assertRaises(SystemExit) as cm:
                    main()
                self.assertEqual(cm.exception.code, 1)
            self.assertIn(
                "Cannot use both --project-id and --create-project",
                captured_output.getvalue(),
            )

    def test_neither_project_id_nor_create_project(self):
        """Must provide either --project-id or --create-project."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            f.write(b"test,data\n")
            filepath = f.name
        self.addCleanup(os.unlink, filepath)

        with mock.patch(
            "sys.argv",
            [
                "brim_utils.py",
                "--csv-file",
                filepath,
                "--api-token",
                "test-token",
            ],
        ):
            captured_output = StringIO()
            with mock.patch("sys.stdout", captured_output):
                with self.assertRaises(SystemExit) as cm:
                    main()
                self.assertEqual(cm.exception.code, 1)
            self.assertIn(
                "Either --project-id or --create-project is required",
                captured_output.getvalue(),
            )

    @mock.patch("brim_utils.create_project")
    def test_create_project_without_filepath(self, mock_create):
        """Create project without uploading a file should succeed."""
        mock_create.return_value = (123, True)  # Created new project

        with mock.patch(
            "sys.argv",
            [
                "brim_utils.py",
                "--create-project",
                "New Project",
                "--api-token",
                "test-token",
            ],
        ):
            with self.assertRaises(SystemExit) as cm:
                main()
            # Should exit with 0 (success)
            self.assertEqual(cm.exception.code, 0)
            mock_create.assert_called_once()

    @mock.patch("brim_utils.invite_user")
    @mock.patch("brim_utils.create_project")
    def test_create_project_and_invite_users_without_filepath(
        self, mock_create, mock_invite
    ):
        """Create project and invite users without uploading should succeed."""
        mock_create.return_value = (123, True)
        mock_invite.return_value = True

        with mock.patch(
            "sys.argv",
            [
                "brim_utils.py",
                "--create-project",
                "New Project",
                "--users-to-add",
                "user1@example.com,user2@example.com",
                "--api-token",
                "test-token",
            ],
        ):
            with self.assertRaises(SystemExit) as cm:
                main()
            self.assertEqual(cm.exception.code, 0)
            mock_create.assert_called_once()
            self.assertEqual(mock_invite.call_count, 2)

    def test_generate_after_upload_requires_csv_file(self):
        """--generate-after-upload without --csv-file should fail."""
        with mock.patch(
            "sys.argv",
            [
                "brim_utils.py",
                "--project-id",
                "123",
                "--generate-after-upload",
                "--api-token",
                "test-token",
            ],
        ):
            captured_output = StringIO()
            with mock.patch("sys.stdout", captured_output):
                with self.assertRaises(SystemExit) as cm:
                    main()
                self.assertEqual(cm.exception.code, 1)
            self.assertIn(
                "--generate-after-upload requires --csv-file",
                captured_output.getvalue(),
            )


class TestInviteUser(unittest.TestCase):
    """Test invite_user function."""

    @mock.patch("brim_utils.requests.post")
    def test_invite_user_success(self, mock_post):
        """Test successful user invitation."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "message": "Invitation for test@example.com sent successfully",
        }
        mock_post.return_value = mock_response

        result = invite_user(
            email="test@example.com",
            project_id=123,
            api_token="test-token",
            api_url="http://localhost:8000",
        )

        self.assertTrue(result)

        # Verify correct endpoint and payload
        call_args = mock_post.call_args
        self.assertIn("/api/v1/users/invite/", call_args[0][0])
        self.assertEqual(call_args[1]["headers"]["Authorization"], "Bearer test-token")
        self.assertEqual(call_args[1]["json"]["email"], "test@example.com")
        self.assertEqual(call_args[1]["json"]["project_id"], 123)

    @mock.patch("brim_utils.requests.post")
    def test_invite_user_with_upload_permission(self, mock_post):
        """Test user invitation with upload permission."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "message": "Invitation sent",
        }
        mock_post.return_value = mock_response

        result = invite_user(
            email="test@example.com",
            project_id=123,
            api_token="test-token",
            api_url="http://localhost:8000",
            can_upload_permission=True,
        )

        self.assertTrue(result)
        self.assertTrue(mock_post.call_args[1]["json"]["can_upload_permission"])

    @mock.patch("brim_utils.requests.post")
    def test_invite_user_already_in_project(self, mock_post):
        """Test invitation fails when user already in project."""
        mock_response = mock.Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "detail": "User test@example.com is already a member of this project.",
        }
        mock_post.return_value = mock_response

        result = invite_user(
            email="test@example.com",
            project_id=123,
            api_token="test-token",
            api_url="http://localhost:8000",
        )

        self.assertFalse(result)

    @mock.patch("brim_utils.requests.post")
    def test_invite_user_server_error(self, mock_post):
        """Test invitation handles server errors."""
        mock_response = mock.Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {
            "detail": "Failed to send invitation email",
        }
        mock_post.return_value = mock_response

        result = invite_user(
            email="test@example.com",
            project_id=123,
            api_token="test-token",
            api_url="http://localhost:8000",
        )

        self.assertFalse(result)

    @mock.patch("brim_utils.requests.post")
    def test_invite_user_connection_error(self, mock_post):
        """Test invitation handles connection errors."""
        import requests as req

        mock_post.side_effect = req.exceptions.ConnectionError("Connection refused")

        result = invite_user(
            email="test@example.com",
            project_id=123,
            api_token="test-token",
            api_url="http://localhost:8000",
        )

        self.assertFalse(result)


class TestPollTaskStatus(unittest.TestCase):
    """Test poll_task_status function."""

    @mock.patch("brim_utils.time.sleep")
    @mock.patch("brim_utils.requests.post")
    def test_poll_returns_on_complete(self, mock_post, mock_sleep):
        """Test polling returns when task completes."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "task_id": "task-123",
                "task_status": TaskStatus.COMPLETE,
                "task_status_display": "Complete",
            },
        }
        mock_post.return_value = mock_response

        status = poll_task_status(
            task_id="task-123",
            project_id=123,
            api_token="test-token",
            api_url="http://localhost:8000",
        )

        self.assertEqual(status, TaskStatus.COMPLETE)
        # Should not sleep since first response is complete
        mock_sleep.assert_not_called()

    @mock.patch("brim_utils.time.sleep")
    @mock.patch("brim_utils.requests.post")
    def test_poll_returns_on_error(self, mock_post, mock_sleep):
        """Test polling returns when task has error."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "task_id": "task-123",
                "task_status": TaskStatus.ERROR,
                "task_status_display": "Error",
            },
        }
        mock_post.return_value = mock_response

        status = poll_task_status(
            task_id="task-123",
            project_id=123,
            api_token="test-token",
            api_url="http://localhost:8000",
        )

        self.assertEqual(status, TaskStatus.ERROR)

    @mock.patch("brim_utils.time.sleep")
    @mock.patch("brim_utils.requests.post")
    def test_poll_returns_on_stopped(self, mock_post, mock_sleep):
        """Test polling returns when task is stopped."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "task_id": "task-123",
                "task_status": TaskStatus.STOPPED,
                "task_status_display": "Stopped",
            },
        }
        mock_post.return_value = mock_response

        status = poll_task_status(
            task_id="task-123",
            project_id=123,
            api_token="test-token",
            api_url="http://localhost:8000",
        )

        self.assertEqual(status, TaskStatus.STOPPED)

    @mock.patch("brim_utils.time.sleep")
    @mock.patch("brim_utils.requests.post")
    def test_poll_continues_while_running(self, mock_post, mock_sleep):
        """Test polling continues while task is running."""
        # First two calls return running, third returns complete
        running_response = mock.Mock()
        running_response.status_code = 200
        running_response.json.return_value = {
            "status": "success",
            "data": {
                "task_id": "task-123",
                "task_status": TaskStatus.RUNNING,
                "task_status_display": "Running",
            },
        }

        complete_response = mock.Mock()
        complete_response.status_code = 200
        complete_response.json.return_value = {
            "status": "success",
            "data": {
                "task_id": "task-123",
                "task_status": TaskStatus.COMPLETE,
                "task_status_display": "Complete",
            },
        }

        mock_post.side_effect = [running_response, running_response, complete_response]

        status = poll_task_status(
            task_id="task-123",
            project_id=123,
            api_token="test-token",
            api_url="http://localhost:8000",
            initial_interval=1,
        )

        self.assertEqual(status, TaskStatus.COMPLETE)
        self.assertEqual(mock_post.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

    @mock.patch("brim_utils.time.sleep")
    @mock.patch("brim_utils.requests.post")
    def test_poll_handles_max_retries(self, mock_post, mock_sleep):
        """Test polling stops after max retries."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "task_id": "task-123",
                "task_status": TaskStatus.RUNNING,
                "task_status_display": "Running",
            },
        }
        mock_post.return_value = mock_response

        status = poll_task_status(
            task_id="task-123",
            project_id=123,
            api_token="test-token",
            api_url="http://localhost:8000",
            max_retries=3,
        )

        self.assertIsNone(status)
        self.assertEqual(mock_post.call_count, 3)

    @mock.patch("brim_utils.requests.post")
    def test_poll_handles_api_error(self, mock_post):
        """Test polling handles API errors."""
        mock_response = mock.Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal server error"
        mock_post.return_value = mock_response

        status = poll_task_status(
            task_id="task-123",
            project_id=123,
            api_token="test-token",
            api_url="http://localhost:8000",
        )

        self.assertIsNone(status)


class TestFetchResults(unittest.TestCase):
    """Test fetch_results function."""

    @mock.patch("brim_utils.requests.post")
    def test_fetch_results_returns_csv_directly(self, mock_post):
        """Test fetching results when CSV is returned directly."""
        mock_response = mock.Mock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "text/csv"}
        mock_response.text = "Name,Value\nvar1,result1\n"
        mock_post.return_value = mock_response

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            output_path = f.name
        self.addCleanup(os.unlink, output_path)

        success = fetch_results(
            task_id="task-123",
            project_id=123,
            api_token="test-token",
            api_url="http://localhost:8000",
            output_file=output_path,
        )

        self.assertTrue(success)

        # Verify file was written
        with open(output_path) as f:
            saved_content = f.read()
        self.assertEqual(saved_content, "Name,Value\nvar1,result1\n")

        # Verify correct endpoint and payload
        call_args = mock_post.call_args
        self.assertIn("/api/v1/results/", call_args[0][0])
        self.assertEqual(call_args[1]["json"]["task_id"], "task-123")
        self.assertEqual(call_args[1]["json"]["project_id"], 123)
        self.assertTrue(call_args[1]["json"]["get_csv"])

    @mock.patch("brim_utils.time.sleep")
    @mock.patch("brim_utils.requests.post")
    def test_fetch_results_polls_export_task(self, mock_post, mock_sleep):
        """Test fetching results when export task needs to be polled."""
        # First call returns export_task_id, second call returns CSV
        export_response = mock.Mock()
        export_response.status_code = 200
        export_response.headers = {"Content-Type": "application/json"}
        export_response.json.return_value = {
            "status": "success",
            "data": {
                "export_task_id": "export-456",
                "is_complete": False,
            },
        }

        csv_response = mock.Mock()
        csv_response.status_code = 200
        csv_response.headers = {"Content-Type": "text/csv"}
        csv_response.text = "Name,Value\nvar1,result1\n"

        mock_post.side_effect = [export_response, csv_response]

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            output_path = f.name
        self.addCleanup(os.unlink, output_path)

        success = fetch_results(
            task_id="task-123",
            project_id=123,
            api_token="test-token",
            api_url="http://localhost:8000",
            output_file=output_path,
        )

        self.assertTrue(success)
        self.assertEqual(mock_post.call_count, 2)

        # Verify file was written
        with open(output_path) as f:
            saved_content = f.read()
        self.assertEqual(saved_content, "Name,Value\nvar1,result1\n")

    @mock.patch("brim_utils.requests.post")
    def test_fetch_results_handles_error(self, mock_post):
        """Test fetching results handles API errors."""
        mock_response = mock.Mock()
        mock_response.status_code = 404
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.text = "Task not found"
        mock_post.return_value = mock_response

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            output_path = f.name
        self.addCleanup(os.unlink, output_path)

        success = fetch_results(
            task_id="task-123",
            project_id=123,
            api_token="test-token",
            api_url="http://localhost:8000",
            output_file=output_path,
        )

        self.assertFalse(success)


class TestTaskStatusConstants(unittest.TestCase):
    """Test TaskStatus constants match expected values."""

    def test_status_constants(self):
        """Verify status constants match SummitTask.Status values."""
        self.assertEqual(TaskStatus.WAITING, 0)
        self.assertEqual(TaskStatus.RUNNING, 1)
        self.assertEqual(TaskStatus.COMPLETE, 2)
        self.assertEqual(TaskStatus.ERROR, 3)
        self.assertEqual(TaskStatus.STOPPED, 4)


class TestLoadCsvIfExists(unittest.TestCase):
    """Tests for load_csv_if_exists function."""

    def test_load_existing_file(self):
        """Test loading an existing CSV file."""
        df = load_csv_if_exists(SAMPLE_FILES_DIR, "note.csv")
        self.assertIsNotNone(df)
        self.assertIsInstance(df, pd.DataFrame)
        self.assertEqual(len(df), 8)

    def test_load_nonexistent_file(self):
        """Test loading a file that doesn't exist returns None."""
        df = load_csv_if_exists(SAMPLE_FILES_DIR, "nonexistent.csv")
        self.assertIsNone(df)


class TestFormatDatetime(unittest.TestCase):
    """Tests for format_datetime function."""

    def test_datetime_with_space(self):
        """Test datetime format with space separator."""
        result = format_datetime("2023-01-15 10:30:00", None)
        self.assertEqual(result, "2023-01-15 10:30:00")

    def test_datetime_with_T_separator(self):
        """Test datetime format with T separator (ISO format)."""
        result = format_datetime("2023-01-15T10:30:00", None)
        self.assertEqual(result, "2023-01-15 10:30:00")

    def test_datetime_missing_seconds(self):
        """Test datetime with missing seconds gets them added."""
        result = format_datetime("2023-08-22 13:20", None)
        self.assertEqual(result, "2023-08-22 13:20:00")

    def test_date_only_in_datetime_field(self):
        """Test when datetime field contains only a date."""
        result = format_datetime("2023-01-15", None)
        self.assertEqual(result, "2023-01-15 00:00:00")

    def test_fallback_to_date(self):
        """Test fallback to note_date when note_datetime is null."""
        result = format_datetime(None, "2023-03-10")
        self.assertEqual(result, "2023-03-10 00:00:00")

    def test_fallback_to_date_with_nan(self):
        """Test fallback to note_date when note_datetime is NaN."""
        result = format_datetime(float("nan"), "2023-03-10")
        self.assertEqual(result, "2023-03-10 00:00:00")

    def test_both_null(self):
        """Test when both datetime and date are null."""
        result = format_datetime(None, None)
        self.assertEqual(result, "")


class TestBuildLookups(unittest.TestCase):
    """Tests for building lookup dictionaries."""

    def test_build_provider_lookup(self):
        """Test building provider lookup from CSV."""
        provider_df = load_csv_if_exists(SAMPLE_FILES_DIR, "provider.csv")
        lookup = build_provider_lookup(provider_df)

        self.assertEqual(len(lookup), 6)
        self.assertIn(10, lookup)
        self.assertEqual(lookup[10]["provider_name"], "Dr. Sarah Smith")
        self.assertEqual(lookup[10]["specialty_source_value"], "Cardiology")

    def test_build_person_lookup(self):
        """Test building person lookup from CSV."""
        person_df = load_csv_if_exists(SAMPLE_FILES_DIR, "person.csv")
        lookup = build_person_lookup(person_df)

        self.assertEqual(len(lookup), 7)
        self.assertIn(100, lookup)
        self.assertEqual(lookup[100]["year_of_birth"], 1965)
        self.assertEqual(lookup[100]["gender_source_value"], "Male")
        self.assertEqual(lookup[100]["race_source_value"], "White")

    def test_build_visit_lookup(self):
        """Test building visit lookup from CSV."""
        visit_df = load_csv_if_exists(SAMPLE_FILES_DIR, "visit_occurrence.csv")
        lookup = build_visit_lookup(visit_df)

        self.assertEqual(len(lookup), 7)
        self.assertIn(1000, lookup)
        self.assertEqual(lookup[1000]["visit_start_date"], "2023-01-15")
        self.assertEqual(lookup[1000]["visit_end_date"], "2023-01-18")
        self.assertEqual(lookup[1000]["visit_source_value"], "Inpatient")

    def test_build_lookup_with_none(self):
        """Test building lookup with None dataframe."""
        self.assertEqual(build_provider_lookup(None), {})
        self.assertEqual(build_person_lookup(None), {})
        self.assertEqual(build_visit_lookup(None), {})


class TestBuildEnrichmentHeader(unittest.TestCase):
    """Tests for building enrichment header."""

    def setUp(self):
        """Set up lookups for testing."""
        provider_df = load_csv_if_exists(SAMPLE_FILES_DIR, "provider.csv")
        person_df = load_csv_if_exists(SAMPLE_FILES_DIR, "person.csv")
        visit_df = load_csv_if_exists(SAMPLE_FILES_DIR, "visit_occurrence.csv")

        self.provider_lookup = build_provider_lookup(provider_df)
        self.person_lookup = build_person_lookup(person_df)
        self.visit_lookup = build_visit_lookup(visit_df)

    def test_full_enrichment(self):
        """Test enrichment header with all data available."""
        note_row = pd.Series(
            {
                "note_id": 1,
                "person_id": 100,
                "provider_id": 10,
                "visit_occurrence_id": 1000,
            }
        )

        header = build_enrichment_header(
            note_row,
            self.provider_lookup,
            self.person_lookup,
            self.visit_lookup,
        )

        self.assertIn("Provider: Dr. Sarah Smith", header)
        self.assertIn("Provider Specialty: Cardiology", header)
        self.assertIn("Patient Year of Birth: 1965", header)
        self.assertIn("Patient Gender: Male", header)
        self.assertIn("Patient Race: White", header)
        self.assertIn("Visit Start Date: 2023-01-15", header)
        self.assertIn("Visit End Date: 2023-01-18", header)
        self.assertIn("Visit Type: Inpatient", header)

    def test_enrichment_missing_provider(self):
        """Test enrichment header when provider is missing."""
        note_row = pd.Series(
            {
                "note_id": 5,
                "person_id": 100,
                "provider_id": float("nan"),
                "visit_occurrence_id": 1003,
            }
        )

        header = build_enrichment_header(
            note_row,
            self.provider_lookup,
            self.person_lookup,
            self.visit_lookup,
        )

        self.assertNotIn("Provider:", header)
        self.assertIn("Patient Year of Birth: 1965", header)
        self.assertIn("Visit Type: Outpatient", header)

    def test_enrichment_missing_visit(self):
        """Test enrichment header when visit is missing."""
        note_row = pd.Series(
            {
                "note_id": 4,
                "person_id": 103,
                "provider_id": 10,
                "visit_occurrence_id": float("nan"),
            }
        )

        header = build_enrichment_header(
            note_row,
            self.provider_lookup,
            self.person_lookup,
            self.visit_lookup,
        )

        self.assertIn("Provider: Dr. Sarah Smith", header)
        self.assertIn("Patient Year of Birth: 1990", header)
        self.assertNotIn("Visit Start Date:", header)


class TestConvertOmopToBrim(unittest.TestCase):
    """Integration tests for the full conversion."""

    def test_conversion_with_enrichment(self):
        """Test full conversion with enrichment enabled."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as tmp_file:
            output_path = Path(tmp_file.name)

        try:
            convert_omop_to_brim(SAMPLE_FILES_DIR, output_path, enrich=True)

            # Read and verify output
            output_df = pd.read_csv(output_path)

            # Check headers
            expected_columns = [
                "NOTE_ID",
                "PERSON_ID",
                "NOTE_DATETIME",
                "NOTE_TEXT",
                "NOTE_TITLE",
            ]
            self.assertEqual(list(output_df.columns), expected_columns)

            # Check row count
            self.assertEqual(len(output_df), 8)

            # Check first note has enrichment
            first_note = output_df[output_df["NOTE_ID"] == 1].iloc[0]
            self.assertIn("Provider: Dr. Sarah Smith", first_note["NOTE_TEXT"])
            self.assertIn("Patient Year of Birth: 1965", first_note["NOTE_TEXT"])
            self.assertIn("Patient presents with chest pain", first_note["NOTE_TEXT"])
            self.assertEqual(first_note["NOTE_TITLE"], "Progress Note")
            self.assertEqual(first_note["NOTE_DATETIME"], "2023-01-15 10:30:00")

            # Check note with missing datetime uses date
            note_3 = output_df[output_df["NOTE_ID"] == 3].iloc[0]
            self.assertEqual(note_3["NOTE_DATETIME"], "2023-03-10 00:00:00")

            # Check note with missing title gets "Unknown title"
            self.assertEqual(note_3["NOTE_TITLE"], "Unknown title")

        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_conversion_without_enrichment(self):
        """Test full conversion with enrichment disabled."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as tmp_file:
            output_path = Path(tmp_file.name)

        try:
            convert_omop_to_brim(SAMPLE_FILES_DIR, output_path, enrich=False)

            # Read and verify output
            output_df = pd.read_csv(output_path)

            # Check first note does NOT have enrichment
            first_note = output_df[output_df["NOTE_ID"] == 1].iloc[0]
            self.assertNotIn("Provider:", first_note["NOTE_TEXT"])
            self.assertNotIn("Patient Year of Birth:", first_note["NOTE_TEXT"])
            # But still has the original text
            self.assertIn("Patient presents with chest pain", first_note["NOTE_TEXT"])

        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_csv_escaping(self):
        """Test that double quotes are properly escaped in output."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as tmp_file:
            output_path = Path(tmp_file.name)

        try:
            convert_omop_to_brim(SAMPLE_FILES_DIR, output_path, enrich=False)

            # Read raw file to check escaping
            with open(output_path, "r") as f:
                content = f.read()

            # Note 7 has quoted text - verify it's properly escaped
            # The original has: "quoted text"
            # In CSV it should be: ""quoted text""
            self.assertIn('""quoted text""', content)

        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_iso_datetime_format(self):
        """Test that ISO datetime format (with T) is normalized."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as tmp_file:
            output_path = Path(tmp_file.name)

        try:
            convert_omop_to_brim(SAMPLE_FILES_DIR, output_path, enrich=False)

            output_df = pd.read_csv(output_path)

            # Note 4 has ISO format: 2023-04-05T09:15:00
            note_4 = output_df[output_df["NOTE_ID"] == 4].iloc[0]
            self.assertEqual(note_4["NOTE_DATETIME"], "2023-04-05 09:15:00")

        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_missing_provider_in_note(self):
        """Test handling of note with missing provider_id."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as tmp_file:
            output_path = Path(tmp_file.name)

        try:
            convert_omop_to_brim(SAMPLE_FILES_DIR, output_path, enrich=True)

            output_df = pd.read_csv(output_path)

            # Note 5 has no provider_id
            note_5 = output_df[output_df["NOTE_ID"] == 5].iloc[0]
            self.assertNotIn("Provider:", note_5["NOTE_TEXT"])
            # But should still have person and visit info
            self.assertIn("Patient Year of Birth: 1965", note_5["NOTE_TEXT"])
            self.assertIn("Visit Type: Outpatient", note_5["NOTE_TEXT"])

        finally:
            if output_path.exists():
                os.unlink(output_path)

    def test_missing_visit_in_note(self):
        """Test handling of note with missing visit_occurrence_id."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False
        ) as tmp_file:
            output_path = Path(tmp_file.name)

        try:
            convert_omop_to_brim(SAMPLE_FILES_DIR, output_path, enrich=True)

            output_df = pd.read_csv(output_path)

            # Note 4 has no visit_occurrence_id
            note_4 = output_df[output_df["NOTE_ID"] == 4].iloc[0]
            self.assertNotIn("Visit Start Date:", note_4["NOTE_TEXT"])
            self.assertNotIn("Visit Type:", note_4["NOTE_TEXT"])
            # But should still have provider and person info
            self.assertIn("Provider: Dr. Sarah Smith", note_4["NOTE_TEXT"])
            self.assertIn("Patient Year of Birth: 1990", note_4["NOTE_TEXT"])

        finally:
            if output_path.exists():
                os.unlink(output_path)


class TestEdgeCases(unittest.TestCase):
    """Tests for edge cases."""

    def test_missing_optional_files(self):
        """Test conversion when optional files are missing."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Create only note.csv
            note_df = pd.DataFrame(
                {
                    "note_id": [1],
                    "person_id": [100],
                    "note_date": ["2023-01-15"],
                    "note_datetime": ["2023-01-15 10:00:00"],
                    "note_type_concept_id": [44814645],
                    "note_class_concept_id": [44803882],
                    "note_title": ["Test Note"],
                    "note_text": ["This is a test note."],
                    "provider_id": [10],
                    "visit_occurrence_id": [1000],
                }
            )
            note_df.to_csv(tmp_path / "note.csv", index=False)

            output_path = tmp_path / "output.csv"
            convert_omop_to_brim(tmp_path, output_path, enrich=True)

            # Should complete without error
            output_df = pd.read_csv(output_path)
            self.assertEqual(len(output_df), 1)
            # No enrichment should be present since lookup files are missing
            self.assertNotIn("Provider:", output_df.iloc[0]["NOTE_TEXT"])
            self.assertEqual(output_df.iloc[0]["NOTE_TEXT"], "This is a test note.")

    def test_empty_note_text(self):
        """Test handling of empty note_text."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            note_df = pd.DataFrame(
                {
                    "note_id": [1],
                    "person_id": [100],
                    "note_date": ["2023-01-15"],
                    "note_datetime": ["2023-01-15 10:00:00"],
                    "note_type_concept_id": [44814645],
                    "note_class_concept_id": [44803882],
                    "note_title": ["Empty Note"],
                    "note_text": [""],
                    "provider_id": [None],
                    "visit_occurrence_id": [None],
                }
            )
            note_df.to_csv(tmp_path / "note.csv", index=False)

            output_path = tmp_path / "output.csv"
            convert_omop_to_brim(tmp_path, output_path, enrich=False)

            output_df = pd.read_csv(output_path)
            # Empty string becomes NaN when read by pandas
            self.assertTrue(
                pd.isna(output_df.iloc[0]["NOTE_TEXT"])
                or output_df.iloc[0]["NOTE_TEXT"] == ""
            )


if __name__ == "__main__":
    unittest.main()
