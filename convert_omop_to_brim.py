#!/usr/bin/env python
"""
OMOP CDM to Brim CSV Converter

Converts OMOP CDM v5.4 note data to Brim's upload format,
enriching notes with information from related tables.

Supports both local file storage and Azure Blob Storage.

REQUIREMENTS
------------
    pip install pandas

    # For Azure Blob Storage support (optional):
    pip install azure-storage-blob azure-identity

USAGE
-----
    # Local storage - output filename auto-generated as {dirname}_notes.csv
    python scripts/convert_omop_to_brim.py --input-dir /path/to/myfolder
    # -> outputs: myfolder_notes.csv

    # Local storage with explicit output file
    python scripts/convert_omop_to_brim.py \\
        --input-dir /path/to/cdm/data \\
        --output-file /path/to/output/output_notes.csv

    # Azure Blob Storage input (auto-detected by URL pattern)
    python scripts/convert_omop_to_brim.py \\
        --input-dir https://account.blob.core.windows.net/container/myfolder
    # -> outputs: myfolder_notes.csv

    # Azure Blob Storage output
    python scripts/convert_omop_to_brim.py \\
        --input-dir /path/to/cdm/data \\
        --output-file https://account.blob.core.windows.net/container/path/output.csv

    # Both input and output in Azure Blob Storage
    python scripts/convert_omop_to_brim.py \\
        --input-dir https://account.blob.core.windows.net/container/input/data \\
        --output-file https://account.blob.core.windows.net/container/output/notes.csv

    # Skip enrichment
    python scripts/convert_omop_to_brim.py \\
        --input-dir /path/to/cdm/data \\
        --do-not-enrich

AZURE AUTHENTICATION
--------------------
    Azure Blob Storage uses DefaultAzureCredential which tries (in order):
    1. Environment variables (AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_CLIENT_SECRET)
    2. Managed Identity (when running in Azure)
    3. Azure CLI credentials (az login)
    4. Azure PowerShell credentials
    5. Interactive browser login

    Run 'az login' before using Azure Blob Storage for local development.

AZURE PERMISSIONS
-----------------
    Your Azure identity needs the "Storage Blob Data Reader" role (or "Storage Blob
    Data Contributor" if writing output to Azure) on the storage account.

    To assign the role:

    1. Get your user's object ID:
       az ad signed-in-user show --query id -o tsv

    2. Assign the role (replace <values> with your actual values):
       az role assignment create \\
           --assignee <user-object-id> \\
           --role "Storage Blob Data Contributor" \\
           --scope "/subscriptions/<subscription-id>/resourceGroups/<resource-group>\\
                    /providers/Microsoft.Storage/storageAccounts/<storage-account>"

    3. Wait 5-10 minutes for RBAC propagation, then re-login:
       az account clear
       az login

    4. Verify OAuth access works:
       az storage blob list \\
           --account-name <storage-account> \\
           --container-name <container> \\
           --auth-mode login

INPUT FILES
-----------
    Required: note.csv
    Optional (for enrichment): provider.csv, person.csv, visit_occurrence.csv
"""

import argparse
import logging
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

# Optional Azure dependencies
try:
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobServiceClient

    AZURE_AVAILABLE = True
except ImportError:
    AZURE_AVAILABLE = False

logger = logging.getLogger(__name__)


def is_azure_blob_url(path: str) -> bool:
    """Check if the path is an Azure Blob Storage URL."""
    if not path.startswith("https://"):
        return False
    parsed = urlparse(path)
    return parsed.netloc.endswith(".blob.core.windows.net")


def parse_azure_blob_url(url: str) -> tuple[str, str, str]:
    """
    Parse an Azure Blob Storage URL into components.

    Args:
        url: Azure Blob URL like https://account.blob.core.windows.net/container/path

    Returns:
        tuple: (account_url, container_name, blob_prefix)
    """
    parsed = urlparse(url)
    account_url = f"{parsed.scheme}://{parsed.netloc}"

    # Path starts with /, split into container and prefix
    path_parts = parsed.path.lstrip("/").split("/", 1)
    container_name = path_parts[0]
    blob_prefix = path_parts[1] if len(path_parts) > 1 else ""

    return account_url, container_name, blob_prefix


