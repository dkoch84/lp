"""Smart playlists you define: rules turned into a library query.

A definition is plain data, stored as JSON::

    {"match": "all" | "any",
     "rules": [{"field": "genre", "op": "contains", "value": "doom"}, ...],
     "sort": "artist", "limit": 100}

Every field, operator and sort maps to a fixed piece of SQL here, and values are
always passed as parameters, so a stored definition can't inject anything.
Rules that don't make sense (unknown field, wrong operator for the field, a
value that isn't a number where one is needed) are ignored rather than failing
the whole list.
"""
import time

TEXT_FIELDS = {
    'artist': 'ar.name',
    'album': 'al.name',
    'title': 't.title',
    'genre': 't.genre',
}
NUMBER_FIELDS = {
    'year': "CAST(NULLIF(al.year, '') AS INTEGER)",
    'rating': 't.rating',
    'plays': 't.play_count',
    'length': 't.duration',          # seconds
}
DATE_FIELDS = {
    'added': 't.added_at',
    'last_played': 't.last_played',
}
BOOL_FIELDS = {
    'favorite': 't.favorite',
}

TEXT_OPS = ('contains', 'not_contains', 'is', 'is_not', 'starts_with')
NUMBER_OPS = {'=': '=', '!=': '!=', '<': '<', '<=': '<=', '>': '>', '>=': '>='}
DATE_OPS = ('in_last_days', 'not_in_last_days', 'never')
BOOL_OPS = ('is_true', 'is_false')

SORTS = {
    'artist': 'ar.sort_name, al.year, al.name, t.disc_no, t.track_no',
    'title': 't.title COLLATE NOCASE',
    'year': "al.year DESC, ar.sort_name, t.track_no",
    'added': 't.added_at DESC',
    'played': 't.last_played DESC',
    'plays': 't.play_count DESC, t.last_played DESC',
    'rating': 't.rating DESC, t.play_count DESC',
    'random': 'RANDOM()',
}

def _escape_like(value):
    return value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


def _rule_sql(rule, now):
    """(sql, params) for one rule, or None to ignore it."""
    field, op, value = rule.get('field'), rule.get('op'), rule.get('value')
    if field in TEXT_FIELDS and op in TEXT_OPS and isinstance(value, str):
        col = TEXT_FIELDS[field]
        if op == 'contains':
            return f"{col} LIKE ? ESCAPE '\\'", [f"%{_escape_like(value)}%"]
        if op == 'not_contains':
            return f"{col} NOT LIKE ? ESCAPE '\\'", [f"%{_escape_like(value)}%"]
        if op == 'starts_with':
            return f"{col} LIKE ? ESCAPE '\\'", [f"{_escape_like(value)}%"]
        if op == 'is':
            return f"{col} = ? COLLATE NOCASE", [value]
        return f"{col} != ? COLLATE NOCASE", [value]
    if field in NUMBER_FIELDS and op in NUMBER_OPS:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return f"{NUMBER_FIELDS[field]} {NUMBER_OPS[op]} ?", [number]
    if field in DATE_FIELDS and op in DATE_OPS:
        col = DATE_FIELDS[field]
        if op == 'never':
            return f"{col} = 0", []
        try:
            since = now - float(value) * 86400
        except (TypeError, ValueError):
            return None
        if op == 'in_last_days':
            return f"{col} >= ?", [since]
        return f"({col} < ? OR {col} = 0)", [since]
    if field in BOOL_FIELDS and op in BOOL_OPS:
        return f"{BOOL_FIELDS[field]} = ?", [1 if op == 'is_true' else 0]
    return None


def build_query(definition, now=None):
    """(where, params, order, limit) for a definition. With no usable rules the
    list is every available track, in the chosen order."""
    now = time.time() if now is None else now
    parts, params = [], []
    for rule in definition.get('rules') or []:
        if isinstance(rule, dict):
            built = _rule_sql(rule, now)
            if built:
                parts.append(f"({built[0]})")
                params.extend(built[1])
    joiner = ' OR ' if definition.get('match') == 'any' else ' AND '
    where = joiner.join(parts) if parts else '1=1'
    order = SORTS.get(definition.get('sort'), SORTS['artist'])
    try:
        limit = max(1, min(10000, int(definition.get('limit') or 10000)))
    except (TypeError, ValueError):
        limit = 10000
    return where, params, order, limit


def normalize(definition):
    """A cleaned copy with only known keys, rules and values, for storing."""
    rules = []
    for rule in definition.get('rules') or []:
        if isinstance(rule, dict) and _rule_sql(rule, time.time()) is not None:
            rules.append({'field': rule['field'], 'op': rule['op'], 'value': rule.get('value')})
    out = {'match': 'any' if definition.get('match') == 'any' else 'all',
           'rules': rules,
           'sort': definition.get('sort') if definition.get('sort') in SORTS else 'artist'}
    try:
        if definition.get('limit'):
            out['limit'] = max(1, min(10000, int(definition['limit'])))
    except (TypeError, ValueError):
        pass
    return out
