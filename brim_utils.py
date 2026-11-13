#!/usr/bin/env python3
"""
Brim Setup - Project setup, user management, and data upload via the Brim API.

This script helps with setting up Brim projects, inviting users, and optionally
uploading clinical notes or structured data files (CSV or TSV) with support for
triggering generation and fetching results.

USAGE
-----
    python scripts/brim_utils.py [options]

EXAMPLES
--------
    # Create a project and invite users (no upload)
    python scripts/brim_utils.py \\
        --create-project "My Project" \\
        --users-to-add "user1@example.com,user2@example.com"

    # Create a project, invite users with upload permission
    python scripts/brim_utils.py \\
        --create-project "My Project" \\
        --users-to-add "user1@example.com,user2@example.com" \\
        --can-upload-permission

    # Upload notes file (CSV or TSV) to existing project
    python scripts/brim_utils.py --filepath notes.csv --project-id 123
    python scripts/brim_utils.py --filepath notes.tsv --project-id 123

    # Upload to existing project, run generation, and fetch results
    python scripts/brim_utils.py --filepath notes.csv \\
        --project-id 123 \\
        --generate-after-upload \\
        --fetch-results \\
        --output-file results.csv

    # Upload structured data file (CSV or TSV) to existing project
    python scripts/brim_utils.py --filepath structured.csv --structured-data --project-id 123
    python scripts/brim_utils.py --filepath structured.tsv --structured-data --project-id 123

    # Upload variable and DV definition files to an existing project
    # (either or both of --variable-file / --decision-file may be provided)
    python scripts/brim_utils.py --project-id 123 \\
        --variable-file variables.csv \\
        --decision-file dvs.csv

    # Create a new project and upload notes to it
    python scripts/brim_utils.py --filepath notes.csv --create-project "My New Project"

    # Create project or use existing if name matches, then upload
    python scripts/brim_utils.py --filepath notes.csv \\
        --create-project "My Project" \\
        --continue-if-project-exists

    # Full hands-off pipeline in one call: create project, import variable/DV
    # definitions, then upload notes and generate. When --variable-file /
    # --decision-file are combined with --notes-file, the definitions are
    # imported FIRST (the script waits for that import to complete) so the
    # variables exist before the notes upload triggers generation.
    python scripts/brim_utils.py \\
        --create-project "My Project" \\
        --continue-if-project-exists \\
        --variable-file variables.csv \\
        --decision-file dvs.csv \\
        --notes-file notes.csv \\
        --generate-after-upload \\
        --fetch-results \\
        --output-file results.csv

    # Full workflow: create project, invite users, upload, generate, fetch results
    python scripts/brim_utils.py --filepath notes.csv \\
        --create-project "My Project" \\
        --continue-if-project-exists \\
        --users-to-add "user1@example.com" \\
        --generate-after-upload \\
        --fetch-results \\
        --output-file results.csv

    # Upload validation labels (defaults to holdout; choose training explicitly)
    python scripts/brim_utils.py --project-id 123 \\
        --validation-file validation.csv --validation-target training

    # Fetch existing project-wide results without uploading anything
    python scripts/brim_utils.py --project-id 123 \\
        --fetch-results \\
        --output-file results.csv

    # Fetch a detailed export instead of the default patient export
    python scripts/brim_utils.py --project-id 123 \\
        --fetch-results \\
        --output-file results.csv \\
        --export-type detailed

    # Custom polling intervals (5s initial, 10min max)
    python scripts/brim_utils.py --filepath notes.csv \\
        --project-id 123 \\
        --generate-after-upload \\
        --fetch-results \\
        --output-file results.csv \\
        --poll-interval 5 \\
        --max-poll-interval 600

    # Wait for a starting server (e.g. freshly launched EC2) before uploading
    python scripts/brim_utils.py --filepath notes.csv \\
        --project-id 123 \\
        --wait-for-ready \\
        --ready-timeout 900

    # List patients whose latest document load is at least 14 days old
    python scripts/brim_utils.py --project-id 123 \\
        --list-patients-by-last-document-load 14 --patient-limit 1000 \\
        --output-file patients.json

    # Use an explicit reference date (date-only / naive dates use UTC)
    python scripts/brim_utils.py --project-id 123 \\
        --list-patients-by-last-document-load 14 --reference-date 2026-09-20

    # Permanently delete explicit MRNs (not database patient IDs)
    python scripts/brim_utils.py --project-id 123 --delete-patients 001 002

ARGUMENTS
---------
    --filepath PATH             Path to the clinical notes or structured-data
                                CSV/TSV file to upload (optional). Notes by
                                default; use --structured-data for structured
                                data. For variable/DV definition files, use
                                --variable-file / --decision-file instead.

    --validation-file PATH      Validation labels CSV/TSV; processed after notes.
                                Cannot be used with --generate-after-upload.
    --validation-target TARGET  training or holdout (default: holdout).
    --validation-only-reviewed  Import only accept/edit validation rows.
    --notes-file PATH           Path to a clinical notes CSV/TSV to upload.
                                Preferred alias for the notes use of --filepath
                                (provide one or the other, not both).

    --api-token STR             API token for Bearer authentication (required)
                                Can also be set via BRIM_API_TOKEN or API_TOKEN

    --url STR                   Base URL of the API
                                Default: http://localhost:8000
                                Can also be set via API_URL env var

PROJECT SELECTION (one required)
--------------------------------
    --project-id INT            Project ID to use
                                Can also be set via PROJECT_ID env var

    --create-project NAME       Create a new project with the given name
                                Fails if project with same name already exists
                                (unless --continue-if-project-exists is set)

    --continue-if-project-exists
                                When used with --create-project, continue with
                                the existing project instead of failing if a
                                project with the same name already exists

INVITE USERS
------------
    --users-to-add EMAILS       Comma-separated list of email addresses to invite
    --can-upload-permission     Grant upload permission to invited users

UPLOAD OPTIONS
--------------
    --notes                     Upload as notes file (default when --filepath provided)
    --structured-data           Upload --filepath as a structured data file
                                Cannot be used with --generate-after-upload, nor
                                combined with --structured-data-file
    --structured-data-file PATH Upload a structured data file in the same run as
                                a notes --filepath. Imported after variable/DV
                                definitions and before notes; the script waits
                                for the import task to complete.

VARIABLE / DV DEFINITION UPLOAD
-------------------------------
    --variable-file PATH        Path to a variable definition CSV/TSV to import
    --decision-file PATH        Path to a dependent-variable (DV) definition CSV/TSV
                                (alias: --dependent-variable-file)
    --overwrite-instruments     Clear and re-derive instruments on variable import

                                These run before any notes upload/generation and
                                the script waits for the import task to complete.

GENERATION & RESULTS
--------------------
    --generate-after-upload     Start LLM generation after upload completes
                                Requires --filepath (CSV or TSV)

    --fetch-results             Fetch results and save CSV. Requires --output-file.
                                With --generate-after-upload, polls the new
                                generation task and fetches its subset export.
                                Without --filepath, fetches the entire project's
                                existing results.

    --export-type TYPE          'patient' (default) or 'detailed'. Selects the
                                shape of the CSV returned by --fetch-results.

    --output-file PATH          Path to save results (CSV format), or the JSON
                                response from a patient operation
                                Required when using --fetch-results

PATIENT OPERATIONS
------------------
    --list-patients-by-last-document-load DAYS
                                List patients by latest document creation time,
                                not clinical note date. Cutoff is inclusive.
                                Patients without documents are included first.
    --patient-limit INT         Maximum returned patients (default: 1000).
                                No implicit pagination.
    --reference-date ISO        Reference date/datetime (default: now).
    --delete-patients MRN ...   Permanently delete explicit MRNs and their data.
                                Returns acceptance, not completion. The Celery
                                task handle cannot use /api/v1/task_status/.
                                Patient operations require --project-id and
                                run separately from upload/generation/invites.

POLLING OPTIONS
---------------
    --poll-interval INT         Initial polling interval in seconds (default: 2)
                                Uses exponential backoff up to max-poll-interval

    --max-poll-interval INT     Maximum polling interval in seconds (default: 300)

SERVER READINESS
----------------
    --wait-for-ready            Poll the server health endpoint (/-/health/)
                                until it responds before making any API calls.
                                Use when the server may still be starting
                                (e.g. a freshly launched or woken EC2 instance).
                                Connection errors and 5xx responses are retried
                                with exponential backoff.

    --ready-timeout INT         Maximum seconds to wait for the server with
                                --wait-for-ready (default: 600)

SSL OPTIONS
-----------
    --no-verify-ssl             Disable SSL certificate verification. Use for
                                staging or dev URLs with self-signed certs.
                                Do not use against production.

ENVIRONMENT VARIABLES
---------------------
    PROJECT_ID                  Default value for --project-id
    BRIM_API_TOKEN              Default value for --api-token (takes precedence)
    API_TOKEN                   Legacy fallback for --api-token
    API_URL                     Default value for --url

EXIT CODES
----------
    0                           Success
    1                           Error (invalid arguments, upload failed, generation failed)
    2                           Project already exists (when --create-project used without
                                --continue-if-project-exists)
"""

