#!/usr/bin/env python3
"""
Upload CSV files to the Brim API.

This script uploads clinical notes or structured data CSV files to the Brim API,
with optional support for creating projects, triggering generation, and fetching results.

USAGE
-----
    python scripts/upload_file_via_api.py <filepath> [options]

EXAMPLES
--------
    # Upload notes CSV to existing project
    python scripts/upload_file_via_api.py notes.csv --project-id 123

    # Upload to existing project, run generation, and fetch results
    python scripts/upload_file_via_api.py notes.csv \\
        --project-id 123 \\
        --generate-after-upload \\
        --fetch-results \\
        --output-file results.csv

    # Upload structured data CSV to existing project
    python scripts/upload_file_via_api.py structured.csv --structured-data --project-id 123

    # Create a new project and upload notes to it
    python scripts/upload_file_via_api.py notes.csv --create-project "My New Project"

    # Create project or use existing if name matches, then upload
    python scripts/upload_file_via_api.py notes.csv \\
        --create-project "My Project" \\
        --continue-if-project-exists

    # Full workflow with new project: create, upload, generate, fetch results
    python scripts/upload_file_via_api.py notes.csv \\
        --create-project "My Project" \\
        --continue-if-project-exists \\
        --generate-after-upload \\
        --fetch-results \\
        --output-file results.csv

    # Custom polling intervals (5s initial, 10min max)
    python scripts/upload_file_via_api.py notes.csv \\
        --project-id 123 \\
        --generate-after-upload \\
        --fetch-results \\
        --output-file results.csv \\
        --poll-interval 5 \\
        --max-poll-interval 600

ARGUMENTS
---------
    filepath                    Path to the CSV file to upload (required)

    --api-token STR             API token for Bearer authentication (required)
                                Can also be set via API_TOKEN env var

    --url STR                   Base URL of the API
                                Default: http://localhost:8000
                                Can also be set via API_URL env var

PROJECT SELECTION (one required)
--------------------------------
    --project-id INT            Project ID to upload to
                                Can also be set via PROJECT_ID env var

    --create-project NAME       Create a new project with the given name
                                Fails if project with same name already exists
                                (unless --continue-if-project-exists is set)

    --continue-if-project-exists
                                When used with --create-project, continue with
                                the existing project instead of failing if a
                                project with the same name already exists

UPLOAD TYPE (mutually exclusive)
--------------------------------
    --notes                     Upload as notes CSV (default behavior)
    --structured-data           Upload as structured data CSV
                                Cannot be used with --generate-after-upload

GENERATION & RESULTS
--------------------
    --generate-after-upload     Start LLM generation after upload completes

    --fetch-results             Poll for generation completion and fetch results
                                Requires: --generate-after-upload and --output-file

    --output-file PATH          Path to save results CSV
                                Required when using --fetch-results

POLLING OPTIONS
---------------
    --poll-interval INT         Initial polling interval in seconds (default: 2)
                                Uses exponential backoff up to max-poll-interval

    --max-poll-interval INT     Maximum polling interval in seconds (default: 300)

ENVIRONMENT VARIABLES
---------------------
    PROJECT_ID                  Default value for --project-id
    API_TOKEN                   Default value for --api-token
    API_URL                     Default value for --url

EXIT CODES
----------
    0                           Success
    1                           Error (invalid arguments, upload failed, generation failed)
    2                           Project already exists (when --create-project used without
                                --continue-if-project-exists)
"""
import argparse
import os
import sys
import time
from pathlib import Path

import requests


# Task status constants matching SummitTask.Status
class TaskStatus:
    WAITING = 0
    RUNNING = 1
    COMPLETE = 2
    ERROR = 3
    STOPPED = 4


def upload_csv(filepath, project_id, api_token, api_url, generate_after_upload):
    """
    Upload a notes CSV file to the API endpoint.

    Args:
        filepath (str): Path to the CSV file to upload
        project_id (int): Project ID to upload to
        api_token (str): API project token for authentication
        api_url (str): Base URL of the API
        generate_after_upload (bool): Start generation after upload.

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
        response = requests.post(endpoint, headers=headers, data=data, files=files)

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


def upload_structured_data(filepath, project_id, api_token, api_url):
    """
    Upload a structured data CSV file to the API endpoint.

    Args:
        filepath (str): Path to the CSV file to upload
        project_id (int): Project ID to upload to
        api_token (str): API project token for authentication
        api_url (str): Base URL of the API

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
        response = requests.post(endpoint, headers=headers, data=data, files=files)

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


