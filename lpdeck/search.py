"""Search with field filters: ``artist:pallbearer year:2020 "rite of"``.

``field:value`` narrows by one field (quote a value with spaces:
``album:"forgotten days"``); ``year:`` takes a year, a range (``1990-1999``) or a
comparison (``>2010``, ``<=1995``). Any other words must each appear in the
title, artist or album. The same query drives the song, album and artist results,
each using the filters that apply to it.
"""
import re
import shlex

TEXT_FIELDS = ('artist', 'album', 'title', 'genre')
_YEAR_RANGE = re.compile(r'^(\d{4})\s*-\s*(\d{4})$')
_YEAR_CMP = re.compile(r'^(<=|>=|<|>|=)?\s*(\d{4})$')


def _split(q):
    try:
        return shlex.split(q)
    except ValueError:                        # an unbalanced quote: split on spaces
        return q.replace('"', ' ').split()


def parse(q):
    """{'artist': [...], 'album': [...], 'title': [...], 'genre': [...],
    'year': [(op, year), ...], 'words': [...]}"""
    out = {f: [] for f in TEXT_FIELDS}
    out['year'] = []
    out['words'] = []
    for token in _split(q or ''):
        field, sep, value = token.partition(':')
        field = field.lower()
        if sep and value and field in TEXT_FIELDS:
            out[field].append(value)
            continue
        if sep and value and field == 'year':
            rng = _YEAR_RANGE.match(value)
            if rng:
                out['year'] += [('>=', int(rng.group(1))), ('<=', int(rng.group(2)))]
                continue
            cmp_ = _YEAR_CMP.match(value)
            if cmp_:
                out['year'].append((cmp_.group(1) or '=', int(cmp_.group(2))))
                continue
        out['words'].append(token)
    return out


def is_empty(parsed):
    return not any(parsed[k] for k in parsed)


def _like(value):
    return '%' + value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'


def _clauses(parsed, columns, word_columns):
    """(sql, params) ANDing every filter whose column is in `columns`, and each
    free word against any of `word_columns`."""
    parts, params = [], []
    for field in TEXT_FIELDS:
        if field in columns:
            for value in parsed[field]:
                parts.append(f"{columns[field]} LIKE ? ESCAPE '\\'")
                params.append(_like(value))
    if 'year' in columns:
        for op, year in parsed['year']:
            parts.append(f"CAST(NULLIF({columns['year']}, '') AS INTEGER) {op} ?")
            params.append(year)
    for word in parsed['words']:
        parts.append('(' + ' OR '.join(f"{c} LIKE ? ESCAPE '\\'" for c in word_columns) + ')')
        params += [_like(word)] * len(word_columns)
    return (' AND '.join(parts) if parts else '1=1'), params


def song_filter(parsed):
    columns = {'artist': 'ar.name', 'album': 'al.name', 'title': 't.title',
               'genre': 't.genre', 'year': 'al.year'}
    return _clauses(parsed, columns, ('t.title', 'ar.name', 'al.name'))


def album_filter(parsed):
    """None when the query filters on something albums don't have."""
    if parsed['title'] or parsed['genre']:
        return None
    columns = {'artist': 'ar.name', 'album': 'al.name', 'year': 'al.year'}
    return _clauses(parsed, columns, ('al.name', 'ar.name'))


def artist_filter(parsed):
    """None when the query filters on something artists don't have."""
    if parsed['title'] or parsed['genre'] or parsed['album'] or parsed['year']:
        return None
    return _clauses(parsed, {'artist': 'name'}, ('name',))
