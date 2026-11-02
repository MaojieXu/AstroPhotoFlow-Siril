import json
from pathlib import Path

FORMATS = json.loads((Path(__file__).resolve().parents[1] / 'reference/formats.json').read_text(encoding='utf-8'))