def download_azure_blobs_to_temp(
    url: str, filenames: list[str]
) -> tuple[Path, list[str]]:
    """
    Download specific files from Azure Blob Storage to a temp directory.

    Args:
        url: Azure Blob Storage URL (container/prefix)
        filenames: List of filenames to download (e.g., ['note.csv', 'person.csv'])

    Returns:
        tuple: (temp_dir_path, list of downloaded filenames)
    """
    if not AZURE_AVAILABLE:
        logger.error(
            "Azure Blob Storage support requires azure-storage-blob and azure-identity packages. "
            "Install with: pip install azure-storage-blob azure-identity"
        )
        sys.exit(1)

    account_url, container_name, blob_prefix = parse_azure_blob_url(url)

    print(f"Connecting to Azure Blob Storage: {account_url}")
    print(f"Container: {container_name}, Prefix: {blob_prefix}")

    # Create temp directory
    temp_dir = Path(tempfile.mkdtemp(prefix="omop_convert_"))
    logger.debug(f"Created temp directory: {temp_dir}")

    # Connect using DefaultAzureCredential
    credential = DefaultAzureCredential()
    blob_service_client = BlobServiceClient(account_url, credential=credential)
    container_client = blob_service_client.get_container_client(container_name)

    downloaded = []
    for filename in filenames:
        # Build full blob path
        if blob_prefix:
            blob_name = f"{blob_prefix}/{filename}"
        else:
            blob_name = filename

        blob_client = container_client.get_blob_client(blob_name)

        try:
            # Check if blob exists and download
            local_path = temp_dir / filename
            print(f"Downloading {blob_name} -> {local_path}")

            with open(local_path, "wb") as f:
                download_stream = blob_client.download_blob()
                f.write(download_stream.readall())

            downloaded.append(filename)
            print(f"Downloaded {filename}")

        except Exception as e:
            # File doesn't exist or other error - this is OK for optional files
            logger.warning(f"{filename} not found in Azure Blob Storage: {e}")

    return temp_dir, downloaded


def upload_file_to_azure(local_path: Path, azure_url: str) -> bool:
    """
    Upload a local file to Azure Blob Storage.

    Args:
        local_path: Path to local file to upload
        azure_url: Full Azure Blob URL
            (e.g., https://account.blob.core.windows.net/container/path/file.csv)

    Returns:
        bool: True if successful, False otherwise
    """
    if not AZURE_AVAILABLE:
        logger.error(
            "Azure Blob Storage support requires azure-storage-blob and azure-identity packages. "
            "Install with: pip install azure-storage-blob azure-identity"
        )
        return False

    account_url, container_name, blob_path = parse_azure_blob_url(azure_url)

    print(f"Uploading to Azure Blob Storage: {azure_url}")

    try:
        credential = DefaultAzureCredential()
        blob_service_client = BlobServiceClient(account_url, credential=credential)
        blob_client = blob_service_client.get_blob_client(
            container=container_name, blob=blob_path
        )

        with open(local_path, "rb") as f:
            blob_client.upload_blob(f, overwrite=True)

        logger.debug(f"Successfully uploaded to {azure_url}")
        return True

    except Exception as e:
        logger.error(f"Failed to upload to Azure Blob Storage: {e}")
        return False


def load_csv_if_exists(input_dir: Path, filename: str) -> pd.DataFrame | None:
    """Load a CSV file if it exists and is not empty, return None otherwise."""
    filepath = input_dir / filename
    if filepath.exists():
        # Check if file is empty or has no data
        if filepath.stat().st_size == 0:
            logger.warning(f"{filename} is empty, skipping")
            return None
        try:
            logger.debug(f"Loading {filename}")
            df = pd.read_csv(filepath, low_memory=False)
            if df.empty:
                logger.warning(f"{filename} has no data rows, skipping")
                return None
            return df
        except pd.errors.EmptyDataError:
            logger.warning(f"{filename} has no columns to parse, skipping")
            return None
    else:
        logger.warning(f"{filename} not found, skipping")
        return None