import argparse
import json
import os
import sys
import time
from contextlib import nullcontext, redirect_stdout
from pathlib import Path

import requests


# Task status constants matching SummitTask.Status
class TaskStatus:
    WAITING = 0
    RUNNING = 1
    COMPLETE = 2
    ERROR = 3
    STOPPED = 4


def _patient_request(
    method, project_id, api_token, api_url, *, verify_ssl=True, **kwargs
):
    """Make a bounded patient API request; return response data or None on error."""
    suffix = kwargs.pop("suffix", "")
    endpoint = f"{api_url.rstrip('/')}/api/v1/projects/{project_id}/patients/{suffix}"
    try:
        response = requests.request(
            method,
            endpoint,
            headers={"Authorization": f"Bearer {api_token}"},
            verify=verify_ssl,
            timeout=60,
            **kwargs,
        )
        expected = 202 if method == "DELETE" else 200
        if response.status_code != expected:
            print(
                f"Error: Patient API returned {response.status_code}: {response.text}",
                file=sys.stderr,
            )
            return None
        data = response.json()["data"]
        if not isinstance(data, dict):
            raise ValueError("Expected a data object")
        if method == "DELETE" and not data.get("task_id"):
            raise ValueError("Missing deletion task_id")
        if method == "GET" and not isinstance(data.get("patients"), list):
            raise ValueError("Missing patients list")
        return data
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        print(f"Error: Patient API request failed: {exc}", file=sys.stderr)
        return None


def list_patients_by_last_document_load(
    project_id,
    api_token,
    api_url,
    days=14,
    limit=1000,
    reference_date=None,
    verify_ssl=True,
):
    """List MRNs by latest document creation time (inclusive cutoff).

    Patients without documents are included first with null last_loaded_at.
    This is a limited result, not an automatically paginated full listing.
    reference_date accepts an ISO date/datetime; naive values mean UTC.
    """
    if isinstance(days, bool) or not isinstance(days, int) or days < 0:
        raise ValueError("days must be a nonnegative integer")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")
    params = {"days": days, "limit": limit}
    if reference_date is not None:
        params["reference_date"] = reference_date
    return _patient_request(
        "GET",
        project_id,
        api_token,
        api_url,
        verify_ssl=verify_ssl,
        suffix="by-last-document-load/",
        params=params,
    )


