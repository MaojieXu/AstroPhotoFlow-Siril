from pathlib import Path

from adapter import recipes
from adapter import siril as adapter

ROOT = Path(__file__).resolve().parents[1]

def defaults(operation):
    values = {item.schema.name: item.schema.default for item in recipes.RECIPES[operation].parameters}
    return {**values, 'runtime': '{}'}


def build(tmp_path, operation, *, sources=None, values=None, **options):
    work = tmp_path / 'work'
    work.mkdir(exist_ok=True)
    if sources is None:
        source = tmp_path / 'original.fit'
        source.write_bytes(b'protected original')
        sources = {'image': [source]}
    return adapter.build_plan(operation, sources, {**defaults(operation), **(values or {})}, work, **options)


def script(plan):
    return Path(plan.arguments[-1]).read_text(encoding='utf-8')
