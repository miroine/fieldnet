"""Saved Monte Carlo results: kept with the case file so P10/P50/P90 survive a reload, and compared between runs/cases."""
from __future__ import annotations
import json, time
import pandas as pd

KEY = 'mc_saved'


def _plain(result):
    return json.loads(json.dumps(result, default=str))


def save_result(ss, name, result, note=''):
    name = (name or '').strip() or time.strftime('MC %Y-%m-%d %H:%M')
    store = dict(ss.get(KEY) or {})
    store[name] = {'saved_at': time.strftime('%Y-%m-%d %H:%M:%S'), 'note': note, 'result': _plain(result)}
    ss[KEY] = store
    return name


def delete_result(ss, name):
    store = dict(ss.get(KEY) or {}); store.pop(name, None)
    if store: ss[KEY] = store
    else: ss.pop(KEY, None)


def gather(ss):
    """Saved runs of the working session plus those stored in the other cases of the library, named 'case / run'."""
    out = dict(ss.get(KEY) or {})
    lib = ss.get('case_library')
    for c in (getattr(lib, 'cases', None) or {}).values():
        ex = c.get('extras') or {}
        for n, e in (ex.get(KEY) or {}).items():
            if (ss.get(KEY) or {}).get(n) == e: continue                  # the working copy of the active case
            out[f"{c.get('name', c.get('id'))} / {n}"] = e
        if ex.get('mc_last') and not ex.get(KEY):
            out[f"{c.get('name', c.get('id'))} / last run"] = {'saved_at': c.get('updated', ''), 'result': ex['mc_last']}
    return out


def _row(name, entry):
    r = entry['result']; out = {'Run': name, 'Saved': entry.get('saved_at', ''), 'Samples ok': r.get('successful_samples'), 'Seed': r.get('seed')}
    for m, s in (r.get('metrics') or {}).items():
        for k in ('P90', 'P50', 'P10', 'mean'):
            if k in s: out[f'{m} {k}'] = s[k]
    return out


def compare_table(ss, names=None, metric_filter=None):
    """One row per saved run with P90/P50/P10 for each metric; ``metric_filter`` keeps only metrics containing the text."""
    store = gather(ss)
    rows = [_row(n, e) for n, e in store.items() if names is None or n in names]
    df = pd.DataFrame(rows)
    if metric_filter and not df.empty:
        keep = [c for c in df.columns if c in ('Run', 'Saved', 'Samples ok', 'Seed') or metric_filter.lower() in c.lower()]
        df = df[keep]
    return df


def delta_table(ss, base, other, metric_filter=None):
    """Differences (other - base, and %) of every shared P-value."""
    store = gather(ss)
    a, b = _row(base, store[base]), _row(other, store[other]); rows = []
    for k in a:
        if k in ('Run', 'Saved', 'Samples ok', 'Seed') or k not in b or not isinstance(a[k], (int, float)) or not isinstance(b[k], (int, float)): continue
        if metric_filter and metric_filter.lower() not in k.lower(): continue
        rows.append({'Quantity': k, base: a[k], other: b[k], 'Δ': b[k] - a[k], 'Δ %': (100 * (b[k] - a[k]) / a[k]) if a[k] else None})
    return pd.DataFrame(rows)