def delete_patients(project_id, patient_ids, api_token, api_url, verify_ssl=True):
    """Queue deletion of explicit patient MRNs and all their project data.

    Returns the Celery task handle on acceptance, not completion. This handle
    cannot be polled using the SummitTask /task_status/ endpoint.
    """
    if not isinstance(patient_ids, (list, tuple)) or not patient_ids:
        raise ValueError("patient_ids must be a nonempty list of MRN strings")
    if any(not isinstance(mrn, str) or not mrn.strip() for mrn in patient_ids):
        raise ValueError("patient_ids must contain only nonempty MRN strings")
    patient_ids = list(dict.fromkeys(mrn.strip() for mrn in patient_ids))
    return _patient_request(
        "DELETE",
        project_id,
        api_token,
        api_url,
        verify_ssl=verify_ssl,
        json={"patient_ids": patient_ids},
    )


def wait_for_ready(
    api_url,
    timeout=600,
    initial_interval=2,
    max_interval=30,
    verify_ssl=True,
):
    """
    Poll the server health endpoint until it responds, or until timeout.

    Intended for deployments where the Brim server may still be starting
    (e.g. an EC2 instance that was just launched or woken): connection
    errors and 5xx responses (nginx up but the app still booting) are
    treated as "not ready yet" and retried with exponential backoff.

    Args:
        api_url (str): Base URL of the API
        timeout (int): Maximum seconds to wait before giving up
        initial_interval (int): Initial polling interval in seconds
        max_interval (int): Maximum polling interval in seconds
        verify_ssl (bool): Whether to verify SSL certificates.

    Returns:
        bool: True once the server reports healthy, False on timeout
    """
    endpoint = f"{api_url.rstrip('/')}/-/health/"
    deadline = time.monotonic() + timeout
    interval = initial_interval

    print(f"Waiting for server to become ready: {endpoint} (timeout: {timeout}s)")

    while True:
        try:
            response = requests.get(endpoint, timeout=10, verify=verify_ssl)
            if response.status_code == 200:
                print("Server is ready.")
                return True
            print(f"  Server not ready yet (HTTP {response.status_code})")
        except requests.exceptions.RequestException as e:
            print(f"  Server not reachable yet ({type(e).__name__})")

        if time.monotonic() + interval > deadline:
            print(f"Error: Server did not become ready within {timeout}s")
            return False

        time.sleep(interval)
        interval = min(interval * 1.5, max_interval)


