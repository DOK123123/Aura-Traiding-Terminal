"""Exact trusted source snapshot from 53097fe, exclusively for offline comparison."""
import hashlib
from pathlib import Path
ROOT=Path(__file__).parent
MODEL_HASH=hashlib.sha256((ROOT/'engine.py').read_bytes()+(ROOT/'rules.json').read_bytes()).hexdigest()
