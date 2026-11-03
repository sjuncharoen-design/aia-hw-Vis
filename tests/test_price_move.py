"""Tests for skill price-move and the shared scripts it extends."""
import importlib.util, json, os, subprocess, sys
from datetime import date, timedelta

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
PM = os.path.join(ROOT, '.claude', 'skills', 'price-move', 'scripts')
SHARED = PM  # Homework เก็บสคริปต์ทั้งหมดไว้ที่เดียว
sys.path.insert(0, SHARED)
import build_evidence_pack as bep  # noqa: E402
import detect_events as de  # noqa: E402
import merge_research as mr  # noqa: E402


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def bars(closes, start=date(2024, 1, 1)):
    return [{'d': (start + timedelta(days=i)).isoformat(), 'p': p} for i, p in enumerate(closes)]


# ---- window events ---------------------------------------------------------------------------------

def test_window_exact_10pct_is_not_counted():
    assert de.window_events(bars([100] * 6 + [110.0])) == []


def test_window_detects_5_day_move_above_10pct():
    e = de.window_events(bars([100] * 6 + [110.1]))
    assert len(e) == 1 and e[0]['kind'] == 'window' and e[0]['dir'] == 'up'


def test_window_detects_6_day_move_when_5_day_does_not():
    assert len(de.window_events(bars([100, 104, 104, 104, 104, 104, 110.5]))) == 1


def test_overlapping_days_merge_into_one_event_with_largest_ret():
    e = de.window_events(bars([100] * 6 + [111, 112, 115]))
    assert len(e) == 1 and e[0]['ret'] == 15.0
    assert e[0]['end'] == bars([0] * 9)[8]['d']


def test_window_range_starts_after_earliest_base():
    P = bars([100] * 6 + [111, 112, 115])
    e = de.window_events(P)[0]
    assert e['base_date'] == P[3]['d'] and e['date'] <= P[6]['d']


def test_overlapping_ranges_merge_even_when_flagged_days_do_not_touch():
    e = de.window_events(bars([100] * 6 + [111, 105, 112]))
    assert len(e) == 1 and e[0]['ret'] == 12.0


def test_opposite_directions_stay_separate():
    e = de.window_events(bars([100] * 6 + [115] * 6 + [100]))
    assert [x['dir'] for x in e] == ['up', 'down']


def test_short_history_does_not_crash():
    assert de.window_events(bars([100, 120])) == []


def test_link_days_only_same_direction():
    P = bars([100] * 6 + [108, 104, 112])
    ev = de.daily_events(P, 5.0) + de.window_events(P)
    de.link_days(ev)
    w = next(e for e in ev if e['kind'] == 'window')
    up, down = P[6]['d'], P[7]['d']
    assert f'{up}_day' in w['days'] and f'{down}_day' not in w['days']
    assert next(e for e in ev if e['date'] == up and e['kind'] == 'day')['in_window'] == f"{w['date']}_window"


def run_detect(tmp_path, closes, prev=None, mode='both'):
    p, o = tmp_path / 'p.json', tmp_path / 'o.json'
    p.write_text(json.dumps(bars(closes)), encoding='utf-8')
    cmd = [sys.executable, os.path.join(SHARED, 'detect_events.py'), str(p), str(o), '--mode', mode, '--years', '0']
    if prev is not None:
        f = tmp_path / 'prev.json'
        f.write_text(json.dumps(prev), encoding='utf-8')
        cmd += ['--prev', str(f)]
    subprocess.run(cmd, check=True, capture_output=True)
    return json.loads(o.read_text(encoding='utf-8'))


def test_both_mode_returns_day_and_window(tmp_path):
    ev = run_detect(tmp_path, [100] * 6 + [111])
    assert sorted(e['kind'] for e in ev) == ['day', 'window']


def test_both_mode_keeps_day_analysis_out_of_window(tmp_path):
    closes = [100] * 6 + [111]
    d = bars(closes)[6]['d']
    prev = [{'date': d, 'end': d, 'kind': 'day', 'ret': 11.0, 'conf': 'mid', 'why': 'งบดี', 'driver': 'margin'}]
    ev = run_detect(tmp_path, closes, prev)
    assert next(e for e in ev if e['kind'] == 'day')['why'] == 'งบดี'
    assert 'why' not in next(e for e in ev if e['kind'] == 'window')


def test_rerun_keeps_unmatched_analysis_as_manual(tmp_path):
    prev = {'events': [{'date': '2020-01-01', 'end': '2020-01-05', 'kind': 'window', 'ret': 12.0, 'conf': 'mid', 'why': 'เดิม', 'driver': 'market'}]}
    ev = run_detect(tmp_path, [100] * 8, prev)
    assert [(e['kind'], e['why']) for e in ev] == [('manual', 'เดิม')]


def test_window_flags_mismatch_inside_range(tmp_path):
    closes = [100] * 6 + [111]
    p, o, r = tmp_path / 'p.json', tmp_path / 'o.json', tmp_path / 'r.json'
    P = bars(closes)
    p.write_text(json.dumps(P), encoding='utf-8')
    r.write_text(json.dumps({'mismatches': [{'d': P[4]['d']}], 'verified_from': P[0]['d'], 'verified_to': P[-1]['d']}), encoding='utf-8')
    subprocess.run([sys.executable, os.path.join(SHARED, 'detect_events.py'), str(p), str(o), '--mode', 'both', '--years', '0', '--recon', str(r)], check=True, capture_output=True)
    ev = json.loads(o.read_text(encoding='utf-8'))
    assert next(e for e in ev if e['kind'] == 'window')['price_mismatch'] is True
    assert next(e for e in ev if e['kind'] == 'day')['price_mismatch'] is False


def test_daily_mode_unchanged():
    assert [e['kind'] for e in de.daily_events(bars([100, 106]), 5.0)] == ['day']


def test_window_pack_uses_event_range_not_long_window():
    lo, hi = bep.event_window({'date': '2025-03-03', 'end': '2025-03-06', 'kind': 'window'})
    assert lo == date(2025, 3, 3) and hi == date(2025, 3, 7)


def test_merge_keeps_pnl_note():
    ev = [{'date': '2025-01-01', 'end': '2025-01-01', 'kind': 'day'}]
    out, _ = mr.merge(ev, [{'id': '2025-01-01_day', 'driver': 'market', 'conf': 'mid', 'why': 'x', 'pnl_note': 'ไม่เกี่ยวกับงบ'}])
    assert out[0]['pnl_note'] == 'ไม่เกี่ยวกับงบ'


def test_rerun_carries_pnl_note():
    assert 'pnl_note' in de.KEEP


def test_merge_keeps_new_fields():
    ev = [{'date': '2025-01-01', 'end': '2025-01-01', 'kind': 'day'}]
    out, missing = mr.merge(ev, [{'id': '2025-01-01_day', 'driver': 'margin', 'conf': 'mid', 'why': 'x', 'outlook': 'ดู GPM', 'market_view': 'บวก', 'direction_match': True}])
    assert not missing and out[0]['outlook'] == 'ดู GPM' and out[0]['market_view'] == 'บวก' and out[0]['direction_match'] is True