def upload_csv(
    filepath, project_id, api_token, api_url, generate_after_upload, verify_ssl=True
):
    """
    Upload a notes file (CSV or TSV) to the API endpoint.

    Args:
        filepath (str): Path to the CSV or TSV file to upload
        project_id (int): Project ID to upload to
        api_token (str): API project token for authentication
        api_url (str): Base URL of the API
        generate_after_upload (bool): Start generation after upload.
        verify_ssl (bool): Whether to verify SSL certificates.

    Returns:
        dict: Response data if successful, None otherwise
    """
    if not os.path.exists(filepath):
        print(f"Error: File not found: {filepath}")
        return None

    try:
        headers = {
            "Authorization": f"Bearer {api_token}",
        }

        files = {"csv_file": open(filepath, "rb")}
        data = {
            "project_id": str(project_id),
            "generate_after_upload": generate_after_upload,
        }

        endpoint = f"{api_url.rstrip('/')}/api/v1/upload/csv/"
        response = requests.post(
            endpoint, headers=headers, data=data, files=files, verify=verify_ssl
        )

        if response.status_code == 200:
            result = response.json()
            print(f"Success! Upload successful: {result['data']['original_filename']}")
            print(f"Upload Task ID: {result['data']['upload_task_id']}")
            if result["data"].get("generation_task_id"):
                print(f"Generation Task ID: {result['data']['generation_task_id']}")
            return result["data"]
        else:
            print(f"Error: Upload failed with status code {response.status_code}")
            print(f"Response: {response.text}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"Error: Failed to connect to server: {e}")
        return None
    except Exception as e:
        print(f"Error: {str(e)}")
        return None
    finally:
        if "files" in locals():
            files["csv_file"].close()


def upload_validation(
    filepath,
    project_id,
    api_token,
    api_url,
    target="holdout",
    only_reviewed=False,
    verify_ssl=True,
):
    """Upload validation labels; return dataset/task metadata or None on failure."""
    try:
        with open(filepath, "rb") as source:
            response = requests.post(
                f"{api_url.rstrip('/')}/api/v1/upload/validation/",
                headers={"Authorization": f"Bearer {api_token}"},
                data={
                    "project_id": str(project_id),
                    "target": target,
                    "only_reviewed": only_reviewed,
                },
                files={"csv_file": source},
                verify=verify_ssl,
            )
        if response.status_code != 200:
            print(
                f"Error: Validation upload failed ({response.status_code}): {response.text}"
            )
            return None
        result = response.json()
        print(result["message"])
        return result["data"]
    except (OSError, requests.exceptions.RequestException, ValueError) as exc:
        print(f"Error: Validation upload failed: {exc}")
        return None


def upload_structured_data(filepath, project_id, api_token, api_url, verify_ssl=True):
    """
    Upload a structured data file (CSV or TSV) to the API endpoint.

    Args:
        filepath (str): Path to the CSV or TSV file to upload
        project_id (int): Project ID to upload to
        api_token (str): API project token for authentication
        api_url (str): Base URL of the API
        verify_ssl (bool): Whether to verify SSL certificates.

    Returns:
        dict: Response data if successful, None otherwise
    """
    if not os.path.exists(filepath):
        print(f"Error: File not found: {filepath}")
        return None

    try:
        headers = {
            "Authorization": f"Bearer {api_token}",
        }

        files = {"csv_file": open(filepath, "rb")}
        data = {
            "project_id": str(project_id),
        }

        endpoint = f"{api_url.rstrip('/')}/api/v1/upload/structured-data/"
        response = requests.post(
            endpoint, headers=headers, data=data, files=files, verify=verify_ssl
        )

        if response.status_code == 200:
            result = response.json()
            print(
                f"Success! Structured data upload started: "
                f"{result['data']['original_filename']}"
            )
            print(f"Upload Task ID: {result['data']['upload_task_id']}")
            return result["data"]
        else:
            print(f"Error: Upload failed with status code {response.status_code}")
            print(f"Response: {response.text}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"Error: Failed to connect to server: {e}")
        return None
    except Exception as e:
        print(f"Error: {str(e)}")
        return None
    finally:
        if "files" in locals():
            files["csv_file"].close()


def upload_variables_decisions(
    variable_file,
    decision_file,
    project_id,
    api_token,
    api_url,
    overwrite_instruments=False,
    verify_ssl=True,
):
    """
    Upload variable and/or dependent-variable (DV) definition files.

    At least one of ``variable_file`` / ``decision_file`` must be provided.

    Args:
        variable_file (str | None): Path to the variable definition CSV/TSV.
        decision_file (str | None): Path to the DV definition CSV/TSV.
        project_id (int): Project ID to import into.
        api_token (str): API token for authentication.
        api_url (str): Base URL of the API.
        overwrite_instruments (bool): Clear and re-derive instruments.
        verify_ssl (bool): Whether to verify SSL certificates.

    Returns:
        dict: Response data if successful, None otherwise.
    """
    for label, path in (("variable", variable_file), ("decision", decision_file)):
        if path and not os.path.exists(path):
            print(f"Error: {label} file not found: {path}")
            return None

    uploading = []
    if variable_file:
        uploading.append(f"variable file '{os.path.basename(variable_file)}'")
    if decision_file:
        uploading.append(f"DV file '{os.path.basename(decision_file)}'")
    print(f"Starting upload of {' and '.join(uploading)} to project {project_id}...")

    open_files = []
    try:
        headers = {
            "Authorization": f"Bearer {api_token}",
        }

        files = {}
        if variable_file:
            fh = open(variable_file, "rb")
            open_files.append(fh)
            files["variable_file"] = fh
        if decision_file:
            fh = open(decision_file, "rb")
            open_files.append(fh)
            files["decision_file"] = fh

        data = {
            "project_id": str(project_id),
            "overwrite_instruments": overwrite_instruments,
        }

        endpoint = f"{api_url.rstrip('/')}/api/v1/upload/variables/"
        response = requests.post(
            endpoint, headers=headers, data=data, files=files, verify=verify_ssl
        )

        if response.status_code == 200:
            result = response.json()
            print("Success! Variable/DV definition upload started.")
            print(f"Upload Task ID: {result['data']['upload_task_id']}")
            print(
                f"  variables: {result['data']['has_variables']}, "
                f"decisions: {result['data']['has_decisions']}"
            )
            return result["data"]
        else:
            print(f"Error: Upload failed with status code {response.status_code}")
            print(f"Response: {response.text}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"Error: Failed to connect to server: {e}")
        return None
    except Exception as e:
        print(f"Error: {str(e)}")
        return None
    finally:
        for fh in open_files:
            fh.close()


def create_project(project_name, api_token, api_url, verify_ssl=True):
    """
    Create a new project via the API.

    Args:
        project_name (str): Name for the new project
        api_token (str): API token for authentication
        api_url (str): Base URL of the API
        verify_ssl (bool): Whether to verify SSL certificates.

    Returns:
        tuple: (project_id, created) where:
            - project_id (int): The project ID if successful, None on error
            - created (bool): True if newly created, False if already existed
    """
    try:
        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }

        payload = {"name": project_name}
        endpoint = f"{api_url.rstrip('/')}/api/v1/projects/"
        response = requests.post(
            endpoint, headers=headers, json=payload, verify=verify_ssl
        )

        if response.status_code == 201:
            result = response.json()
            project_id = result["data"]["id"]
            created = result["data"]["created"]
            if created:
                print(f"Project created: '{project_name}' (ID: {project_id})")
            else:
                print(f"Project already exists: '{project_name}' (ID: {project_id})")
            return project_id, created
        else:
            print(f"Error: Failed to create project with status {response.status_code}")
            print(f"Response: {response.text}")
            return None, False

    except requests.exceptions.RequestException as e:
        print(f"Error: Failed to connect to server: {e}")
        return None, False
    except Exception as e:
        print(f"Error: {str(e)}")
        return None, False


def poll_task_status(
    task_id,
    project_id,
    api_token,
    api_url,
    initial_interval=2,
    max_interval=300,
    max_retries=None,
    verify_ssl=True,
):
    """
    Poll the task status endpoint until the task completes or fails.

    Args:
        task_id (str): Task ID to check
        project_id (int): Project ID
        api_token (str): API project token for authentication
        api_url (str): Base URL of the API
        initial_interval (int): Initial polling interval in seconds
        max_interval (int): Maximum polling interval in seconds
        max_retries (int): Maximum number of retries (None for unlimited)
        verify_ssl (bool): Whether to verify SSL certificates.

    Returns:
        int: Final task status (COMPLETE=2, ERROR=3, STOPPED=4) or None on error
    """
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }

    endpoint = f"{api_url.rstrip('/')}/api/v1/task_status/"
    payload = {
        "project_id": project_id,
        "task_id": task_id,
    }

    interval = initial_interval
    retries = 0

    print(f"Polling task status for task {task_id}...")

    while True:
        try:
            response = requests.post(
                endpoint, headers=headers, json=payload, verify=verify_ssl
            )

            if response.status_code == 200:
                result = response.json()
                task_data = result["data"]
                status = task_data["task_status"]
                status_display = task_data["task_status_display"]

                # Show aggregated progress when the API reports it.
                total_steps = task_data.get("total_steps") or 0
                progress = task_data.get("progress") or 0
                progress_str = ""
                if total_steps:
                    pct = int(100 * progress / total_steps)
                    progress_str = f" - {progress}/{total_steps} steps ({pct}%)"

                print(f"  Status: {status_display} ({status}){progress_str}")

                # Check for terminal states
                if status in [
                    TaskStatus.COMPLETE,
                    TaskStatus.ERROR,
                    TaskStatus.STOPPED,
                ]:
                    return status

            else:
                print(
                    f"Error checking task status: {response.status_code} - "
                    f"{response.text}"
                )
                return None

        except requests.exceptions.RequestException as e:
            print(f"Error connecting to server: {e}")
            return None

        # Check retry limit
        retries += 1
        if max_retries is not None and retries >= max_retries:
            print(f"Max retries ({max_retries}) reached")
            return None

        # Wait with exponential backoff
        time.sleep(interval)
        interval = min(interval * 1.5, max_interval)


def _parse_results_response(response):
    """
    Parse a response from the results API endpoint.

    Args:
        response: requests.Response object

    Returns:
        tuple: (csv_content, export_task_id, error_msg)
            - csv_content: CSV string if response contains CSV data
            - export_task_id: Task ID to poll if export is in progress
            - error_msg: Error message if something went wrong
    """
    content_type = response.headers.get("Content-Type", "")

    if "text/csv" in content_type:
        return response.text, None, None

    if response.status_code != 200:
        return None, None, f"API error: {response.status_code} - {response.text}"

    result = response.json()
    data = result.get("data", {})

    # Check for error status
    status = data.get("status")
    is_complete = data.get("is_complete", False)
    if status == TaskStatus.ERROR or (is_complete and status != TaskStatus.COMPLETE):
        message = data.get("message", "Unknown error")
        return None, None, f"Export failed: {message}"

    # Return export_task_id for polling
    export_task_id = data.get("export_task_id")
    status_display = data.get("status_display", "Unknown")
    return (
        None,
        export_task_id,
        None if export_task_id else f"Status: {status_display}",
    )


def fetch_results(
    task_id,
    project_id,
    api_token,
    api_url,
    output_file,
    initial_interval=2,
    max_interval=300,
    export_type="patient",
    verify_ssl=True,
):
    """
    Fetch results. Creates an export task (or returns a cached one) and polls
    until the CSV is ready.

    Args:
        task_id (str | None): Generation or upload task ID to fetch a subset
            for. Pass ``None`` for a project-wide export of all results.
        project_id (int): Project ID
        api_token (str): API project token for authentication
        api_url (str): Base URL of the API
        output_file (str): Path to save CSV results
        initial_interval (int): Initial polling interval in seconds
        max_interval (int): Maximum polling interval in seconds
        export_type (str): "detailed" or "patient" — selects the API's
            ``detailed_export`` / ``patient_export`` flag.
        verify_ssl (bool): Whether to verify SSL certificates.

    Returns:
        bool: True if successful, False otherwise
    """
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }
    endpoint = f"{api_url.rstrip('/')}/api/v1/results/"

    scope = f"task {task_id}" if task_id else "the full project"
    print(f"Fetching {export_type} results for {scope}...")

    try:
        payload = {
            "project_id": project_id,
            "get_csv": True,
            "detailed_export": export_type == "detailed",
            "patient_export": export_type == "patient",
        }
        if task_id:
            payload["task_id"] = task_id
        response = requests.post(
            endpoint, headers=headers, json=payload, verify=verify_ssl
        )
        csv_content, export_task_id, error = _parse_results_response(response)

        if csv_content:
            with open(output_file, "w") as f:
                f.write(csv_content)
            print(f"Results saved to: {output_file}")
            return True

        if error:
            print(f"Error: {error}")
            return False

        if not export_task_id:
            print("Error: No export_task_id returned")
            return False

        print(f"Export task created: {export_task_id}")

        # Poll for export completion
        interval = initial_interval
        poll_payload = {
            "project_id": project_id,
            "task_id": export_task_id,
            "get_csv": True,
        }

        while True:
            time.sleep(interval)
            response = requests.post(
                endpoint, headers=headers, json=poll_payload, verify=verify_ssl
            )
            csv_content, _, error = _parse_results_response(response)

            if csv_content:
                with open(output_file, "w") as f:
                    f.write(csv_content)
                print(f"Results saved to: {output_file}")
                return True

            if error:
                print(f"Error: {error}")
                return False

            interval = min(interval * 1.5, max_interval)

    except requests.exceptions.RequestException as e:
        print(f"Error connecting to server: {e}")
        return False
    except Exception as e:
        print(f"Error: {str(e)}")
        return False