def create_project(project_name, api_token, api_url):
    """
    Create a new project via the API.

    Args:
        project_name (str): Name for the new project
        api_token (str): API token for authentication
        api_url (str): Base URL of the API

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
        response = requests.post(endpoint, headers=headers, json=payload)

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
            response = requests.post(endpoint, headers=headers, json=payload)

            if response.status_code == 200:
                result = response.json()
                status = result["data"]["task_status"]
                status_display = result["data"]["task_status_display"]

                print(f"  Status: {status_display} ({status})")

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
):
    """
    Fetch results for a completed task. Creates an export task and polls until complete.

    Args:
        task_id (str): Task ID (generation or upload task)
        project_id (int): Project ID
        api_token (str): API project token for authentication
        api_url (str): Base URL of the API
        output_file (str): Path to save CSV results
        initial_interval (int): Initial polling interval in seconds
        max_interval (int): Maximum polling interval in seconds

    Returns:
        bool: True if successful, False otherwise
    """
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }
    endpoint = f"{api_url.rstrip('/')}/api/v1/results/"

    print(f"Fetching results for task {task_id}...")

    try:
        payload = {"project_id": project_id, "task_id": task_id, "get_csv": True}
        response = requests.post(endpoint, headers=headers, json=payload)
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
            response = requests.post(endpoint, headers=headers, json=poll_payload)
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


def create_parser():
    """Create and return the argument parser for the upload script."""
    parser = argparse.ArgumentParser(
        description="Upload a CSV file to the API (notes or structured data)"
    )
    parser.add_argument("filepath", type=str, help="Path to the CSV file to upload")
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
        default=os.environ.get("API_TOKEN"),
    )
    parser.add_argument(
        "--url",
        type=str,
        help="Base URL of the API",
        default=os.environ.get("API_URL", "http://localhost:8000"),
    )

    # Mutually exclusive upload type group
    upload_type = parser.add_mutually_exclusive_group()
    upload_type.add_argument(
        "--notes",
        action="store_true",
        help="Upload as notes CSV (default behavior)",
    )
    upload_type.add_argument(
        "--structured-data",
        action="store_true",
        help="Upload as structured data CSV",
    )

    parser.add_argument(
        "--generate-after-upload",
        action="store_true",
        help="Start generation after upload completes",
    )
    parser.add_argument(
        "--fetch-results",
        action="store_true",
        help="Poll for completion and fetch results (requires --generate-after-upload)",
    )
    parser.add_argument(
        "--output-file",
        type=str,
        help="Path to save results CSV (used with --fetch-results)",
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

    return parser


def main():
    parser = create_parser()
    args = parser.parse_args()

    # Validate required arguments
    if not args.api_token:
        print(
            "Error: API token is required. "
            "Provide it via --api-token or set API_TOKEN "
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

    # Validate argument combinations
    if args.fetch_results and not args.generate_after_upload:
        print("Error: --fetch-results requires --generate-after-upload")
        sys.exit(1)

    if args.fetch_results and not args.output_file:
        print("Error: --fetch-results requires --output-file")
        sys.exit(1)

    if args.structured_data and args.generate_after_upload:
        print("Error: --structured-data cannot be used with --generate-after-upload")
        sys.exit(1)

    # Normalize filepath
    filepath = str(Path(args.filepath).expanduser().resolve())

    # Determine project_id (either from args or by creating a new project)
    project_id = args.project_id
    if args.create_project:
        project_id, was_created = create_project(
            args.create_project,
            args.api_token,
            args.url,
        )
        if project_id is None:
            sys.exit(1)
        if not was_created and not args.continue_if_project_exists:
            print(
                "Error: Project already exists. "
                "Use --continue-if-project-exists to proceed with existing project."
            )
            sys.exit(2)

    # Perform upload based on type
    if args.structured_data:
        result = upload_structured_data(
            filepath,
            project_id,
            args.api_token,
            args.url,
        )
    else:
        # Default to notes upload (--notes flag or no flag)
        result = upload_csv(
            filepath,
            project_id,
            args.api_token,
            args.url,
            args.generate_after_upload,
        )

    if not result:
        sys.exit(1)

    # Handle fetch-results flow
    if args.fetch_results:
        generation_task_id = result.get("generation_task_id")
        if not generation_task_id:
            print("Error: No generation task ID returned")
            sys.exit(1)

        # Poll until generation complete
        status = poll_task_status(
            generation_task_id,
            project_id,
            args.api_token,
            args.url,
            initial_interval=args.poll_interval,
            max_interval=args.max_poll_interval,
        )

        if status == TaskStatus.COMPLETE:
            print("Generation complete!")
            success = fetch_results(
                generation_task_id,
                project_id,
                args.api_token,
                args.url,
                args.output_file,
                initial_interval=args.poll_interval,
                max_interval=args.max_poll_interval,
            )
            if not success:
                sys.exit(1)
        elif status == TaskStatus.ERROR:
            print("Generation ended with ERROR status")
            sys.exit(1)
        elif status == TaskStatus.STOPPED:
            print("Generation was STOPPED")
            sys.exit(1)
        else:
            print(f"Generation ended with unexpected status: {status}")
            sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
