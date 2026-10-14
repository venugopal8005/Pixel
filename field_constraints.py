"""Project OCR alternatives through field types without changing source evidence."""
import json
import re
from pathlib import Path

RULEBOOK = json.loads(Path(__file__).with_name('field_rules.json').read_text(encoding='utf-8'))
RULES = {r['index']: r for r in RULEBOOK['fields']}
GENERATED = {0, 2, 13, 25, 36}
PRINTED = set(range(37)) - GENERATED
DESCRIPTIONS = {'digits': 'Digits only.', 'numeric_identifier': 'Digits and hyphen.',
                'currency': 'Numeric amount.', 'months': 'Whole number of months.',
                'percent': 'Numeric percentage.', 'date': 'Calendar date.',
                'text': 'Text; punctuation is preserved.',
                'mixed': 'Letters, numbers and punctuation are preserved.', 'generated': 'Generated field.'}


def allowed(kind, value):
    # Empty is a real deletion alternative, not evidence that a digit is present.
    if not value:
        return True
    if kind == 'digits':
        return all(c in '0123456789' or c.isspace() for c in value)
    if kind == 'numeric_identifier':
        return all(c in '0123456789-' or c.isspace() for c in value)
    if kind in ('currency', 'percent', 'months', 'numeric_date'):
        punctuation = {'currency': '$,.', 'percent': '.%', 'months': '', 'numeric_date': '/'}[kind]
        return all(c in '0123456789' + punctuation or c.isspace() for c in value)
    if kind == 'text':
        # Punctuation is retained: the manual's String examples contain it.
        return not any(c.isdigit() for c in value)
    return True


def effective_kind(field, plain, offset):
    kind = RULES[field]['kind']
    if kind == 'months':
        suffix = re.search(r'\s+Months\s*$', plain, re.I)
        if suffix and offset >= suffix.start():
            return 'mixed'
    if kind == 'date':
        # Only a complete numeric date gives safe numeric positions. Month and
        # weekday spellings, including misspellings, are never guessed.
        numeric=re.search(r'[0-9OoIl]{1,2}/[0-9OoIl]{1,2}/(?:[0-9OoIl]{4}|[0-9OoIl]{2})$',plain)
        return 'numeric_date' if numeric and offset>=numeric.start() else 'mixed'
    return kind


def constrain_segment(field, segment, decisions, plain='', offset=0):
    """Return field-local evidence; None means preserve the original segment."""
    if segment['id'] in decisions or segment['category'] != 'ambiguous':
        return None
    options = list(dict.fromkeys(segment.get('options', [])))
    if len(options) < 2:
        return None
    kind = effective_kind(field, plain, offset)
    choices = [v for v in options if allowed(kind, v)]
    if choices == options:
        return None
    rule = RULES[field]
    if not choices or choices == ['']:
        return dict(options=options, text=segment['text'], category=segment['category'],
                    resolved=False, conflict=True, original_options=options,
                    reason=f"No nonempty OCR alternative matches the {rule['name']} rule. Inspect the source.")
    resolved = len(choices) == 1
    return dict(options=choices, text=choices[0] if resolved else segment['text'],
                category='single' if resolved else 'ambiguous', resolved=resolved,
                conflict=False, original_options=options,
                reason=f"{rule['name']} rule kept " + ' / '.join(v or '∅' for v in choices) +
                       '. This is rule-assisted, not human-confirmed.')


def project_cell(cell, record, decisions):
    """Only located fields are eligible. Proposed crops stay unlocated."""
    from character_review import render_segments
    from client_rules import join_parts
    field = cell['field']
    cell['field_rule'] = {k: RULES[field][k] for k in ('name', 'kind', 'instruction', 'min_length', 'max_length')}
    cell['field_rule']['description'] = DESCRIPTIONS[RULES[field]['kind']]
    cell['rule_segments'] = {}
    cell['rule_actions'] = []
    cell['rule_conflicts'] = []
    cell['raw_value'] = cell['value']
    if cell['manual'] or cell.get('candidate') or field in GENERATED or not cell.get('parts'):
        return
    segments = {s['id']: s for line in record['lines'] for s in line['segments']}
    plain = ''.join(p['raw'] for p in cell['parts'])
    marked, output, offset = [], [], 0
    for part in cell['parts']:
        segment = segments.get(part.get('id'))
        result = constrain_segment(field, segment, decisions, plain, offset) if segment else None
        if result:
            cell['rule_segments'][segment['id']] = result
            if result['conflict']:
                cell['rule_conflicts'].append(result['reason'])
            else:
                cell['rule_actions'].append(dict(segment=segment['id'], **result))
            effective = dict(segment, **{k: result[k] for k in ('text', 'options', 'category')})
            marked.append(render_segments([effective], decisions))
            output.append(effective['text'])
        else:
            marked.append(part['marked'])
            output.append(part['raw'])
        offset += len(part['raw'])
    cell['value'] = join_parts(field,[dict(text=t,line_break=p.get('line_break',False)) for t,p in zip(marked,cell['parts'])]) or '[?]'
    cell['plain'] = join_parts(field,[dict(text=t,line_break=p.get('line_break',False)) for t,p in zip(output,cell['parts'])])
    cell['pending'] = sum(
        segments[r['id']]['category'] != 'single' and r['id'] not in decisions and
        not cell['rule_segments'].get(r['id'], {}).get('resolved')
        for r in cell['segments'])
    if cell['status'] != 'unmapped':
        cell['status'] = 'uncertain' if cell['pending'] else 'read'


def field_coverage(cells):
    located = [c['field'] for c in cells if c['field'] in PRINTED and c.get('sources') and not c.get('candidate')]
    missing = sorted(PRINTED - set(located))
    return dict(expected=len(PRINTED), located=len(located), missing_fields=missing,
                all_located=not missing,
                note='Located crops are not proof of correct boundaries or transcription.')