def invite_user(
    email: str,
    project_id: int,
    api_token: str,
    api_url: str,
    can_upload_permission: bool = False,
    verify_ssl: bool = True,
):
    """
    Invite a user to a project via the API.

    Args:
        email (str): Email address of the user to invite
        project_id (int): Project ID to invite the user to
        api_token (str): API token for authentication
        api_url (str): Base URL of the API
        can_upload_permission (bool): Grant upload permission to the user
        verify_ssl (bool): Whether to verify SSL certificates.

    Returns:
        bool: True if successful, False otherwise
    """
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "email": email,
        "project_id": project_id,
        "can_upload_permission": can_upload_permission,
    }

    endpoint = f"{api_url.rstrip('/')}/api/v1/users/invite/"

    try:
        response = requests.post(
            endpoint, headers=headers, json=payload, verify=verify_ssl
        )

        if response.status_code == 200:
            result = response.json()
            print(f"Success: {result.get('message', f'User {email} invited')}")
            return True
        else:
            try:
                error_data = response.json()
                error_msg = error_data.get("detail", response.text)
            except ValueError:
                error_msg = response.text
            print(f"Error inviting {email}: {response.status_code} - {error_msg}")
            return False

    except requests.exceptions.RequestException as e:
        print(f"Error: Failed to connect to server: {e}")
        return False


