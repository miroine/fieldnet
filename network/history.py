"""Undo / redo of model edits. Snapshots of (nodes, edges) are recorded whenever the model fingerprint changes (property-panel edits, canvas
changes, deletions); undo restores the previous snapshot. Pure functions over a session-state-like mapping so they are testable without Streamlit."""
from __future__ import annotations
import copy

KEY = '_model_history'
LIMIT = 30


def _h(ss):
    h = ss.get(KEY)
    if not isinstance(h, dict): h = {'stack': [], 'idx': -1}; ss[KEY] = h
    return h


def record(ss, fp, nodes, edges):
    """Remember the model when its fingerprint ``fp`` differs from the current history entry. Returns True when a snapshot was added."""
    h = _h(ss)
    if h['idx'] >= 0 and h['stack'][h['idx']]['fp'] == fp: return False
    del h['stack'][h['idx'] + 1:]                                       # a new edit discards the redo branch
    h['stack'].append({'fp': fp, 'nodes': copy.deepcopy(nodes), 'edges': copy.deepcopy(edges)})
    if len(h['stack']) > LIMIT: del h['stack'][0:len(h['stack']) - LIMIT]
    h['idx'] = len(h['stack']) - 1
    return True


def can_undo(ss): h = _h(ss); return h['idx'] > 0
def can_redo(ss): h = _h(ss); return 0 <= h['idx'] < len(h['stack']) - 1


def _go(ss, step):
    h = _h(ss); j = h['idx'] + step
    if not (0 <= j < len(h['stack'])): return None
    h['idx'] = j; s = h['stack'][j]
    return s['fp'], copy.deepcopy(s['nodes']), copy.deepcopy(s['edges'])


def undo(ss): return _go(ss, -1)
def redo(ss): return _go(ss, +1)


def clear(ss): ss.pop(KEY, None)