def _normalize_id(value) -> str:
    """Normalize an ID value to a string key, stripping trailing .0 from floats."""
    s = str(value)
    if s.endswith(".0"):
        s = s[:-2]
    return s


def build_provider_lookup(provider_df: pd.DataFrame | None) -> dict:
    """Build a lookup dictionary for provider information."""
    if provider_df is None:
        return {}

    lookup = {}
    for _, row in provider_df.iterrows():
        provider_id = row.get("provider_id")
        if pd.notna(provider_id):
            lookup[_normalize_id(provider_id)] = {
                "provider_name": row.get("provider_name"),
                "specialty_source_value": row.get("specialty_source_value"),
            }
    return lookup


def build_person_lookup(person_df: pd.DataFrame | None) -> dict:
    """Build a lookup dictionary for person information."""
    if person_df is None:
        return {}

    lookup = {}
    for _, row in person_df.iterrows():
        person_id = row.get("person_id")
        if pd.notna(person_id):
            lookup[_normalize_id(person_id)] = {
                "year_of_birth": row.get("year_of_birth"),
                "gender_source_value": row.get("gender_source_value"),
                "race_source_value": row.get("race_source_value"),
            }
    return lookup


def build_visit_lookup(visit_df: pd.DataFrame | None) -> dict:
    """Build a lookup dictionary for visit information."""
    if visit_df is None:
        return {}

    lookup = {}
    for _, row in visit_df.iterrows():
        visit_id = row.get("visit_occurrence_id")
        if pd.notna(visit_id):
            lookup[_normalize_id(visit_id)] = {
                "visit_start_date": row.get("visit_start_date"),
                "visit_end_date": row.get("visit_end_date"),
                "visit_source_value": row.get("visit_source_value"),
            }
    return lookup


def format_datetime(note_datetime, note_date) -> str:
    """Format datetime, using note_date as fallback."""
    if pd.notna(note_datetime):
        dt_str = str(note_datetime)
        # If already has time component, return as-is (normalize format)
        if " " in dt_str or "T" in dt_str:
            # Normalize ISO format to space-separated
            dt_str = dt_str.replace("T", " ")
            # Ensure we have at least HH:MM:SS
            if len(dt_str.split(" ")[1].split(":")) < 3:
                dt_str = dt_str.split(" ")[0] + " " + dt_str.split(" ")[1] + ":00"
            return dt_str[:19]  # Trim to YYYY-MM-DD HH:MM:SS
        else:
            # Date only, add time
            return f"{dt_str} 00:00:00"
    elif pd.notna(note_date):
        return f"{note_date} 00:00:00"
    else:
        return ""