def create_parser():
    """Create and return the argument parser for the brim setup script."""
    parser = argparse.ArgumentParser(
        description="Set up Brim projects, invite users, and upload data via the API"
    )
    parser.add_argument(
        "--filepath",
        type=str,
        help=(
            "Path to the clinical notes or structured-data CSV/TSV file to "
            "upload (notes by default; use --structured-data for structured "
            "data). For variable/DV definitions use --variable-file / "
            "--decision-file instead."
        ),
        default=None,
    )
    parser.add_argument(
        "--notes-file",
        type=str,
        help=(
            "Path to a clinical notes CSV/TSV to upload. Preferred, consistent "
            "alias for the notes use of --filepath (provide one or the other)."
        ),
        default=None,
    )
    parser.add_argument(
        "--project-id",
        type=int,
        help="Project ID to upload to",
        default=os.environ.get("PROJECT_ID"),
    )
    parser.add_argument(
        "--create-project",
        type=str,
        metavar="NAME",
        help="Create a new project with this name",
        default=None,
    )
    parser.add_argument(
        "--continue-if-project-exists",
        action="store_true",
        help="Continue if project already exists (use with --create-project)",
    )
    parser.add_argument(
        "--api-token",
        type=str,
        help="API token for Bearer authentication",
        default=os.environ.get("BRIM_API_TOKEN") or os.environ.get("API_TOKEN"),
    )
    parser.add_argument(
        "--url",
        type=str,
        help="Base URL of the API",
        default=os.environ.get("API_URL", "http://localhost:8000"),
    )

    patients = parser.add_mutually_exclusive_group()
    patients.add_argument(
        "--list-patients-by-last-document-load",
        type=int,
        metavar="DAYS",
        help=(
            "List patients whose latest document load is at least DAYS old "
            "(includes patients without documents)"
        ),
    )
    patients.add_argument(
        "--delete-patients",
        nargs="+",
        metavar="MRN",
        help=(
            "Permanently delete these explicit patient MRNs and their data; "
            "returns an async task handle"
        ),
    )
    parser.add_argument(
        "--patient-limit",
        type=int,
        default=None,
        help="Maximum patients to list (default: 1000)",
    )
    parser.add_argument(
        "--reference-date",
        help="ISO reference date/datetime for the age cutoff (default: now; naive values use UTC)",
    )

    parser.add_argument(
        "--validation-file",
        help="Validation labels CSV/TSV to upload after notes and definitions",
    )
    parser.add_argument(
        "--validation-target",
        choices=["training", "holdout"],
        default=None,
        help="Validation destination (default: holdout)",
    )
    parser.add_argument(
        "--validation-only-reviewed",
        action="store_true",
        help="Import only accept/edit validation rows",
    )

    # Mutually exclusive upload type group
    upload_type = parser.add_mutually_exclusive_group()
    upload_type.add_argument(
        "--notes",
        action="store_true",
        help="Upload as notes file — CSV or TSV (default behavior)",
    )
    upload_type.add_argument(
        "--structured-data",
        action="store_true",
        help="Upload as structured data file — CSV or TSV",
    )

    parser.add_argument(
        "--structured-data-file",
        type=str,
        help=(
            "Path to a structured-data CSV/TSV to upload alongside notes. Unlike "
            "--filepath --structured-data, this can be combined with a notes "
            "--filepath in one run."
        ),
        default=None,
    )
    parser.add_argument(
        "--variable-file",
        type=str,
        help="Path to a variable definition CSV/TSV to upload",
        default=None,
    )
    parser.add_argument(
        "--decision-file",
        "--dependent-variable-file",  # alias; user-facing term per naming convention
        dest="decision_file",  # pin dest so the alias can't change it regardless of order
        type=str,
        help="Path to a dependent-variable (DV) definition CSV/TSV to upload",
        default=None,
    )
    parser.add_argument(
        "--overwrite-instruments",
        action="store_true",
        help="Clear and re-derive instruments when uploading variable definitions",
        default=False,
    )
    parser.add_argument(
        "--generate-after-upload",
        action="store_true",
        help="Start generation after upload completes",
    )
    parser.add_argument(
        "--fetch-results",
        action="store_true",
        help=(
            "Fetch results and save CSV. With --generate-after-upload, polls "
            "the generation task and fetches its subset export. Without "
            "--filepath, fetches the entire project's existing results."
        ),
    )
    parser.add_argument(
        "--export-type",
        type=str,
        choices=["detailed", "patient"],
        default="patient",
        help="Export type for --fetch-results (default: patient)",
    )
    parser.add_argument(
        "--output-file",
        type=str,
        help="Path to save results CSV or a patient operation's JSON response",
        default=None,
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        help="Initial polling interval in seconds (default: 2)",
        default=2,
    )
    parser.add_argument(
        "--max-poll-interval",
        type=int,
        help="Maximum polling interval in seconds (default: 300)",
        default=300,
    )
    parser.add_argument(
        "--users-to-add",
        type=str,
        help="Comma-separated list of email addresses to invite to the project",
        default=None,
    )
    parser.add_argument(
        "--can-upload-permission",
        action="store_true",
        help="Grant upload permission to the users",
        default=False,
    )
    parser.add_argument(
        "--no-verify-ssl",
        action="store_true",
        help="Disable SSL certificate verification (use for self-signed certs)",
        default=False,
    )
    parser.add_argument(
        "--wait-for-ready",
        action="store_true",
        help=(
            "Poll the server health endpoint until it responds before making "
            "any API calls. Use when the Brim server may still be starting "
            "(e.g. a freshly launched or woken EC2 instance)."
        ),
        default=False,
    )
    parser.add_argument(
        "--ready-timeout",
        type=int,
        help=(
            "Maximum seconds to wait for the server with --wait-for-ready "
            "(default: 600)"
        ),
        default=600,
    )

    return parser


