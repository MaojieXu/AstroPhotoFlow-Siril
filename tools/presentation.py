"""Authored node names and category paths shared by both generators."""
import json


def load_presentation(root, identities):
    source = json.loads((root / 'locales/source.zh.json').read_text(encoding='utf-8'))
    if len(identities) != 160 or len(set(identities)) != 160 or set(source['operations']) != set(identities):
        raise ValueError('Presentation must cover exactly the 160 declared Siril operations.')
    used = set()
    for identity in identities:
        entry = source['operations'][identity]
        if type(entry.get('automatic_result_preview')) is not bool:
            raise ValueError('An explicit automatic result policy is required: ' + identity)
        if not entry['name'].strip() or not entry['name_en'].strip():
            raise ValueError('Both node names are required: ' + identity)
        category = entry['category']
        if len(category) != 2 or any(not part or '/' in part or part != part.strip() for part in category):
            raise ValueError('Siril nodes require exactly two category levels: ' + identity)
        for part in category:
            labels = source['categories'][part]
            if any(not labels[locale].strip() or '/' in labels[locale] for locale in ('en', 'zh')):
                raise ValueError('Both category labels are required: ' + part)
            used.add(part)
    if used != set(source['categories']):
        raise ValueError('Category labels must match the used node categories.')
    return source


def node_name(entry, identity, locale):
    return entry['name'] + '（' + identity + '）' if locale == 'zh' else entry['name_en'] + ' (' + identity + ')'


def category_labels(source, identity, locale):
    return [source['categories'][part][locale] for part in source['operations'][identity]['category']]
