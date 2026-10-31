"""Build display-only translations without changing executable declarations."""
import json
import re
import runpy
from pathlib import Path

from astrophotoflow.contracts.localization import CapabilityDisplay


ROOT = Path(__file__).resolve().parents[1]
PRESENTATION = runpy.run_path(str(Path(__file__).with_name('presentation.py')))


def parameter_label(name, source):
    if name.startswith('use_'):
        return '启用' + parameter_label(name[4:], source)
    if re.fullmatch(r'm[0-2][0-2]', name):
        return f'矩阵第 {int(name[1]) + 1} 行第 {int(name[2]) + 1} 列'
    return source['parameters'][name]


def parameter_help(parameter, locale):
    zh = locale == 'zh'
    value = json.dumps(parameter['default'], ensure_ascii=False)
    parts = [('类型：' if zh else 'Type: ') + parameter['kind'],
             ('控件初值：' if zh else 'Widget initial value: ') + value]
    for field, label in [('minimum', '最小值'), ('maximum', '最大值'), ('step', '步长'), ('choices', '选项')]:
        if parameter.get(field) is not None:
            parts.append((label if zh else field) + ': ' + json.dumps(parameter[field], ensure_ascii=False))
    if parameter['name'].startswith('use_'):
        parts.append('仅勾选时发送对应可选参数，零值仍为有效值。' if zh else 'Send the optional argument only when enabled; zero remains valid.')
    if parameter['name'] == 'runtime':
        parts.append('JSON 对象；支持 ini、settings、threads、memory_ratio、output_bits、compression、online、selection、findstar、photometry。默认离线，联网须显式启用。' if zh else
                     'JSON object. Keys: ini, settings, threads, memory_ratio, output_bits, compression, online, selection, findstar, photometry. Networking is offline unless explicitly enabled.')
    return ' · '.join(parts)


def main():
    manifest = json.loads((ROOT / 'bundle.json').read_text(encoding='utf-8'))
    entries = [json.loads((ROOT / name).read_text(encoding='utf-8')) for name in manifest['operations']]
    source = PRESENTATION['load_presentation'](ROOT, [entry['operation']['operation_id'] for entry in entries])
    values = {'en': {}, 'zh': {}}
    for entry in entries:
        operation = entry['operation']
        identity = operation['operation_id']
        notes = [note for section in ('limitations', 'dependencies', 'corrections') for note in entry.get(section, [])]
        for locale in values:
            zh = locale == 'zh'
            translated = source['operations'][identity]
            name = PRESENTATION['node_name'](translated, identity, locale)
            description = translated['description'] if zh else operation['description']
            help_text = entry['help'] if not zh else '\n\n'.join([
                description, *(source['notes'][note] for note in notes),
                '使用固定输入引用，只写入本次调用目录。可选参数仅在 use_* 控制启用时发送，零值保留。控件初值不代表省略参数时的 Siril 默认值。',
                'selection 省略表示全图，显式 null 清除选择。运行配置 runtime 为 JSON；默认离线，联网须显式启用。',
                '允许自动结果计算的处理与分析操作可作为本次执行目标，无需额外导出节点；手动运行仍使用明确的导出、叠加或分析终点。只执行所请求的依赖。保存引用指向完整且已检查的文件，不是预览像素。',
                '命令与标识符保持原文。详见 reference/coverage.json 和 docs/usage.md。'])
            display = dict(name=name, category=PRESENTATION['category_labels'](source, identity, locale),
                description=description, help=help_text,
                parameters={parameter['name']: dict(label=parameter_label(parameter['name'], source) if zh else parameter['name'].replace('_', ' '),
                    description=parameter_help(parameter, locale)) for parameter in operation['parameters']},
                **{section: {port['name']: dict(label=source['ports'][port['name']] if zh else port['name'].replace('_', ' '),
                    description=('端口类型：' if zh else 'Port type: ') + port['type']) for port in operation[section]} for section in ('inputs', 'outputs')})
            values[locale][identity] = CapabilityDisplay.model_validate(display).model_dump(mode='json')
    for locale, catalog in values.items():
        (ROOT / 'locales' / (locale + '.json')).write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(f'Built {len(entries)} operation/node translations in each of en and zh.')


if __name__ == '__main__':
    main()