def main():
    parser = create_parser()
    args = parser.parse_args()

    # Validate required arguments
    if not args.api_token:
        print(
            "Error: API token is required. "
            "Provide it via --api-token or set BRIM_API_TOKEN or API_TOKEN "
            "environment variable"
        )
        sys.exit(1)

    # Validate project selection
    if not args.project_id and not args.create_project:
        print(
            "Error: Either --project-id or --create-project is required. "
            "Provide --project-id or set PROJECT_ID environment variable, "
            "or use --create-project to create a new project."
        )
        sys.exit(1)

    if args.project_id and args.create_project:
        print("Error: Cannot use both --project-id and --create-project")
        sys.exit(1)

    if args.continue_if_project_exists and not args.create_project:
        print("Error: --continue-if-project-exists requires --create-project")
        sys.exit(1)

    patient_action = (
        args.list_patients_by_last_document_load is not None
        or args.delete_patients is not None
    )
    if patient_action:
        if not args.project_id or any(
            (
                args.create_project,
                args.filepath,
                args.notes_file,
                args.variable_file,
                args.decision_file,
                args.structured_data_file,
                args.validation_file,
                args.validation_target,
                args.validation_only_reviewed,
                args.structured_data,
                args.notes,
                args.users_to_add,
                args.generate_after_upload,
                args.fetch_results,
            )
        ):
            parser.error(
                "Patient operations require --project-id and cannot be combined "
                "with uploads, invitations, generation, or results"
            )
        if (
            args.list_patients_by_last_document_load is not None
            and args.list_patients_by_last_document_load < 0
        ):
            parser.error("--list-patients-by-last-document-load must be nonnegative")
        if args.delete_patients is not None and any(
            not mrn.strip() for mrn in args.delete_patients
        ):
            parser.error("--delete-patients requires nonempty MRNs")
    if args.patient_limit is not None and args.patient_limit < 1:
        parser.error("--patient-limit must be positive")
    if (
        args.patient_limit is not None or args.reference_date is not None
    ) and args.list_patients_by_last_document_load is None:
        parser.error(
            "--patient-limit and --reference-date require --list-patients-by-last-document-load"
        )

    if (
        args.validation_target or args.validation_only_reviewed
    ) and not args.validation_file:
        parser.error(
            "--validation-target and --validation-only-reviewed require --validation-file"
        )

    if args.validation_file and args.generate_after_upload:
        # The validation upload waits on the notes task, which is the
        # generation task when generation is requested.
        parser.error("--validation-file cannot be used with --generate-after-upload")

    # Validate argument combinations
    if args.structured_data and not args.filepath:
        print("Error: --structured-data requires --filepath")
        sys.exit(1)

    if args.notes and not args.filepath and not args.notes_file:
        print("Error: --notes requires --filepath or --notes-file")
        sys.exit(1)

    if args.notes_file and args.filepath and not args.structured_data:
        print("Error: provide notes via either --notes-file or --filepath, not both")
        sys.exit(1)

    if args.generate_after_upload and not args.notes_file and not args.filepath:
        print(
            "Error: --generate-after-upload requires a notes file "
            "(--notes-file or --filepath)"
        )
        sys.exit(1)

    if args.fetch_results and not args.output_file:
        print("Error: --fetch-results requires --output-file")
        sys.exit(1)

    if args.structured_data and args.generate_after_upload:
        print("Error: --structured-data cannot be used with --generate-after-upload")
        sys.exit(1)

    if args.structured_data and args.structured_data_file:
        print(
            "Error: --structured-data-file cannot be combined with the legacy "
            "--structured-data flag; use one or the other"
        )
        sys.exit(1)

    verify_ssl = not args.no_verify_ssl
    if not verify_ssl:
        print(
            "Warning: SSL certificate verification is disabled",
            file=sys.stderr if patient_action else sys.stdout,
        )

    # Wait for the server to come up before any API call (e.g. an EC2
    # instance that was just started for this run).
    if args.wait_for_ready:
        # Keep patient-operation stdout machine-readable even with readiness logs.
        with redirect_stdout(sys.stderr) if patient_action else nullcontext():
            ready = wait_for_ready(
                args.url,
                timeout=args.ready_timeout,
                initial_interval=args.poll_interval,
                verify_ssl=verify_ssl,
            )
        if not ready:
            sys.exit(1)

    if patient_action:
        if args.delete_patients is not None:
            data = delete_patients(
                args.project_id,
                args.delete_patients,
                args.api_token,
                args.url,
                verify_ssl=verify_ssl,
            )
        elif args.list_patients_by_last_document_load is not None:
            data = list_patients_by_last_document_load(
                args.project_id,
                args.api_token,
                args.url,
                days=args.list_patients_by_last_document_load,
                limit=args.patient_limit or 1000,
                reference_date=args.reference_date,
                verify_ssl=verify_ssl,
            )
        else:
            parser.error("No supported patient action was selected")
        if data is None:
            sys.exit(1)
        rendered = json.dumps(data, indent=2)
        if args.output_file:
            try:
                Path(args.output_file).expanduser().write_text(
                    rendered + "\n", encoding="utf-8"
                )
            except OSError as exc:
                print(f"Error writing patient response: {exc}", file=sys.stderr)
                sys.exit(1)
        print(rendered)
        return

    # Normalize file paths if provided
    filepath = None
    if args.filepath:
        filepath = str(Path(args.filepath).expanduser().resolve())
    variable_file = None
    if args.variable_file:
        variable_file = str(Path(args.variable_file).expanduser().resolve())
    decision_file = None
    if args.decision_file:
        decision_file = str(Path(args.decision_file).expanduser().resolve())
    structured_data_file = None
    if args.structured_data_file:
        structured_data_file = str(
            Path(args.structured_data_file).expanduser().resolve()
        )

    # Resolve the effective notes path: the dedicated --notes-file, or --filepath
    # when it isn't being routed to a legacy structured-data upload.
    notes_path = None
    if args.notes_file:
        notes_path = str(Path(args.notes_file).expanduser().resolve())
    elif filepath and not args.structured_data:
        notes_path = filepath

    # Determine project_id (either from args or by creating a new project)
    project_id = args.project_id
    if args.create_project:
        project_id, was_created = create_project(
            args.create_project,
            args.api_token,
            args.url,
            verify_ssl=verify_ssl,
        )
        if project_id is None:
            sys.exit(1)
        if not was_created and not args.continue_if_project_exists:
            print(
                "Error: Project already exists. "
                "Use --continue-if-project-exists to proceed with existing project."
            )
            sys.exit(2)

    # Invite users if indicated
    if args.users_to_add:
        email_addresses = [email.strip() for email in args.users_to_add.split(",")]
        failed_invites = []
        print(f"Inviting {len(email_addresses)} users to project {project_id}")
        for email in email_addresses:
            if not invite_user(
                email,
                project_id,
                args.api_token,
                args.url,
                args.can_upload_permission,
                verify_ssl=verify_ssl,
            ):
                failed_invites.append(email)
        if failed_invites:
            print(f"Warning: Failed to invite {len(failed_invites)} user(s)")

    # Upload variable / DV definition files if provided. Do this before any
    # notes upload + generation so the new variables exist when generation runs.
    if variable_file or decision_file:
        var_result = upload_variables_decisions(
            variable_file,
            decision_file,
            project_id,
            args.api_token,
            args.url,
            overwrite_instruments=args.overwrite_instruments,
            verify_ssl=verify_ssl,
        )
        if not var_result:
            sys.exit(1)

        # Wait for the import to finish so later steps see the new variables.
        var_task_id = var_result.get("upload_task_id")
        if var_task_id:
            status = poll_task_status(
                var_task_id,
                project_id,
                args.api_token,
                args.url,
                initial_interval=args.poll_interval,
                max_interval=args.max_poll_interval,
                verify_ssl=verify_ssl,
            )
            if status != TaskStatus.COMPLETE:
                print("Error: Variable/DV upload did not complete successfully")
                sys.exit(1)
            print("Variable/DV upload complete!")

    # Upload a structured-data file if provided via the dedicated flag. This
    # runs after variable/DV import and before the notes upload so the data is
    # in place before any generation. (The legacy --filepath --structured-data
    # mode is still handled in the notes-upload block below.)
    if structured_data_file:
        sd_result = upload_structured_data(
            structured_data_file,
            project_id,
            args.api_token,
            args.url,
            verify_ssl=verify_ssl,
        )
        if not sd_result:
            sys.exit(1)

        sd_task_id = sd_result.get("upload_task_id")
        if sd_task_id:
            status = poll_task_status(
                sd_task_id,
                project_id,
                args.api_token,
                args.url,
                initial_interval=args.poll_interval,
                max_interval=args.max_poll_interval,
                verify_ssl=verify_ssl,
            )
            if status != TaskStatus.COMPLETE:
                print("Error: Structured data upload did not complete successfully")
                sys.exit(1)
            print("Structured data upload complete!")

    result = None

    # Legacy mode: --filepath --structured-data uploads the file as structured
    # data. (The dedicated --structured-data-file flag is handled above.)
    if filepath and args.structured_data:
        sd_legacy = upload_structured_data(
            filepath,
            project_id,
            args.api_token,
            args.url,
            verify_ssl=verify_ssl,
        )
        if not sd_legacy:
            sys.exit(1)
        result = sd_legacy

    # Notes upload (+ optional generation). result is overwritten with the notes
    # response so --fetch-results below can pick up its generation_task_id.
    if notes_path:
        notes_result = upload_csv(
            notes_path,
            project_id,
            args.api_token,
            args.url,
            args.generate_after_upload,
            verify_ssl=verify_ssl,
        )
        if not notes_result:
            sys.exit(1)
        result = notes_result

    if args.validation_file:
        # Notes must be present before validation is matched to patients/documents.
        if result and result.get("upload_task_id"):
            status = poll_task_status(
                result["upload_task_id"],
                project_id,
                args.api_token,
                args.url,
                initial_interval=args.poll_interval,
                max_interval=args.max_poll_interval,
                verify_ssl=verify_ssl,
            )
            if status != TaskStatus.COMPLETE:
                print("Error: Data upload did not complete successfully")
                sys.exit(1)
        validation_result = upload_validation(
            str(Path(args.validation_file).expanduser().resolve()),
            project_id,
            args.api_token,
            args.url,
            target=args.validation_target or "holdout",
            only_reviewed=args.validation_only_reviewed,
            verify_ssl=verify_ssl,
        )
        if validation_result is None:
            sys.exit(1)
        validation_task_id = validation_result.get("upload_task_id")
        if validation_task_id:
            status = poll_task_status(
                validation_task_id,
                project_id,
                args.api_token,
                args.url,
                initial_interval=args.poll_interval,
                max_interval=args.max_poll_interval,
                verify_ssl=verify_ssl,
            )
            if status != TaskStatus.COMPLETE:
                print("Error: Validation upload did not complete successfully")
                sys.exit(1)
            print("Validation upload complete!")

    # Handle fetch-results flow
    if args.fetch_results:
        # If we just kicked off generation, wait for it and fetch its subset;
        # otherwise fall through to a project-wide fetch (task_id stays None).
        generation_task_id = result.get("generation_task_id") if result else None

        if generation_task_id:
            status = poll_task_status(
                generation_task_id,
                project_id,
                args.api_token,
                args.url,
                initial_interval=args.poll_interval,
                max_interval=args.max_poll_interval,
                verify_ssl=verify_ssl,
            )
            status_messages = {
                TaskStatus.ERROR: "Generation ended with ERROR status",
                TaskStatus.STOPPED: "Generation was STOPPED",
            }
            if status != TaskStatus.COMPLETE:
                print(
                    status_messages.get(
                        status, f"Generation ended with unexpected status: {status}"
                    )
                )
                sys.exit(1)
            print("Generation complete!")

        success = fetch_results(
            generation_task_id,
            project_id,
            args.api_token,
            args.url,
            args.output_file,
            initial_interval=args.poll_interval,
            max_interval=args.max_poll_interval,
            export_type=args.export_type,
            verify_ssl=verify_ssl,
        )
        if not success:
            sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