def build_enrichment_header(
    note_row: pd.Series,
    provider_lookup: dict,
    person_lookup: dict,
    visit_lookup: dict,
) -> str:
    """Build the enrichment header block for a note."""
    lines = []

    # Provider info
    provider_id = note_row.get("provider_id")
    if pd.notna(provider_id) and _normalize_id(provider_id) in provider_lookup:
        provider_info = provider_lookup[_normalize_id(provider_id)]
        if pd.notna(provider_info.get("provider_name")):
            lines.append(f"Provider: {provider_info['provider_name']}")
        if pd.notna(provider_info.get("specialty_source_value")):
            lines.append(
                f"Provider Specialty: {provider_info['specialty_source_value']}"
            )

    # Person info
    person_id = note_row.get("person_id")
    if pd.notna(person_id) and _normalize_id(person_id) in person_lookup:
        person_info = person_lookup[_normalize_id(person_id)]
        if pd.notna(person_info.get("year_of_birth")):
            lines.append(f"Patient Year of Birth: {int(person_info['year_of_birth'])}")
        if pd.notna(person_info.get("gender_source_value")):
            lines.append(f"Patient Gender: {person_info['gender_source_value']}")
        if pd.notna(person_info.get("race_source_value")):
            lines.append(f"Patient Race: {person_info['race_source_value']}")

    # Visit info
    visit_id = note_row.get("visit_occurrence_id")
    if pd.notna(visit_id) and _normalize_id(visit_id) in visit_lookup:
        visit_info = visit_lookup[_normalize_id(visit_id)]
        if pd.notna(visit_info.get("visit_start_date")):
            lines.append(f"Visit Start Date: {visit_info['visit_start_date']}")
        if pd.notna(visit_info.get("visit_end_date")):
            lines.append(f"Visit End Date: {visit_info['visit_end_date']}")
        if pd.notna(visit_info.get("visit_source_value")):
            lines.append(f"Visit Type: {visit_info['visit_source_value']}")

    if lines:
        return "\n".join(lines) + "\n\n"
    return ""


def escape_csv_value(value: str) -> str:
    """Escape a value for CSV output (double quotes → "")."""
    if pd.isna(value):
        return ""
    return str(value).replace('"', '""')


def convert_omop_to_brim(input_dir: Path, output_file: Path, enrich: bool = True):
    """
    Convert OMOP CDM note data to Brim's upload format.

    Args:
        input_dir: Path to directory containing OMOP CDM CSV files
        output_file: Path for output Brim-format CSV
        enrich: If True, prepend header with provider/person/visit info to NOTE_TEXT
    """
    # Load required note.csv
    note_df = load_csv_if_exists(input_dir, "note.csv")
    if note_df is None:
        logger.error("note.csv is required but not found in input directory")
        sys.exit(1)

    logger.debug(f"Loaded {len(note_df)} notes from note.csv")

    # Load optional related CSVs for enrichment
    provider_lookup = {}
    person_lookup = {}
    visit_lookup = {}

    if enrich:
        provider_df = load_csv_if_exists(input_dir, "provider.csv")
        person_df = load_csv_if_exists(input_dir, "person.csv")
        visit_df = load_csv_if_exists(input_dir, "visit_occurrence.csv")

        provider_lookup = build_provider_lookup(provider_df)
        person_lookup = build_person_lookup(person_df)
        visit_lookup = build_visit_lookup(visit_df)

        logger.debug(
            f"Built lookups: {len(provider_lookup)} providers, "
            f"{len(person_lookup)} persons, {len(visit_lookup)} visits"
        )

    # Process notes and build output
    output_rows = []
    for _, note_row in note_df.iterrows():
        # Map core fields
        note_id = note_row.get("note_id", "")
        person_id = note_row.get("person_id", "")
        note_datetime = format_datetime(
            note_row.get("note_datetime"), note_row.get("note_date")
        )
        note_text = note_row.get("note_text", "")
        note_title = note_row.get("note_title", "")

        # Handle NaN values
        if pd.isna(note_id):
            note_id = ""
        if pd.isna(person_id):
            person_id = ""
        if pd.isna(note_text):
            note_text = ""
        if pd.isna(note_title) or str(note_title).strip() == "":
            note_title = "Unknown title"

        # Build enrichment header if enabled
        if enrich:
            header = build_enrichment_header(
                note_row,
                provider_lookup,
                person_lookup,
                visit_lookup,
            )
            note_text = header + str(note_text)

        output_rows.append(
            {
                "NOTE_ID": note_id,
                "PERSON_ID": person_id,
                "NOTE_DATETIME": note_datetime,
                "NOTE_TEXT": note_text,
                "NOTE_TITLE": note_title,
            }
        )

    # Create output dataframe and write to CSV
    output_df = pd.DataFrame(output_rows)

    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Write with proper escaping
    output_df.to_csv(
        output_file,
        index=False,
        quoting=1,  # csv.QUOTE_ALL - quote all fields
        doublequote=True,  # Escape quotes with double quotes
    )

    logger.debug(f"Wrote {len(output_df)} notes to {output_file}")