def test_merge_and_carry_keep_vs_consensus():
    vc = {'verdict': 'above', 'pct': 15, 'note': 'x', 'src': []}
    ev = [{'date': '2025-01-01', 'end': '2025-01-01', 'kind': 'day'}]
    out, _ = mr.merge(ev, [{'id': '2025-01-01_day', 'driver': 'margin', 'conf': 'mid', 'why': 'x', 'vs_consensus': vc}])
    assert out[0]['vs_consensus'] == vc
    new = [{'date': '2025-01-01', 'end': '2025-01-01', 'kind': 'day', 'ret': 6.0}]
    de.carry_over(new, [dict(out[0], ret=6.0)])
    assert new[0]['vs_consensus'] == vc


# ---- price_daily single source ---------------------------------------------------------------------

def yahoo_file(tmp_path, n=30):
    ts = [1735689600 + 86400 * i for i in range(n)]
    d = {'chart': {'result': [{'timestamp': ts, 'indicators': {'quote': [{'close': [100.0 + i for i in range(n)]}]}}]}}
    f = tmp_path / 'y.json'
    f.write_text(json.dumps(d), encoding='utf-8')
    return f


def test_single_source_writes_status_and_unverified_days(tmp_path):
    r = subprocess.run([sys.executable, os.path.join(SHARED, 'price_daily.py'), 'XYZ', str(tmp_path / 'o'), '--yahoo-file', str(yahoo_file(tmp_path)), '--single-source'], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    rec = json.loads((tmp_path / 'o' / 'price_recon.json').read_text(encoding='utf-8'))
    rows = json.loads((tmp_path / 'o' / 'price_daily.json').read_text(encoding='utf-8'))
    assert rec['status'] == 'single_source' and rec['primary'] == 'yahoo'
    assert rows and all(x['v'] is False for x in rows)


def test_without_tv_and_without_flag_still_fails(tmp_path):
    r = subprocess.run([sys.executable, os.path.join(SHARED, 'price_daily.py'), 'XYZ', str(tmp_path / 'o'), '--yahoo-file', str(yahoo_file(tmp_path))], capture_output=True, text=True)
    assert r.returncode != 0


# ---- pnl_breakdown ---------------------------------------------------------------------------------

def pnl():
    return load('pnl_breakdown', os.path.join(PM, 'pnl_breakdown.py'))


def block(cur, pri, labels=None):
    """one income-statement block. cur/pri = dict(rev, tot, cogs, sell, admin, fin, np)"""
    L = {'rev': 'รายได้จากการขาย', 'tot': 'รวมรายได้', 'cogs': 'ต้นทุนขาย', 'sell': 'ค่าใช้จ่ายในการขาย', 'admin': 'ค่าใช้จ่ายในการบริหาร', 'fin': 'ต้นทุนทางการเงิน', 'ecl': 'ผลขาดทุนด้านเครดิตที่คาดว่าจะเกิดขึ้น', 'np': 'กำไรสำหรับงวด'}
    L.update(labels or {})
    out = ['| รายได้ |  |  |']
    for k in ('rev', 'tot', 'cogs', 'sell', 'admin', 'ecl', 'fin', 'np'):
        if k in cur:
            out.append(f'| {L[k]} |  | {cur[k]} |  | {pri[k]} |')
    return out


def v(rev=1000, cogs=600, sell=100, admin=50, fin=10, np=200, scale=1000):
    return dict(rev=rev * scale, tot=rev * scale, cogs=cogs * scale, sell=sell * scale, admin=admin * scale, fin=fin * scale, np=np * scale)


def fs(tmp_path, t, q, *blocks_):
    d = tmp_path / t / 'Financial statement'
    d.mkdir(parents=True, exist_ok=True)
    (d / f'{q}_FS_{t}.xlsx.extracted.md').write_text('\n'.join(x for b in blocks_ for x in b) + '\n', encoding='utf-8')


def test_q4_is_full_year_minus_nine_months(tmp_path):
    fs(tmp_path, 'XYZ', '2024Q3', block(v(1000, np=100), v(900, np=90)), block(v(3000, cogs=1800, sell=300, admin=150, fin=30, np=300), v(2700, cogs=1700, sell=280, admin=140, fin=30, np=270)))
    fs(tmp_path, 'XYZ', '2024Q4', block(v(4200, cogs=2500, sell=420, admin=210, fin=40, np=450), v(3600, cogs=2300, sell=380, admin=190, fin=40, np=350)))
    q = pnl().build('XYZ', str(tmp_path))['quarters']['2024Q4']
    assert q['cur']['np'] == 150 and q['prior']['np'] == 80 and q['cur']['rev'] == 1200


def test_quarter_uses_three_month_block_not_cumulative(tmp_path):
    fs(tmp_path, 'XYZ', '2024Q2', block(v(1000, np=100), v(900, np=90)), block(v(2000, np=250), v(1800, np=200)))
    q = pnl().build('XYZ', str(tmp_path))['quarters']['2024Q2']
    assert q['cur']['np'] == 100 and q['cur']['rev'] == 1000


def test_q3_without_valid_cumulative_block_is_missing(tmp_path):
    fs(tmp_path, 'XYZ', '2024Q3', block(v(1000, np=100), v(900, np=90)))
    r = pnl().build('XYZ', str(tmp_path))
    assert '2024Q3' in r['missing'] and '2024Q3' not in r['quarters']


def test_block_without_profit_row_is_dropped(tmp_path):
    a = [x for x in block(v(800, np=80), v(700, np=70)) if 'กำไร' not in x]
    fs(tmp_path, 'XYZ', '2024Q1', a, block(v(1000, np=100), v(900, np=90)))
    assert pnl().build('XYZ', str(tmp_path))['quarters']['2024Q1']['cur']['np'] == 100


def test_decomposed_sara_am_is_read(tmp_path):
    fs(tmp_path, 'XYZ', '2024Q1', block(v(np=100), v(np=90), {'np': 'ก\u0e4d\u0e32ไรสุทธิส\u0e4d\u0e32หรับงวด', 'cogs': 'ต้นทุนขาย'}))
    assert pnl().build('XYZ', str(tmp_path))['quarters']['2024Q1']['cur']['np'] == 100


def test_note_column_is_not_read_as_value(tmp_path):
    d = tmp_path / 'XYZ' / 'Financial statement'
    d.mkdir(parents=True)
    rows = block(v(), v(900))
    rows[1] = '| รายได้จากการขาย | 27 | 1000000 |  | 900000 |'
    (d / '2024Q1_FS_XYZ.xlsx.extracted.md').write_text('\n'.join(rows), encoding='utf-8')
    assert pnl().build('XYZ', str(tmp_path))['quarters']['2024Q1']['cur']['rev'] == 1000


def test_negative_costs_become_positive(tmp_path):
    a, b = v(), v(900)
    a['cogs'], b['cogs'] = -a['cogs'], -b['cogs']
    fs(tmp_path, 'XYZ', '2024Q1', block(a, b))
    assert pnl().build('XYZ', str(tmp_path))['quarters']['2024Q1']['cur']['cogs'] == 600


def test_thousand_and_baht_units_scale_to_million(tmp_path):
    fs(tmp_path, 'XYZ', '2024Q1', block(v(scale=1000), v(900, scale=1000)))
    fs(tmp_path, 'XYZ', '2025Q1', block(v(scale=1000000), v(1000, scale=1000000)))
    r = pnl().build('XYZ', str(tmp_path))['quarters']
    assert r['2024Q1']['cur']['rev'] == 1000 and r['2025Q1']['cur']['rev'] == 1000


def test_finance_layout_when_cogs_below_5pct_of_revenue(tmp_path):
    a = dict(tot=800000, cogs=200, admin=400000, ecl=140000, fin=90000, np=140000)
    b = dict(tot=790000, cogs=300, admin=410000, ecl=190000, fin=118000, np=50000)
    d = tmp_path / 'XYZ' / 'Financial statement'
    fs(tmp_path, 'XYZ', '2024Q1', block(a, b))
    r = pnl().build('XYZ', str(tmp_path))
    q = r['quarters']['2024Q1']
    assert r['finance'] is True and q['cur'].get('gpm') is None and q['cur']['rev'] == 800
    assert {x['line'] for x in q['bridge']} == {'rev', 'admin', 'ecl', 'fin', 'other', 'np'}


def bridge_of(tmp_path):
    fs(tmp_path, 'XYZ', '2024Q1', block(v(1000, 600, 100, 50, 10, 200), v(900, 500, 120, 60, 20, 160)))
    return pnl().build('XYZ', str(tmp_path))['quarters']['2024Q1']['bridge']


def test_bridge_sums_to_net_profit_change(tmp_path):
    b = bridge_of(tmp_path)
    np_ = next(x['delta'] for x in b if x['line'] == 'np')
    assert np_ == 40 and abs(sum(x['delta'] for x in b if x['line'] != 'np') - np_) <= 0.02


def test_revenue_and_margin_effect_sum_to_gross_profit_change(tmp_path):
    b = {x['line']: x['delta'] for x in bridge_of(tmp_path)}
    # รายได้ +100 × GPM ปีก่อน 44.44% = 44.44 · กำไรขั้นต้น 400 เทียบ 400 จึงเหลือผลมาร์จิ้น −44.44
    assert b['rev'] == 44.44 and b['gpm'] == -44.44


def test_filing_time_prefers_set_news_over_file_name(tmp_path):
    fs(tmp_path, 'XYZ', '2025Q1', block(v(), v(900)))
    (tmp_path / 'XYZ' / 'Financial statement' / 'FS_202505_1FIN1205202508560').mkdir()
    n = tmp_path / 'XYZ' / 'News'
    n.mkdir()
    (n / 'set_news_2025-05-15.jsonl').write_text(json.dumps({'title': 'งบการเงิน ไตรมาสที่ 1/2568 (สอบทานแล้ว)', 'datetime': '2025-05-15T17:26:00'}, ensure_ascii=False) + '\n', encoding='utf-8')
    f = pnl().build('XYZ', str(tmp_path))['quarters']['2025Q1']['filed']
    assert f['date'] == '2025-05-15' and f['time'] == '17:26' and f['est'] is False


def test_filing_uses_file_name_when_no_news(tmp_path):
    fs(tmp_path, 'XYZ', '2025Q1', block(v(), v(900)))
    (tmp_path / 'XYZ' / 'Financial statement' / 'FS_202505_1FIN1205202508560').mkdir()
    f = pnl().build('XYZ', str(tmp_path))['quarters']['2025Q1']['filed']
    assert f['date'] == '2025-05-12' and f['est'] is False


def test_filing_estimated_when_unknown(tmp_path):
    fs(tmp_path, 'XYZ', '2025Q1', block(v(), v(900)))
    f = pnl().build('XYZ', str(tmp_path))['quarters']['2025Q1']['filed']
    assert f['date'] == '2025-05-15' and f['est'] is True


def test_browser_news_file_is_used(tmp_path):
    fs(tmp_path, 'XYZ', '2025Q1', block(v(), v(900)))
    b = tmp_path / 'browser.jsonl'
    b.write_text(json.dumps({'title': 'งบการเงิน ไตรมาสที่ 1/2568', 'datetime': '2025-05-09T17:10'}, ensure_ascii=False) + '\n', encoding='utf-8')
    assert pnl().build('XYZ', str(tmp_path), str(b))['quarters']['2025Q1']['filed']['date'] == '2025-05-09'


# ---- build_page / check_page ------------------------------------------------------------------------

def bp():
    return load('pm_build_page', os.path.join(PM, 'build_page.py'))


def cp():
    return load('pm_check_page', os.path.join(PM, 'check_page.py'))


GOOD_EV = dict(src='https://www.set.or.th/x', tier='A', date='2025-08-06', time='17:24', accessed='2026-11-02', note='งบ')


def known_event(**kw):
    e = dict(date='2025-08-07', end='2025-08-07', kind='day', ret=-8.68, dir='down', conf='mid', direction_match=True, what='งบออก', why='กำไรลด', market_view='ไม่มี', outlook='ดู GPM', evidence=[dict(GOOD_EV)], pnl_note='เรื่องงบ')
    e.update(kw)
    return e


def test_status_known_needs_evidence_direction_and_conf():
    b = bp()
    assert b.status_of(known_event()) == 'known'
    assert b.status_of(known_event(conf='low')) == 'draft'
    assert b.status_of(known_event(direction_match=False)) == 'draft'
    assert b.status_of(known_event(evidence=[])) == 'draft'


def test_status_draft_when_only_broker_evidence():
    ev = dict(GOOD_EV, src='AllCompany/DOHOME/Broker/KSec_2025-08-06.pdf.extracted.md')
    assert bp().status_of(known_event(evidence=[ev])) == 'draft'


def test_status_draft_when_evidence_after_event():
    assert bp().status_of(known_event(evidence=[dict(GOOD_EV, date='2025-08-08')])) == 'draft'


def test_evidence_after_1630_on_event_day_does_not_count():
    b = bp()
    assert b.status_of(known_event(evidence=[dict(GOOD_EV, date='2025-08-07', time='17:00')])) == 'draft'
    assert b.status_of(known_event(evidence=[dict(GOOD_EV, date='2025-08-07', time='09:00')])) == 'known'


def test_high_conf_with_price_mismatch_becomes_mid():
    e = known_event(conf='high', price_mismatch=True)
    bp().normalize(e)
    assert e['conf'] == 'mid'


def test_window_inherits_known_from_linked_day():
    b = bp()
    day = known_event()
    w = dict(date='2025-08-04', end='2025-08-08', kind='window', ret=-12.0, dir='down', conf='low', days=['2025-08-07_day'])
    for e in (day, w):
        e['status'] = b.status_of(e)
    b.inherit_window([day, w])
    assert w['status'] == 'known' and w['inherited_from'] == ['2025-08-07_day']


def page_of(tmp_path, events=None, takeaways=None, closes=None, public=False, pnl_q=None):
    b = bp()
    closes = closes or [100, 100, 91.32]
    prices = [{'d': x['d'], 'p': x['p'], 'v': True} for x in bars(closes, date(2025, 8, 5))]
    pnl_ = pnl_q or {'ticker': 'XYZ', 'finance': False, 'missing': [], 'quarters': {}}
    return b.assemble('XYZ', events if events is not None else [known_event()], takeaways or {'catalysts': [], 'risks': []}, pnl_, prices, {'status': 'ok', 'primary': 'yahoo'})


def test_check_passes_on_good_page(tmp_path):
    assert cp().check(page_of(tmp_path)) == []


def test_check_fails_when_event_missing_from_page(tmp_path):
    assert any('ไม่อยู่ในหน้า' in x for x in cp().check(page_of(tmp_path, events=[])))


def test_check_fails_when_takeaway_cites_draft_event(tmp_path):
    t = {'catalysts': [{'text': 'x', 'ids': ['2025-08-07_day'], 'watch': 'y'}], 'risks': []}
    pg = page_of(tmp_path, events=[known_event(conf='low')], takeaways=t)
    assert any('Key takeaway' in x for x in cp().check(pg))


def test_check_fails_when_known_card_missing_what_or_why(tmp_path):
    assert any('what' in x for x in cp().check(page_of(tmp_path, events=[known_event(what='')])))
    assert any('why' in x for x in cp().check(page_of(tmp_path, events=[known_event(why='')])))


def test_check_allows_known_card_without_market_view_or_outlook(tmp_path):
    assert cp().check(page_of(tmp_path, events=[known_event(outlook='', market_view='')])) == []


def test_check_fails_when_known_has_no_pnl_answer(tmp_path):
    e = known_event()
    del e['pnl_note']
    assert any('กระทบงบ' in x for x in cp().check(page_of(tmp_path, events=[e])))


def test_check_fails_when_source_not_in_reference(tmp_path):
    pg = page_of(tmp_path)
    pg['references'] = []
    assert any('Reference' in x for x in cp().check(pg))


def test_check_fails_when_url_has_no_access_date(tmp_path):
    ev = dict(GOOD_EV)
    del ev['accessed']
    assert any('วันที่เข้าถึง' in x for x in cp().check(page_of(tmp_path, events=[known_event(evidence=[ev])])))


def test_check_fails_when_bridge_does_not_sum(tmp_path):
    q = {'cur': {}, 'prior': {}, 'yoy': {}, 'filed': {'date': '2025-08-06', 'est': False}, 'bridge': [{'line': 'rev', 'name': 'a', 'delta': 5}, {'line': 'other', 'name': 'b', 'delta': 1}, {'line': 'np', 'name': 'c', 'delta': 9}]}
    pg = page_of(tmp_path, events=[known_event(pnl_quarter='2025Q2')], pnl_q={'ticker': 'XYZ', 'finance': False, 'missing': [], 'quarters': {'2025Q2': q}})
    assert any('สะพานกำไร' in x for x in cp().check(pg))


def test_check_fails_when_event_has_no_tooltip(tmp_path):
    pg = page_of(tmp_path)
    pg['events'][0]['tip'] = ''
    assert any('กล่อง' in x for x in cp().check(pg))


def write_inputs(tmp_path, events, takeaways=None):
    d = tmp_path / 'd'
    d.mkdir(exist_ok=True)
    prices = [{'d': x['d'], 'p': x['p'], 'v': True} for x in bars([100, 100, 91.32], date(2025, 8, 5))]
    (d / 'price_daily.json').write_text(json.dumps(prices), encoding='utf-8')
    (d / 'price_recon.json').write_text(json.dumps({'status': 'ok', 'primary': 'yahoo'}), encoding='utf-8')
    (tmp_path / 'e.json').write_text(json.dumps(events, ensure_ascii=False), encoding='utf-8')
    (tmp_path / 't.json').write_text(json.dumps(takeaways or {'catalysts': [], 'risks': []}), encoding='utf-8')
    (tmp_path / 'p.json').write_text(json.dumps({'ticker': 'XYZ', 'finance': False, 'missing': [], 'quarters': {}}), encoding='utf-8')


def run_build(tmp_path, *extra):
    return subprocess.run([sys.executable, os.path.join(PM, 'build_page.py'), 'XYZ', '--events', str(tmp_path / 'e.json'), '--takeaways', str(tmp_path / 't.json'), '--pnl', str(tmp_path / 'p.json'), '--price-dir', str(tmp_path / 'd'), '--out-dir', str(tmp_path / 'o'), *extra], capture_output=True, text=True)


def built_html(tmp_path):
    f = [x for x in os.listdir(tmp_path / 'o') if x.endswith('.html')]
    return (tmp_path / 'o' / f[0]).read_text(encoding='utf-8')


def test_page_builds_with_no_known_events(tmp_path):
    write_inputs(tmp_path, [known_event(conf='low')])
    assert run_build(tmp_path).returncode == 0
    assert 'ยังไม่มีเหตุการณ์ที่รู้สาเหตุ' in built_html(tmp_path)
    pg = json.loads((tmp_path / 'o' / 'price_move.json').read_text(encoding='utf-8'))
    assert [e['status'] for e in pg['events']] == ['draft']


def test_script_tag_in_news_title_is_escaped(tmp_path):
    write_inputs(tmp_path, [known_event(why='</script><b>x')])
    assert run_build(tmp_path).returncode == 0
    h = built_html(tmp_path)
    assert '</script><b>x' not in h and embedded_json(h)['events'][0]['why'] == '</script><b>x'


def test_manual_event_is_shown(tmp_path):
    write_inputs(tmp_path, [known_event(), known_event(date='2020-01-01', end='2020-01-05', kind='manual', ret=12.0, dir='up')])
    assert run_build(tmp_path).returncode == 0
    pg = json.loads((tmp_path / 'o' / 'price_move.json').read_text(encoding='utf-8'))
    assert '2020-01-01_manual' in [e['id'] for e in pg['events']]


def test_public_removes_broker_and_target_price(tmp_path):
    broker = dict(GOOD_EV, src='AllCompany/XYZ/Broker/a.pdf.extracted.md', note='สรุป')
    write_inputs(tmp_path, [known_event(market_view='KSec แนะนำซื้อ', market_view_public='โบรกส่วนใหญ่มองบวก', market_view_src=[broker], context=[broker])])
    out = tmp_path / 'pub.html'
    r = run_build(tmp_path, '--public', '--out', str(out))
    assert r.returncode == 0, r.stderr
    h = out.read_text(encoding='utf-8')
    assert 'KSec' not in h and 'โบรกส่วนใหญ่มองบวก' in h and '/Broker/' not in h


def test_public_aborts_when_broker_name_remains(tmp_path):
    write_inputs(tmp_path, [known_event(why='KSec ลดราคาเป้าหมาย')])
    out = tmp_path / 'pub.html'
    r = run_build(tmp_path, '--public', '--out', str(out))
    assert r.returncode != 0 and not out.exists()


def test_missing_pnl_quarter_says_no_data(tmp_path):
    pg = page_of(tmp_path, events=[known_event(pnl_quarter='2020Q1')])
    assert pg['events'][0]['pnl'] is None and 'ไม่มีข้อมูลงบงวด 2020Q1' in pg['events'][0]['pnl_note']


def test_quarterly_rows_match_evidence_pack_fields(tmp_path):
    fs(tmp_path, 'XYZ', '2024Q1', block(v(1000, np=200), v(800, np=100)))
    fs(tmp_path, 'XYZ', '2024Q2', block(v(1000, np=300), v(800, np=100)), block(v(2000, np=500), v(1600, np=200)))
    m = pnl()
    rows = m.quarterly_rows(m.build('XYZ', str(tmp_path)))
    assert [r['q'] for r in rows] == ['2024Q1', '2024Q2']
    assert rows[0]['rev'] == 1000 and rows[0]['np'] == 200 and rows[0]['rev_yoy'] == 25 and rows[0]['np_yoy'] == 100
    assert rows[1]['np_qoq'] == 50 and rows[0]['gpm'] == 40


# ---- final review fixes ---------------------------------------------------------------------------

import re  # noqa: E402


def embedded_json(html):
    m = re.search(r'<script id="data" type="application/json">(.*?)</script>', html, re.S)
    return json.loads(m.group(1))


def test_html_comment_in_text_keeps_embedded_json_valid(tmp_path):
    write_inputs(tmp_path, [known_event(why='ข่าว <!-- x --> จบ')])
    assert run_build(tmp_path).returncode == 0
    assert embedded_json(built_html(tmp_path))['events'][0]['why'] == 'ข่าว <!-- x --> จบ'


def test_template_escapes_every_free_text_interpolation():
    tpl = open(os.path.join(PM, '..', 'assets', 'page_template.html'), encoding='utf-8').read()
    assert re.search(r'const fd=s=>\{[^\n]*esc\(', tpl)
    for raw in ('${x.level}', '${e.conf}', 'href="#ev-${i}"', 'class="tag ${e.conf}"', 'class="tag ${x.level}"'):
        assert raw not in tpl, raw


def test_unit_label_beats_magnitude_guess(tmp_path):
    d = tmp_path / 'XYZ' / 'Financial statement'
    d.mkdir(parents=True)
    big = v(scale=100000)  # 1000 x 100,000 = 100,000,000 in thousand baht = 100,000 M
    (d / '2024Q1_FS_XYZ.xlsx.extracted.md').write_text('หน่วย: พันบาท)\n' + '\n'.join(block(big, big)), encoding='utf-8')
    small = v(scale=45206)  # 45,206,000 baht = 45.21 M, magnitude alone would read thousand
    (d / '2024Q2_FS_XYZ.xlsx.extracted.md').write_text('หน่วย : บาท\n' + '\n'.join(block(small, small) + block(v(scale=90410), v(scale=90410))), encoding='utf-8')
    q = pnl().build('XYZ', str(tmp_path))['quarters']
    assert q['2024Q1']['cur']['rev'] == 100000 and q['2024Q2']['cur']['rev'] == 45.21


def test_dash_blank_and_comma_cells_keep_their_column(tmp_path):
    d = tmp_path / 'XYZ' / 'Financial statement'
    d.mkdir(parents=True)
    rows = block(v(), v(900))
    rows = [r for r in rows if 'ต้นทุนทางการเงิน' not in r and 'ต้นทุนขาย' not in r]
    rows.insert(2, '| ต้นทุนขาย |  | 600,000 |  | 500,000 |')
    rows.insert(3, '| ต้นทุนทางการเงิน |  | - |  | 5,660 |')
    (d / '2024Q1_FS_XYZ.xlsx.extracted.md').write_text('\n'.join(rows), encoding='utf-8')
    q = pnl().build('XYZ', str(tmp_path))['quarters']['2024Q1']
    assert q['cur']['cogs'] == 600 and q['prior']['cogs'] == 500
    assert q['cur']['fin'] == 0 and q['prior']['fin'] == 5.66


@pytest.mark.parametrize('text', ['ดู https://www.globlex.co.th/r', 'Bualuang มองบวก', 'target price 4.3', 'TP 4.3 บาท', 'ประมาณการกำไรปีหน้า'])
def test_public_aborts_on_more_broker_content(tmp_path, text):
    write_inputs(tmp_path, [known_event(outlook=text)])
    out = tmp_path / 'pub.html'
    assert run_build(tmp_path, '--public', '--out', str(out)).returncode != 0 and not out.exists()


def test_broker_url_cannot_confirm_a_cause():
    assert bp().status_of(known_event(evidence=[dict(GOOD_EV, src='https://www.kgieworld.co.th/research/x')])) == 'draft'


def test_evidence_long_before_event_does_not_count():
    assert bp().status_of(known_event(evidence=[dict(GOOD_EV, date='2022-08-06')])) == 'draft'


def test_time_without_leading_zero_is_read_as_morning():
    assert bp().status_of(known_event(evidence=[dict(GOOD_EV, date='2025-08-07', time='9:30')])) == 'known'


def window_and_day(day_ret=-8.68, w_ret=-12.0, **wkw):
    b = bp()
    day = known_event(ret=day_ret)
    w = dict(date='2025-08-04', end='2025-08-08', kind='window', ret=w_ret, dir='down', conf='low', days=['2025-08-07_day'], **wkw)
    for e in (day, w):
        e['status'] = b.status_of(e)
    b.inherit_window([day, w])
    return w


def test_window_does_not_inherit_when_its_own_analysis_disagrees():
    assert window_and_day(direction_match=False)['status'] == 'draft'


def test_window_does_not_inherit_when_known_days_explain_under_half():
    assert window_and_day(day_ret=-5.5, w_ret=-24.0)['status'] == 'draft'


def test_rerun_keeps_unmatched_draft_with_hypothesis(tmp_path):
    prev = {'events': [{'date': '2020-01-01', 'end': '2020-01-05', 'kind': 'window', 'ret': 12.0, 'conf': 'low', 'why': 'ยังไม่พบ', 'hypothesis': {'scope': 'industry', 'text': 'ตามกลุ่ม'}, 'next_check': 'ดูดัชนีกลุ่ม'}]}
    ev = run_detect(tmp_path, [100] * 8, prev)
    assert [(e['kind'], e['next_check']) for e in ev] == [('manual', 'ดูดัชนีกลุ่ม')]


def test_partial_revenue_label_falls_back_to_total(tmp_path):
    a, b = v(1000), v(900)
    a['tot'], b['tot'] = 5000000, 4500000  # รายได้จากการขายเป็นแค่ส่วนน้อย ที่เหลือเป็นรายได้บริการที่ไม่รู้จักชื่อบรรทัด
    fs(tmp_path, 'XYZ', '2024Q1', block(a, b))
    q = pnl().build('XYZ', str(tmp_path))['quarters']['2024Q1']
    assert q['cur']['rev'] == 5000 and q['cur']['gpm'] is None


# ---- market file, volume/gap, XD ----------------------------------------------------------------------

def yahoo_full(tmp_path, n=40, vols=None, opens=None):
    ts = [1735689600 + 86400 * i for i in range(n)]
    q = {'close': [100.0 + i for i in range(n)], 'volume': vols or [1000] * n, 'open': opens or [100.0 + i for i in range(n)]}
    f = tmp_path / 'y.json'
    f.write_text(json.dumps({'chart': {'result': [{'timestamp': ts, 'indicators': {'quote': [q]}}]}}), encoding='utf-8')
    return f


def run_price(tmp_path, *extra, yf=None):
    out = tmp_path / 'o'
    r = subprocess.run([sys.executable, os.path.join(SHARED, 'price_daily.py'), 'XYZ', str(out), '--yahoo-file', str(yf or yahoo_full(tmp_path)), '--single-source', *extra], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads((out / 'price_daily.json').read_text(encoding='utf-8')), json.loads((out / 'price_recon.json').read_text(encoding='utf-8'))


def test_market_file_fills_set_field_and_records_source(tmp_path):
    rows0, _ = run_price(tmp_path)
    mf = tmp_path / 'm.json'
    mf.write_text(json.dumps({'points': {r['d']: 1500.0 + i for i, r in enumerate(rows0)}}), encoding='utf-8')
    rows, rec = run_price(tmp_path, '--market-file', str(mf))
    assert rows[3]['set'] == 1503.0 and rec['market_source'] == 'm.json'


def test_volume_ratio_and_gap_are_added_from_yahoo(tmp_path):
    vols = [1000] * 39 + [4000]
    opens = [100.0 + i for i in range(39)] + [120.0]  # วันสุดท้าย: ปิดก่อนหน้า 138 เปิด 120 = gap -13.04%
    rows, _ = run_price(tmp_path, yf=yahoo_full(tmp_path, 40, vols, opens))
    assert rows[-1]['vr'] == 4.0 and rows[-1]['gap'] == -13.04
    assert 'vr' not in rows[5]  # ยังมีวันก่อนหน้าไม่ถึง 20 วัน


def test_event_carries_volume_ratio_and_gap():
    P = bars([100.0] * 25 + [112.0])
    P[-1].update(vr=3.5, gap=4.2)
    e = de.daily_events(P, 5.0)[0]
    assert e['vol_ratio'] == 3.5 and e['gap'] == 4.2


def corp():
    return load('pm_corp_actions', os.path.join(PM, 'corp_actions.py'))


def write_div_xlsx(tmp_path, rows):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    for r in [['Rights & Benefits'], ['By Company', 'XYZ'], ['Display', 'Selected Symbol'], ['CA Type', 'XD'], [], ['Symbol', 'X-Date', 'Announce Date', 'Dividend (per Share)', 'Adjusted DPS', 'Unit', 'Operation Period', 'Source of Dividend', 'Payment Date', 'Price Before X-Date', 'Price On X-Date']] + rows:
        ws.append(r)
    f = tmp_path / 'XYZ-Dividends.xlsx'
    wb.save(f)
    return f


def test_corp_actions_reads_cash_and_stock_dividends(tmp_path):
    from datetime import datetime
    f = write_div_xlsx(tmp_path, [
        ['XYZ', datetime(2025, 3, 4, 0, 0, 4), None, ' 0.5 ', '0.4', 'Baht', '', 'NP', None, '10.0', '9.5'],
        ['XYZ', datetime(2025, 3, 4, 0, 0, 4), None, ' 25 : 1 ', '25 : 1', 'Share', '', 'NP', None, '10.0', '9.5'],
    ])
    acts = corp().read_dividends(str(f))
    assert [(a['date'], a['kind']) for a in acts] == [('2025-03-04', 'cash'), ('2025-03-04', 'stock')]
    assert acts[0]['amount'] == 0.5 and acts[0]['price_before'] == 10.0 and acts[1]['ratio'] == '25:1'


def test_corp_actions_missing_file_returns_empty(tmp_path):
    assert corp().read_dividends(str(tmp_path / 'none.xlsx')) == []


def test_events_get_xd_context_inside_their_range(tmp_path):
    p, o, x = tmp_path / 'p.json', tmp_path / 'o.json', tmp_path / 'x.json'
    P = bars([100] * 6 + [111])
    p.write_text(json.dumps(P), encoding='utf-8')
    x.write_text(json.dumps([{'date': P[6]['d'], 'kind': 'cash', 'amount': 1.0, 'price_before': 100.0}]), encoding='utf-8')
    subprocess.run([sys.executable, os.path.join(SHARED, 'detect_events.py'), str(p), str(o), '--mode', 'both', '--years', '0', '--xd', str(x)], check=True, capture_output=True)
    ev = json.loads(o.read_text(encoding='utf-8'))
    assert all(e['xd'][0]['pct'] == 1.0 for e in ev)


def test_prev_file_missing_is_treated_as_first_run(tmp_path):
    p, o = tmp_path / 'p.json', tmp_path / 'o.json'
    p.write_text(json.dumps(bars([100] * 6 + [111])), encoding='utf-8')
    r = subprocess.run([sys.executable, os.path.join(SHARED, 'detect_events.py'), str(p), str(o), '--mode', 'both', '--years', '0', '--prev', str(tmp_path / 'nope.json')], capture_output=True, text=True)
    assert r.returncode == 0 and len(json.loads(o.read_text(encoding='utf-8'))) == 2


# ---- small leftovers from the review ---------------------------------------------------------------------

def test_stale_no_data_note_is_dropped_when_quarter_is_readable(tmp_path):
    q = {'cur': {}, 'prior': {}, 'yoy': {}, 'filed': {'date': '2025-08-06', 'est': False}, 'bridge': None}
    pg = page_of(tmp_path, events=[known_event(pnl_quarter='2025Q2', pnl_note='ไม่มีข้อมูลงบงวด 2025Q2')], pnl_q={'ticker': 'XYZ', 'finance': False, 'missing': [], 'quarters': {'2025Q2': q}})
    assert pg['events'][0].get('pnl_note') is None


def test_duplicate_event_ids_get_a_suffix(tmp_path):
    pg = page_of(tmp_path, events=[known_event(kind='manual'), known_event(kind='manual')])
    ids = [e['id'] for e in pg['events']]
    assert len(set(ids)) == 2


def test_empty_price_rows_exit_with_message(tmp_path):
    write_inputs(tmp_path, [known_event()])
    (tmp_path / 'd' / 'price_daily.json').write_text('[]', encoding='utf-8')
    r = run_build(tmp_path)
    assert r.returncode != 0 and 'ไม่มีราคา' in (r.stderr + r.stdout) and 'Traceback' not in r.stderr


def test_public_runs_check_and_aborts_when_an_event_is_missing(tmp_path):
    write_inputs(tmp_path, [])  # ราคาในไฟล์มีวัน -8.68% แต่ไม่มีเหตุการณ์ในรายการ
    out = tmp_path / 'pub.html'
    r = run_build(tmp_path, '--public', '--out', str(out))
    assert r.returncode != 0 and 'ไม่ผ่านการตรวจ' in (r.stderr + r.stdout) and not out.exists()


def test_template_draws_manual_events():
    tpl = open(os.path.join(PM, '..', 'assets', 'page_template.html'), encoding='utf-8').read()
    assert "e.kind==='manual'" in tpl or "'manual'" in tpl


# ---- Homework: ไม่มี path/ข้อมูลส่วนตัวในสคริปต์ที่ย้ายมา ----
def test_no_private_paths_in_skill():
    bad = ('Routines4_broker', 'D:/', '1_unified_dashboard')
    for d in (PM, os.path.join(PM, '..', 'assets')):
        for f in os.listdir(d):
            if f.endswith(('.py', '.html', '.json')):
                t = open(os.path.join(d, f), encoding='utf-8').read()
                assert not [b for b in bad if b in t], (f, bad)


def test_evidence_pack_raw_default_from_env(tmp_path):
    ev = tmp_path / 'e.json'; ev.write_text('[]')
    q = tmp_path / 'q.json'; q.write_text('{}')
    env = dict(os.environ, PRICE_MOVE_RAW=str(tmp_path / 'raw'))
    r = subprocess.run([sys.executable, os.path.join(PM, 'build_evidence_pack.py'), 'XYZ', str(ev), str(q), str(tmp_path / 'k')],
                       capture_output=True, text=True, env=env)
    assert 'AllCompany' not in (r.stdout + r.stderr)


def test_evidence_pack_no_broker_by_default():
    src = open(os.path.join(PM, 'build_evidence_pack.py'), encoding='utf-8').read()
    assert "a.broker or os.path.join" not in src


# ---- extras.json: ส่วนเสริมของหน้า (Oppday / หัวข้อติดตาม / เหตุการณ์ถัดไป / ปัจจัย SWOT-5 Forces) ----
GOOD_EXTRAS = {
    'oppday': {'file': 'Oppday Q2/2026 (ไฟล์ในเครื่อง)', 'drivers': [{'t': 'สินเชื่อโต', 'pg': 'หน้า 3'}], 'risks': [{'t': 'หนี้ครัวเรือนสูง', 'pg': 'หน้า 7'}]},
    'watch': [{'t': 'Credit cost', 'latest': '4.5%', 'signal': 'เกิน 5.25%'}],
    'next': [{'t': 'งบ Q3', 'd': 'ราว 11 พ.ย.', 'basis': 'ปีก่อนออก 11 พ.ย.'}],
    'factors': [{'f': 'ราคาเหล็ก', 'force': 'อำนาจซัพพลายเออร์', 'swot': 'Threat', 'level': 'tested', 'src': 'เทียบ HRC ได้ทิศเดียวกัน 6/8 ไตรมาส'}],
}


def with_extras(tmp_path, extras):
    (tmp_path / 'x.json').write_text(json.dumps(extras, ensure_ascii=False), encoding='utf-8')
    return ['--extras', str(tmp_path / 'x.json')]


def test_page_embeds_extras(tmp_path):
    write_inputs(tmp_path, [known_event()])
    assert run_build(tmp_path, *with_extras(tmp_path, GOOD_EXTRAS)).returncode == 0
    assert embedded_json(built_html(tmp_path))['extras']['next'][0]['basis'] == 'ปีก่อนออก 11 พ.ย.'


def test_page_builds_without_extras(tmp_path):
    write_inputs(tmp_path, [known_event()])
    assert run_build(tmp_path).returncode == 0
    assert embedded_json(built_html(tmp_path)).get('extras') in (None, {})


def test_check_fails_when_factor_has_no_source(tmp_path):
    pg = page_of(tmp_path)
    pg['extras'] = dict(GOOD_EXTRAS, factors=[dict(GOOD_EXTRAS['factors'][0], src='')])
    assert any('ปัจจัย' in x for x in cp().check(pg))


def test_check_fails_when_next_event_has_no_basis(tmp_path):
    pg = page_of(tmp_path)
    pg['extras'] = dict(GOOD_EXTRAS, next=[{'t': 'งบ Q3', 'd': 'ราว 11 พ.ย.'}])
    assert any('เหตุการณ์ถัดไป' in x for x in cp().check(pg))


def test_public_aborts_when_extras_hold_broker_name(tmp_path):
    write_inputs(tmp_path, [known_event()])
    ex = dict(GOOD_EXTRAS, watch=[{'t': 'KSec ปรับประมาณการ', 'latest': 'x', 'signal': 'y'}])
    out = tmp_path / 'pub.html'
    r = run_build(tmp_path, '--public', '--out', str(out), *with_extras(tmp_path, ex))
    assert r.returncode != 0 and not out.exists()


# ---- repo Public: ไฟล์ที่ commit ต้องไม่มีเนื้อหาโบรกหรือข้อมูลซื้อมา ----
def committed_data_files():
    for sub in ('output/price_move', 'data'):
        for dp, dn, fn in os.walk(os.path.join(ROOT, *sub.split('/'))):
            for f in fn:
                yield os.path.join(dp, f)


def test_no_purchased_files_or_private_dirs_in_outputs():
    for p in committed_data_files():
        assert not p.lower().endswith(('.xlsx', '.xls', '.csv')), p
        assert not {'Broker', 'pack'} & set(p.replace(os.sep, '/').split('/')), p


def test_committed_outputs_hold_no_broker_names_or_target_price():
    b = bp()
    for p in committed_data_files():
        if p.endswith(('.json', '.jsonl', '.html')):
            assert b.forbidden(open(p, encoding='utf-8').read()) == [], p


# ---- dashboard.html: หน้าสรุปรวมทุกหุ้น อ่านจากหน้า Price Move ที่สร้างแล้ว ----
def make_pages(tmp_path, names=('XYZ',), **ev):
    pages = tmp_path / 'pm'
    pages.mkdir(exist_ok=True)
    write_inputs(tmp_path, [known_event(**ev)])
    for n in names:
        r = run_build(tmp_path, '--public', '--out', str(pages / f'{n}.html'))
        assert r.returncode == 0, r.stderr
    return pages


def run_index(pages, out):
    return subprocess.run([sys.executable, os.path.join(PM, 'build_index.py'), '--pages-dir', str(pages), '--out', str(out)], capture_output=True, text=True)


def test_index_lists_every_page_with_counts(tmp_path):
    pages = make_pages(tmp_path, names=('AAA', 'BBB'))
    out = tmp_path / 'dash.html'
    r = run_index(pages, out)
    assert r.returncode == 0, r.stderr
    d = embedded_json(out.read_text(encoding='utf-8'))
    assert [s['href'] for s in d['stocks']] == ['pm/AAA.html', 'pm/BBB.html']
    s = d['stocks'][0]
    assert s['day'] == 1 and s['known'] == 1 and s['draft'] == 0 and s['href'].endswith('.html')


def test_index_aborts_on_broker_name(tmp_path):
    pages = make_pages(tmp_path)
    p = pages / 'XYZ.html'
    p.write_text(p.read_text(encoding='utf-8').replace('<title>', '<title>KSec '), encoding='utf-8')
    out = tmp_path / 'dash.html'
    assert run_index(pages, out).returncode == 0  # ชื่อใน <title> ไม่ได้อยู่ใน JSON ข้อมูล
    d = json.loads(json.dumps(embedded_json(p.read_text(encoding='utf-8'))))
    d['events'][0]['why'] = 'KSec ลดราคาเป้าหมาย'
    h = p.read_text(encoding='utf-8')
    import re
    h = re.sub(r'(<script id="data" type="application/json">).*?(</script>)', lambda m: m.group(1) + json.dumps(d, ensure_ascii=False).replace('<', '\u003c') + m.group(2), h, flags=re.S)
    p.write_text(h, encoding='utf-8')
    out2 = tmp_path / 'dash2.html'
    assert run_index(pages, out2).returncode != 0 and not out2.exists()


def test_index_with_no_pages_fails(tmp_path):
    (tmp_path / 'empty').mkdir()
    assert run_index(tmp_path / 'empty', tmp_path / 'd.html').returncode != 0


# ---- ซีรีส์เสริม (ดัชนีเหล็ก สนค.) และคำตัดสินเทียบตลาดคาด ----
STEEL = {'id': 'steel_cmi', 'name': 'ดัชนีราคาเหล็ก (สนค.)', 'unit': 'ดัชนี', 'freq': 'monthly', 'note': 'ทดสอบ',
         'src': [{'src': 'https://index.tpso.go.th/api/cmi/filter', 'tier': 'A', 'accessed': '2026-11-03'}],
         'rows': [{'d': '2025-06-30', 'p': 99.9, 'yoy': -3.5}, {'d': '2025-07-31', 'p': 100.0, 'yoy': -2.2}]}


def with_series(tmp_path, *series):
    paths = []
    for i, sr in enumerate(series):
        p = tmp_path / f's{i}.json'
        p.write_text(json.dumps(sr, ensure_ascii=False), encoding='utf-8')
        paths += ['--series', str(p)]
    return paths


def test_page_embeds_series(tmp_path):
    write_inputs(tmp_path, [known_event()])
    assert run_build(tmp_path, *with_series(tmp_path, STEEL)).returncode == 0
    assert embedded_json(built_html(tmp_path))['series'][0]['rows'][1]['p'] == 100.0


def test_page_builds_without_series(tmp_path):
    write_inputs(tmp_path, [known_event()])
    assert run_build(tmp_path).returncode == 0
    assert embedded_json(built_html(tmp_path)).get('series') in (None, [])


def test_check_fails_when_series_has_no_source(tmp_path):
    pg = page_of(tmp_path)
    pg['series'] = [dict(STEEL, src=[])]
    assert any('ซีรีส์' in x for x in cp().check(pg))


def test_check_fails_when_series_url_has_no_access_date(tmp_path):
    pg = page_of(tmp_path)
    pg['series'] = [dict(STEEL, src=[{'src': 'https://x.go.th', 'tier': 'A'}])]
    assert any('วันที่เข้าถึง' in x for x in cp().check(pg))


def test_check_fails_when_series_has_duplicate_dates(tmp_path):
    pg = page_of(tmp_path)
    pg['series'] = [dict(STEEL, rows=STEEL['rows'] + [STEEL['rows'][0]])]
    assert any('ซ้ำ' in x for x in cp().check(pg))


def run_import(tmp_path, raw, **extra):
    r = tmp_path / 'raw.json'
    r.write_text(json.dumps(raw), encoding='utf-8')
    out = tmp_path / 'series.json'
    args = ['--id', 'steel_cmi', '--name', 'ดัชนีเหล็ก', '--unit', 'ดัชนี', '--freq', 'monthly', '--note', 'n', '--src', 'https://index.tpso.go.th/api/cmi/filter', '--tier', 'A', '--accessed', '2026-11-03']
    return subprocess.run([sys.executable, os.path.join(PM, 'series_import.py'), str(r), str(out), *args], capture_output=True, text=True), out


def test_series_import_uses_month_end_dates(tmp_path):
    r, out = run_import(tmp_path, [{'y': 2025, 'm': 2, 'index': 98.6, 'yoy': -3.2}, {'y': 2024, 'm': 2, 'index': 101.9, 'yoy': -3.6}])
    assert r.returncode == 0, r.stderr
    s = json.loads(out.read_text(encoding='utf-8'))
    assert [x['d'] for x in s['rows']] == ['2024-02-29', '2025-02-28'] and s['rows'][0]['p'] == 101.9 and s['src'][0]['accessed'] == '2026-11-03'


def test_series_import_rejects_duplicate_month(tmp_path):
    r, out = run_import(tmp_path, [{'y': 2025, 'm': 2, 'index': 98.6}, {'y': 2025, 'm': 2, 'index': 98.7}])
    assert r.returncode != 0 and not out.exists()


def test_series_import_rejects_missing_value(tmp_path):
    r, out = run_import(tmp_path, [{'y': 2025, 'm': 2, 'index': None}])
    assert r.returncode != 0 and not out.exists()


def test_check_fails_when_consensus_verdict_has_no_source(tmp_path):
    pg = page_of(tmp_path, events=[known_event(vs_consensus={'verdict': 'above', 'pct': 15, 'note': 'x', 'src': []})])
    assert any('ตลาดคาด' in x for x in cp().check(pg))


def test_check_fails_when_consensus_verdict_is_unknown_word(tmp_path):
    pg = page_of(tmp_path, events=[known_event(vs_consensus={'verdict': 'great', 'note': 'x', 'src': [dict(GOOD_EV)]})])
    assert any('ตลาดคาด' in x for x in cp().check(pg))


def test_check_allows_consensus_without_verdict_when_noted(tmp_path):
    pg = page_of(tmp_path, events=[known_event(vs_consensus={'verdict': None, 'note': '[ยังไม่ยืนยัน] ไม่พบรายงาน', 'src': []})])
    assert cp().check(pg) == []


def test_public_aborts_when_consensus_note_has_estimate_word(tmp_path):
    write_inputs(tmp_path, [known_event(vs_consensus={'verdict': 'above', 'pct': 5, 'note': 'ประมาณการกำไร 100 ล้านบาท', 'src': [dict(GOOD_EV)]})])
    out = tmp_path / 'pub.html'
    assert run_build(tmp_path, '--public', '--out', str(out)).returncode != 0 and not out.exists()


def test_bars_carry_quarter_label(tmp_path):
    pnl_ = {'ticker': 'XYZ', 'finance': False, 'missing': [], 'quarters': {'2025Q2': {'filed': {'date': '2025-08-06', 'est': False}, 'cur': {'np': 157.0}, 'prior': {'np': 192.0}, 'yoy': {'np': {'pct': -18.4}}, 'bridge': []}}}
    pg = page_of(tmp_path, pnl_q=pnl_)
    assert [b['q'] for b in pg['bars']] == ['2025Q2']
