from __future__ import annotations

import re
from pathlib import Path

from astrophotoflow.contracts.bundles import (
    BundleProgress,
)


def parse_progress(text: str) -> BundleProgress:
    result = BundleProgress()
    text = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', text).replace('\r', '\n')
    for line in text.splitlines():
        command = re.match(r'log: Running command: (\S+)', line)
        progress = re.match(r'progress:\s*(?:(.*),\s*)?([\d.]+)%\s*$', line)
        if command:
            result = BundleProgress(phase=command[1])
        elif progress:
            value = float(progress[2]) / 100
            if not 0 <= value <= 1:
                raise ValueError('Siril reported an invalid progress value.')
            result = BundleProgress(phase=progress[1] or result.phase, progress=value)
    return result


def parse_failure(log_path: Path) -> str:
    lines = Path(log_path).read_text(encoding='utf-8', errors='replace').splitlines()
    errors = [re.sub(r'<[^>]+>', '', line.removeprefix('log: ')) for line in lines
              if re.search(r'error|failed|cannot|could not|must be|not available|not found|missing', line, re.IGNORECASE)]
    return '\n'.join(errors[-6:])[-2400:] if errors else '\n'.join(lines[-8:])[-2400:] or 'Siril exited without an error message.'
