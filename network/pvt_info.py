"""Which PVT every well and tank uses, and where they differ. Feeds the canvas labels and the Fluid & PVT checks."""
from __future__ import annotations
import json

CORR_SHORT = {'standing': 'Standing', 'vasquez_beggs': 'V-B', 'glaso': 'Glaso', 'petrosky_farshad': 'P-F'}


def pvt_info(params):
    """{'label','detail','sig'}: short label for the canvas, tooltip detail and a signature that is equal for equal PVT."""
    p = params or {}; cfg = p.get('pvt'); name = p.get('fluid_name') or ''
    if isinstance(cfg, dict) and str(cfg.get('model', 'legacy')).lower() == 'correlation':
        pb = CORR_SHORT.get(str(cfg.get('pb_corr', 'standing')), str(cfg.get('pb_corr')))
        sig = ('corr', json.dumps({k: v for k, v in cfg.items()}, sort_keys=True, default=str))
        return {'label': f"{name or 'fluid'} · corr", 'detail': f"Correlation PVT ({cfg.get('pb_corr', 'standing')} Pb, {cfg.get('bo_corr', 'standing')} Bo, {cfg.get('visc_corr', 'beggs_robinson')} viscosity, {cfg.get('z_corr', 'dak')} Z); API {cfg.get('api', p.get('api', '?'))}, Rsb {cfg.get('rsb_sm3sm3', '?')}", 'sig': sig}
    api, sg = p.get('api'), p.get('gas_sg')
    return {'label': f"{name or 'fluid'} · scr", 'detail': f"Screening PVT (constant Bo, linear Rs below Pb); API {api if api is not None else '?'}, gas SG {sg if sg is not None else '?'}",
            'sig': ('legacy', name, None if api is None else round(float(api), 1), None if sg is None else round(float(sg), 3))}


def same_pvt(a, b):
    """Do two ``pvt_info`` results describe the same PVT? Unknown values (a well with no fluid name, a tank with no API) are not treated as a difference."""
    (ka, *ra), (kb, *rb) = a['sig'], b['sig']
    if ka != kb: return False
    if ka == 'corr': return ra == rb
    (na, apia, sga), (nb, apib, sgb) = ra, rb
    if na and nb: return na == nb
    if apia is not None and apib is not None and abs(apia - apib) > 0.5: return False
    if sga is not None and sgb is not None and abs(sga - sgb) > 0.01: return False
    return True


def pvt_map(nodes):
    """{node_id: {'label','detail','diff': bool, 'note'}} for wells, injectors and tanks. ``diff`` = the element's PVT differs from a tank it is linked to."""
    from network.reservoir_mb import linked_tank_ids
    byid = {n['id']: n for n in nodes}; out = {}
    for n in nodes:
        k = n.get('kind')
        if k not in ('well', 'reservoir', 'water_injector', 'gas_injector', 'injector'): continue
        if k in ('water_injector',) or ((n.get('params') or {}).get('injection_fluid') == 'water' and k != 'reservoir'): continue      # injected water has no black-oil PVT
        out[n['id']] = {**pvt_info(n.get('params')), 'diff': False, 'note': ''}
    for n in nodes:
        if n['id'] not in out or n.get('kind') == 'reservoir': continue
        diffs = []
        for tid in linked_tank_ids(n.get('params')):
            if tid in out and not same_pvt(out[tid], out[n['id']]): diffs.append(byid[tid].get('name') or tid)
        if diffs:
            out[n['id']]['diff'] = True
            out[n['id']]['note'] = 'PVT differs from tank ' + ', '.join(diffs)
    tk = [n for n in nodes if n['id'] in out and n.get('kind') == 'reservoir']
    for n in tk:                                                       # a commingled well draining tanks with different PVT
        pass
    for n in nodes:
        if n['id'] in out and n.get('kind') == 'well':
            ts = [t for t in __import__('network.reservoir_mb', fromlist=['x']).linked_tank_ids(n.get('params')) if t in out]
            if any(not same_pvt(out[ts[0]], out[t]) for t in ts[1:]):
                out[n['id']]['diff'] = True; out[n['id']]['note'] = (out[n['id']]['note'] + '; ' if out[n['id']]['note'] else '') + 'drains tanks with different PVT (blended in one wellbore)'
    return out


def summary(nodes):
    """Human lines for the Fluid & PVT page / a caption: distinct PVTs in use and the number of mismatching elements."""
    m = pvt_map(nodes); labels = sorted({v['label'] for v in m.values()})
    return {'distinct': labels, 'mismatches': [(k, v['note']) for k, v in m.items() if v['diff']]}


FLUID_KEYS = ('fluid_name', 'api', 'gas_sg', 'gor_sm3sm3')


def fix_to_tank(nodes, element_id, tank_id=None):
    """Make a well / injector use the PVT of ``tank_id`` (default: its first, largest-share tank): fluid name, API, gas gravity, GOR and the PVT block are copied.
    Returns True when something changed."""
    import copy
    from network.reservoir_mb import primary_tank_id
    byid = {n['id']: n for n in nodes}; el = byid.get(element_id)
    if not el: return False
    tid = tank_id or primary_tank_id(el.get('params'))
    tk = byid.get(tid)
    if not tk or tk.get('kind') != 'reservoir': return False
    p, tp = el.setdefault('params', {}), tk.get('params') or {}; before = {k: copy.deepcopy(p.get(k)) for k in (*FLUID_KEYS, 'pvt')}
    for k in FLUID_KEYS:
        if k in tp and tp[k] is not None: p[k] = tp[k]
        elif k == 'fluid_name': p.pop(k, None)
    if tp.get('pvt'): p['pvt'] = copy.deepcopy(tp['pvt'])
    else: p.pop('pvt', None)
    return before != {k: p.get(k) for k in (*FLUID_KEYS, 'pvt')}


def fix_all(nodes):
    """Apply ``fix_to_tank`` to every element flagged by ``pvt_map``. Returns the ids changed."""
    m = pvt_map(nodes)
    return [k for k, v in m.items() if v['diff'] and fix_to_tank(nodes, k)]


def used_by(nodes, edges=()):
    """Rows {'PVT','Detail','Tanks','Wells','Injectors','Flowlines'} - which elements use each distinct PVT (named fluids and unnamed settings alike)."""
    m = pvt_map(nodes); byid = {n['id']: n for n in nodes}; groups = {}
    for k, v in m.items():
        n = byid[k]; g = groups.setdefault(v['label'], {'PVT': v['label'], 'Detail': v['detail'], 'Tanks': [], 'Wells': [], 'Injectors': [], 'Flowlines': []})
        g[{'reservoir': 'Tanks', 'well': 'Wells'}.get(n.get('kind'), 'Injectors')].append((n.get('name') or k) + (' ⚠' if v['diff'] else ''))
    for e in edges:
        nm = (e.get('params') or {}).get('fluid_name')
        if nm and e.get('kind', 'pipeline') == 'pipeline':
            for g in groups.values():
                if g['PVT'].startswith(nm + ' ·'): g['Flowlines'].append(e.get('name') or e['id']); break
    return [{**g, **{k: ', '.join(g[k]) for k in ('Tanks', 'Wells', 'Injectors', 'Flowlines')}} for g in groups.values()]