def get_input_dir_name(input_path: str) -> str:
    """
    Extract the directory name from an input path (local or Azure URL).

    Args:
        input_path: Local path or Azure Blob URL

    Returns:
        str: The directory name (e.g., 'myfolder' from '/path/to/myfolder/')
    """
    if is_azure_blob_url(input_path):
        # For Azure URLs, get the last path component
        _, _, blob_prefix = parse_azure_blob_url(input_path)
        # Remove trailing slash and get last component
        parts = blob_prefix.rstrip("/").split("/")
        return parts[-1] if parts and parts[-1] else "output"
    else:
        # For local paths
        path = Path(input_path)
        return path.name if path.name else "output"


def main():
    parser = argparse.ArgumentParser(
        description="Convert OMOP CDM note data to Brim's upload format"
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        required=True,
        help="Path to folder containing OMOP CDM CSV files (local path or Azure Blob URL)",
    )
    parser.add_argument(
        "--output-file",
        type=str,
        default=None,
        help=(
            "Path for output Brim-format CSV (local path or Azure Blob URL). "
            "If not provided, defaults to {input_dir_name}_notes.csv"
        ),
    )
    parser.add_argument(
        "--do-not-enrich",
        action="store_true",
        help="Skip prepending header with provider/person/visit info to NOTE_TEXT",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose debug logging",
    )

    args = parser.parse_args()

    # Configure logging based on --debug flag
    log_level = logging.DEBUG if args.debug else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(levelname)s - %(message)s",
    )

    enrich = not args.do_not_enrich
    logger.info(f"Enrichment {'disabled' if not enrich else 'enabled'}")

    # Auto-generate output filename if not provided
    if args.output_file is None:
        dir_name = get_input_dir_name(args.input_dir)
        args.output_file = f"{dir_name}_notes.csv"
        print(f"Auto-generated output filename: {args.output_file}")

    # Determine input source (local or Azure)
    input_is_azure = is_azure_blob_url(args.input_dir)
    output_is_azure = is_azure_blob_url(args.output_file)

    temp_dir = None
    try:
        if input_is_azure:
            # Download files from Azure to temp directory
            required_files = ["note.csv"]
            optional_files = [
                "provider.csv",
                "person.csv",
                "visit_occurrence.csv",
            ]
            all_files = required_files + (optional_files if enrich else [])

            temp_dir, downloaded = download_azure_blobs_to_temp(
                args.input_dir, all_files
            )
            input_dir = temp_dir

            if "note.csv" not in downloaded:
                logger.error("note.csv is required but not found in Azure Blob Storage")
                sys.exit(1)
        else:
            # Local input
            input_dir = Path(args.input_dir)

            if not input_dir.exists():
                logger.error(f"Input directory does not exist: {input_dir}")
                sys.exit(1)

            if not input_dir.is_dir():
                logger.error(f"Input path is not a directory: {input_dir}")
                sys.exit(1)

        # Determine output path
        if output_is_azure:
            # Write to temp file, then upload to Azure
            temp_output = Path(tempfile.mktemp(suffix=".csv", prefix="brim_output_"))
            output_file = temp_output
        else:
            output_file = Path(args.output_file)

        # Run conversion
        convert_omop_to_brim(input_dir, output_file, enrich=enrich)

        # Upload to Azure if needed
        if output_is_azure:
            success = upload_file_to_azure(output_file, args.output_file)
            # Clean up temp output file
            output_file.unlink()
            if not success:
                sys.exit(1)
            print(f"Output written to: {args.output_file}")
        else:
            print(f"Output written to: {output_file}")

    finally:
        # Clean up temp directory if we created one
        if temp_dir is not None:
            import shutil

            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.debug(f"Cleaned up temp directory: {temp_dir}")


if __name__ == "__main__":
    main()
