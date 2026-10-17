import math
from physics.darcy_ipr import wc_mobility_factor
from physics.well_model import well_settings, ipr_rate, ipr_pwf, rate_capacity

GAS = {'darcy': True, 'ipr_model': 'Gas', 'reservoir_pressure_bar': 250, 'gor_sm3sm3': 1e5}


def test_non_darcy_lowers_deliverability_and_roundtrips():
    s0 = well_settings(GAS); s1 = well_settings({**GAS, 'darcy_nd_d': 0.05})
    assert s0['gas_b'] == 0 and s1['gas_b'] > 0
    assert rate_capacity(s1) < rate_capacity(s0)
    q = 0.5 * rate_capacity(s1)
    assert abs(ipr_rate(ipr_pwf(q, s1), s1) - q) < 1e-6 * q
    assert ipr_pwf(q, s1) < ipr_pwf(q, s0)


def test_non_darcy_zero_is_unchanged():
    assert well_settings({**GAS, 'darcy_nd_d': 0})['gas_b'] == 0


def test_wc_mobility_monotone_start_and_flag():
    f0, _ = wc_mobility_factor(0.0, {}, 1.0)
    assert abs(f0 - 1.0) < 1e-6
    assert wc_mobility_factor(0.5, {}, 1.0)[0] < 1.0
    oil = {'darcy': True, 'ipr_model': 'PI', 'reservoir_pressure_bar': 200, 'water_cut': 0.5}
    a = well_settings(oil)['pi']; b = well_settings({**oil, 'darcy_wc_dependence': True})['pi']
    assert b < a and b > 0
    assert math.isclose(well_settings({**oil, 'water_cut': 0.0, 'darcy_wc_dependence': True})['pi'], well_settings({**oil, 'water_cut': 0.0})['pi'], rel_tol=1e-6)


def test_mc_store_roundtrip_with_case_and_compare():
    from network import mc_store
    from network.case_manager import new_case, CaseLibrary
    from ui.cases_view import current_extras
    res = lambda p50: {'successful_samples': 40, 'seed': 1, 'metrics': {'cumulative_oil_m3': {'P90': p50 * .8, 'P50': p50, 'P10': p50 * 1.3, 'mean': p50}}, 'runs': [], 'profiles': [{'date': 'x', 'P50': 1.0}]}
    ss = {}
    mc_store.save_result(ss, 'base', res(100.0)); mc_store.save_result(ss, 'more wells', res(130.0))
    ss['v17_mc'] = res(100.0)
    ex = current_extras(ss); assert 'mc_saved' in ex and 'mc_last' in ex
    case = new_case('c1', [], [], extras=ex)
    assert case['extras']['mc_saved']['base']['result']['metrics']['cumulative_oil_m3']['P50'] == 100.0   # survives the JSON round-trip
    d = mc_store.delta_table(ss, 'base', 'more wells', 'cumulative')
    assert abs(d[d.Quantity.str.contains('P50')]['Δ %'].iloc[0] - 30.0) < 1e-6
    ss2 = {'case_library': CaseLibrary([case]), 'mc_saved': {'extra': {'saved_at': '', 'result': res(90.0)}}}
    assert any('c1 / base' == n for n in mc_store.gather(ss2))
    mc_store.delete_result(ss, 'base'); assert 'base' not in ss['mc_saved']


def _two_tank():
    import copy
    from network.examples import demo_field_case
    n, e = demo_field_case(); t1 = next(x for x in n if x['kind'] == 'reservoir')
    t2 = copy.deepcopy(t1); t2['id'] = 'T2'; t2['name'] = 'Tank 2'; t2['params']['api'] = 45.0; t2['params'].pop('fluid_name', None); n.append(t2)
    wells = [x for x in n if x['kind'] == 'well']
    for w in wells: w['params']['reservoir_id'] = t1['id']
    wells[0]['params']['reservoir_alloc'] = [{'tank_id': t1['id'], 'share': 50.0}, {'tank_id': 'T2', 'share': 50.0}]
    if len(wells) > 1: wells[1]['params']['reservoir_id'] = 'T2'
    return n, e, wells


def test_drainage_gives_per_tank_rf_and_flags():
    from network import drainage as D
    n, e, wells = _two_tank()
    ids = [w['id'] for w in wells][:3]
    res = D.drainage_strategy(n, e, ids, '2030-01-01', 3.0, 365, True, 0.05)
    ts = res['tank_study']['tanks']
    assert len(ts) == 2 and all(len(t['series']) == len(ids) for t in ts.values())
    t2 = ts['T2']; assert t2['optimal_wells_field'] in range(1, len(ids) + 1) and t2['final_rf'] >= 0
    assert any(t['commingled_wells'] for t in ts.values())


def test_wells_per_tank_counts_commingled_well_in_both():
    from network import drainage as D
    n, e, wells = _two_tank()
    m = D.wells_per_tank(n, [wells[0]['id']]); assert len(m) == 2


def test_greedy_order_returns_every_candidate_once():
    from network import drainage as D
    n, e, wells = _two_tank(); ids = [w['id'] for w in wells][:3]
    order, eurs = D.greedy_order(n, e, ids, '2030-01-01', 2.0, 365)
    assert sorted(order) == sorted(ids) and len(eurs) == len(ids)


def test_fix_to_tank_makes_pvt_match_and_used_by_lists_elements():
    from network.pvt_info import pvt_map, fix_to_tank, fix_all, used_by, summary
    n, e, wells = _two_tank()
    t1 = next(x for x in n if x['kind'] == 'reservoir'); t1['params']['fluid_name'] = 'Light'; t1['params']['api'] = 38.0
    w = wells[-1]; w['params']['reservoir_id'] = t1['id']; w['params'].pop('reservoir_alloc', None); w['params']['api'] = 25.0; w['params']['fluid_name'] = 'Heavy'
    assert pvt_map(n)[w['id']]['diff']
    assert fix_to_tank(n, w['id']) is True
    assert w['params']['api'] == 38.0 and w['params']['fluid_name'] == 'Light'
    assert not pvt_map(n)[w['id']]['diff'] and fix_to_tank(n, w['id']) is False
    rows = used_by(n, e); assert any(r['Tanks'] for r in rows) and any(r['Wells'] for r in rows)
    fix_all(n); assert not summary(n)['mismatches'] or all('commingled' in x[1] or 'drains' in x[1] for x in summary(n)['mismatches'])


def test_undo_redo_history():
    from network import history as H
    ss = {}; nodes = [{'id': 'a', 'params': {'x': 1}}]; edges = []
    assert H.record(ss, 'f1', nodes, edges) and not H.can_undo(ss)
    nodes[0]['params']['x'] = 2; assert H.record(ss, 'f2', nodes, edges) and H.can_undo(ss)
    assert not H.record(ss, 'f2', nodes, edges)                      # unchanged fingerprint: nothing recorded
    fp, n, e = H.undo(ss); assert fp == 'f1' and n[0]['params']['x'] == 1 and H.can_redo(ss)
    n[0]['params']['x'] = 99                                          # mutating the restored copy must not corrupt the history
    assert H.redo(ss)[1][0]['params']['x'] == 2
    H.undo(ss); H.record(ss, 'f3', [{'id': 'a', 'params': {'x': 3}}], [])   # new edit after undo drops the redo branch
    assert not H.can_redo(ss)
    for i in range(50): H.record(ss, f'g{i}', nodes, edges)
    assert len(ss[H.KEY]['stack']) == H.LIMIT and H.undo(ss) is not None
    assert H.undo({}) is None
