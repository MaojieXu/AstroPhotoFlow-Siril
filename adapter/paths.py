from __future__ import annotations


def inside(directory, path):
    resolved = (directory / path).resolve()
    if not resolved.is_relative_to(directory.resolve()):
        raise ValueError('Output paths must stay inside this invocation.')
    return resolved
