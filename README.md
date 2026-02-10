# Brim Utils

Utilities for working with the Brim API.

## Scripts

### convert_omop_to_brim.py

Converts OMOP CDM v5.4 note data to Brim's upload format, enriching notes with information from related tables. Supports both local file storage and Azure Blob Storage.

**Requirements:**
```bash
pip install pandas

# For Azure Blob Storage support (optional):
pip install azure-storage-blob azure-identity
```

**Usage:**
```bash
# Local storage - output filename auto-generated as {dirname}_notes.csv
python convert_omop_to_brim.py --input-dir /path/to/myfolder

# Local storage with explicit output file
python convert_omop_to_brim.py \
    --input-dir /path/to/cdm/data \
    --output-file /path/to/output/output_notes.csv

# Azure Blob Storage input (auto-detected by URL pattern)
python convert_omop_to_brim.py \
    --input-dir https://account.blob.core.windows.net/container/myfolder

# Skip enrichment
python convert_omop_to_brim.py \
    --input-dir /path/to/cdm/data \
    --do-not-enrich
```

**Input Files:**
- Required: `note.csv`
- Optional (for enrichment): `provider.csv`, `person.csv`, `visit_occurrence.csv`

**Azure Authentication:**

Azure Blob Storage uses `DefaultAzureCredential` which tries (in order):
1. Environment variables (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_SECRET`)
2. Managed Identity (when running in Azure)
3. Azure CLI credentials (`az login`)
4. Azure PowerShell credentials
5. Interactive browser login

Run `az login` before using Azure Blob Storage for local development.

---

### brim_utils.py

Project setup, user management, and data upload via the Brim API. Supports creating projects, inviting users, and optionally uploading clinical notes or structured data CSV files with generation and result fetching.

**Requirements:**
```bash
pip install requests
```

**Usage:**
```bash
# Create a project and invite users (no upload)
python brim_utils.py \
    --create-project "My Project" \
    --users-to-add "user1@example.com,user2@example.com" \
    --api-token YOUR_TOKEN

# Create a project and invite users with upload permission
python brim_utils.py \
    --create-project "My Project" \
    --users-to-add "user1@example.com,user2@example.com" \
    --can-upload-permission \
    --api-token YOUR_TOKEN

# Upload notes CSV to existing project
python brim_utils.py --csv-file notes.csv --project-id 123 --api-token YOUR_TOKEN

# Upload to existing project, run generation, and fetch results
python brim_utils.py --csv-file notes.csv \
    --project-id 123 \
    --api-token YOUR_TOKEN \
    --generate-after-upload \
    --fetch-results \
    --output-file results.csv

# Upload structured data CSV to existing project
python brim_utils.py --csv-file structured.csv --structured-data --project-id 123 --api-token YOUR_TOKEN

# Create a new project and upload notes to it
python brim_utils.py --csv-file notes.csv --create-project "My New Project" --api-token YOUR_TOKEN

# Full workflow: create project, invite users, upload, generate, fetch results
python brim_utils.py --csv-file notes.csv \
    --create-project "My Project" \
    --continue-if-project-exists \
    --users-to-add "user1@example.com" \
    --api-token YOUR_TOKEN \
    --generate-after-upload \
    --fetch-results \
    --output-file results.csv
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `--csv-file PATH` | Path to the CSV file to upload (optional) |
| `--api-token` | API token for Bearer authentication (required, or set `API_TOKEN` env var) |
| `--url` | Base URL of the API (default: `http://localhost:8000`, or set `API_URL` env var) |
| `--project-id` | Project ID to use (or set `PROJECT_ID` env var) |
| `--create-project NAME` | Create a new project with the given name |
| `--continue-if-project-exists` | Continue with existing project if name matches |
| `--users-to-add EMAILS` | Comma-separated list of email addresses to invite to the project |
| `--can-upload-permission` | Grant upload permission to invited users |
| `--notes` | Upload as notes CSV (default when `--csv-file` is provided) |
| `--structured-data` | Upload as structured data CSV |
| `--generate-after-upload` | Start LLM generation after upload completes (requires `--csv-file`) |
| `--fetch-results` | Poll for completion and fetch results (requires `--generate-after-upload` and `--output-file`) |
| `--output-file PATH` | Path to save results CSV |
| `--poll-interval` | Initial polling interval in seconds (default: 2) |
| `--max-poll-interval` | Maximum polling interval in seconds (default: 300) |

**Environment Variables:**
- `API_TOKEN` - Default value for `--api-token`
- `API_URL` - Default value for `--url`
- `PROJECT_ID` - Default value for `--project-id`

**Exit Codes:**
- `0` - Success
- `1` - Error (invalid arguments, upload failed, generation failed)
- `2` - Project already exists (when using `--create-project` without `--continue-if-project-exists`)
