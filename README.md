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

### upload_file_via_api.py

Uploads clinical notes or structured data CSV files to the Brim API, with optional support for creating projects, triggering generation, and fetching results.

**Requirements:**
```bash
pip install requests
```

**Usage:**
```bash
# Upload notes CSV to existing project
python upload_file_via_api.py notes.csv --project-id 123 --api-token YOUR_TOKEN

# Upload to existing project, run generation, and fetch results
python upload_file_via_api.py notes.csv \
    --project-id 123 \
    --api-token YOUR_TOKEN \
    --generate-after-upload \
    --fetch-results \
    --output-file results.csv

# Upload structured data CSV to existing project
python upload_file_via_api.py structured.csv --structured-data --project-id 123 --api-token YOUR_TOKEN

# Create a new project and upload notes to it
python upload_file_via_api.py notes.csv --create-project "My New Project" --api-token YOUR_TOKEN

# Full workflow: create project, upload, generate, fetch results
python upload_file_via_api.py notes.csv \
    --create-project "My Project" \
    --continue-if-project-exists \
    --api-token YOUR_TOKEN \
    --generate-after-upload \
    --fetch-results \
    --output-file results.csv
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `filepath` | Path to the CSV file to upload (required) |
| `--api-token` | API token for Bearer authentication (required, or set `API_TOKEN` env var) |
| `--url` | Base URL of the API (default: `http://localhost:8000`, or set `API_URL` env var) |
| `--project-id` | Project ID to upload to (or set `PROJECT_ID` env var) |
| `--create-project NAME` | Create a new project with the given name |
| `--continue-if-project-exists` | Continue with existing project if name matches |
| `--notes` | Upload as notes CSV (default) |
| `--structured-data` | Upload as structured data CSV |
| `--generate-after-upload` | Start LLM generation after upload completes |
| `--fetch-results` | Poll for completion and fetch results |
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

---

### pg_dump_and_copy.sh

Dumps a PostgreSQL database running inside a Docker container and copies the backup to the host. Old backups are automatically pruned based on a configurable retention period.

**Usage:**
```bash
./pg_dump_and_copy.sh [CONTAINER_NAME] [DB_NAME] [DB_USER] [RETENTION_DAYS]
```

**Arguments:**

| Argument | Default | Description |
|----------|---------|-------------|
| `CONTAINER_NAME` | `brim-db` | Name of the Docker container running PostgreSQL |
| `DB_NAME` | `summit_db` | Name of the database to dump |
| `DB_USER` | `summit-db-user` | PostgreSQL user for the dump |
| `RETENTION_DAYS` | `14` | Number of days to retain old backups |

**Environment Variables:**
- `BACKUP_DIR` - Directory to store dump files (default: `pg_dumps`)

**Set a Crontab:**

The script's defaults are set to run the backup at midnight (system time) each day and purge backups in the `pg_dumps` directory older than 14 days. You may need to use the absolute path for the script in the cron table. If so, ensure the script is executable (`chmod +x /absolute/path/to/pg_dump_and_copy.sh`).

1. Edit the cron table with `crontab -e`.
2. Add line: `0 0 * * * /absolute/path/to/pg_dump_and_copy.sh >> /path/to/logs.txt 2>&1`

---

### pg_restore_from_dump.sh

Restores a pg_dump file into a Docker container, overwriting the existing database. The existing database is dropped and recreated before restoring.

**Usage:**
```bash
./pg_restore_from_dump.sh <DUMP_FILE> [CONTAINER_NAME] [DB_NAME] [DB_USER]
```

**Arguments:**

| Argument | Default | Description |
|----------|---------|-------------|
| `DUMP_FILE` | *(required)* | Path to the `.dump` file to restore |
| `CONTAINER_NAME` | `brim-db` | Name of the Docker container running PostgreSQL |
| `DB_NAME` | `summit_db` | Name of the database to overwrite |
| `DB_USER` | `summit-db-user` | PostgreSQL user for the restore |
