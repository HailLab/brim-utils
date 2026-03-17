import sys
from pathlib import Path

# Add project root to sys.path so tests can import brim_utils and convert_omop_to_brim
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
