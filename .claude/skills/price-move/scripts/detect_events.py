"""Detect strong weekly price moves from price_valuation.json -> events_raw.json.
usage: python detect_events.py PRICE_JSON OUT_JSON [--mode daily|weekly|both] [--years 5] [--prev EVENTS_JSON] [--week 5] [--trend 15] [--max-trend-w 52]
  PRICE_JSON : list of {d, p, set} closes (d = bar date, oldest first) — daily closes for --mode daily, weekly for --mode weekly
  --mode     : daily (default) = one event per trading day whose close moved > --week % vs the previous close;
               both = daily + window events (skill price-move);
               weekly = legacy (weekly bars, merged runs + zigzag trend legs)
  --years    : keep only events inside the last N years counted from the newest bar (default 5; 0 = all)
  --prev     : existing events.json — analysis fields (why/evidence/conf/...) are carried over by date
kinds:
  day   : (daily mode) one close-to-close move with |ret| > --week %; market/sector comparison is informational only
  window: (both mode) close vs the close 5 or 6 trading days earlier moved > 10%; same-direction days with overlapping ranges merge
  week  : (weekly mode) one week with |ret| >= --week %, consecutive same-direction weeks merged into one event
  trend : (weekly mode) zigzag leg with |ret| >= --trend % spanning 2..--max-trend-w weeks
market_hint = True when the stock moved roughly with SET (|rel| < 2pp while |set_ret| >= 3%)
sector_hint = same test against the sector index when PRICE_JSON rows carry `sec` (e.g. SET:PAPER close)
"""
import argparse, json, os, sys
from datetime import date, timedelta

KEEP = ('why', 'evidence', 'conf', 'cat', 'driver', 'metric_move', 'sources_checked', 'context', 'from_deepdive',
        'what', 'direction_match', 'pnl_quarter', 'pnl_note', 'pnl_links', 'market_view', 'market_view_public', 'market_view_src', 'outlook', 'hypothesis', 'next_check', 'conflicts')


def pct(a, b):
    return round((b / a - 1) * 100, 1) if a else None


def _end(d):
    return (date.fromisoformat(d) + timedelta(days=6)).isoformat()


def _event(P, i0, i1, kind):
    """move from close of bar i0-1 to close of bar i1 (i0..i1 inclusive)."""
    a, b = P[i0 - 1], P[i1]
    ret, sret = pct(a['p'], b['p']), pct(a.get('set'), b.get('set')) if a.get('set') and b.get('set') else None
    rel = round(ret - sret, 1) if sret is not None else None
    cret = pct(a['sec'], b['sec']) if a.get('sec') and b.get('sec') else None
    crel = round(ret - cret, 1) if cret is not None else None
    ctx = {k: P[i1][k] for k in ('vr', 'gap') if P[i1].get(k) is not None}
    return {'date': P[i0]['d'], 'end': _end(P[i1]['d']), 'kind': kind, 'span_w': i1 - i0 + 1,
            **({'vol_ratio': ctx['vr']} if 'vr' in ctx else {}), **({'gap': ctx['gap']} if 'gap' in ctx else {}),
            'dir': 'up' if ret > 0 else 'down', 'ret': ret, 'price_from': a['p'], 'price_to': b['p'],
            'set_ret': sret, 'rel': rel, 'sec_ret': cret, 'rel_sec': crel,
            'market_hint': bool(sret is not None and abs(rel) < 2 and abs(sret) >= 3),
            'sector_hint': bool(cret is not None and abs(crel) < 2 and abs(cret) >= 3)}


def within_years(events, P, years):
    """events dated inside the last `years` years before the newest price bar (0/None = keep all)."""
    if not years or not P:
        return events
    last = date.fromisoformat(P[-1]['d'])
    try:
        cut = last.replace(year=last.year - years)
    except ValueError:
        cut = last.replace(year=last.year - years, day=28)
    return [e for e in events if e['date'] >= cut.isoformat()]


def daily_events(P, thr):
    """one event per day whose close is more than thr% away from the previous close (strictly greater)."""
    out = []
    for i in range(1, len(P)):
        a_, b_ = P[i - 1]['p'], P[i]['p']
        raw = round((b_ / a_ - 1) * 100, 6) if a_ else None  # unrounded, so a 5.04% day counts and an exact 5.0% tick move does not
        if raw is not None and abs(raw) > thr:
            e = _event(P, i, i, 'day')
            e['end'] = P[i]['d']
            e['ret'] = round(raw, 2)
            if e['set_ret'] is not None:
                e['rel'] = round(raw - e['set_ret'], 1)
            out.append(e)
    return out


def window_events(P, thr=10.0, spans=(5, 6)):
    """runs of days whose close moved more than thr% against the close spans[*] bars earlier; same-direction days with overlapping ranges merge."""
    hits = []
    for i in range(len(P)):
        best = None
        for n in spans:
            if i - n >= 0 and P[i - n]['p']:
                raw = round((P[i]['p'] / P[i - n]['p'] - 1) * 100, 6)
                if abs(raw) > thr and (best is None or abs(raw) > abs(best[0])):
                    best = (raw, i - n)
        if best:
            hits.append((i, best[0], best[1]))
    runs = []
    for h in hits:  # same direction and overlapping range (this day's base is not after the run's last flagged day)
        if runs and h[2] + 1 <= runs[-1][-1][0] and runs[-1][-1][1] * h[1] > 0:
            runs[-1].append(h)
        else:
            runs.append([h])
    out = []
    for run in runs:
        peak, raw, base = max(run, key=lambda h: abs(h[1]))
        e = _event(P, base + 1, peak, 'window')
        e.update(date=P[min(h[2] for h in run) + 1]['d'], end=P[run[-1][0]]['d'], ret=round(raw, 2), base_date=P[base]['d'], peak_date=P[peak]['d'])
        if e['set_ret'] is not None:
            e['rel'] = round(raw - e['set_ret'], 1)
        out.append(e)
    return out


def add_xd(events, actions):
    """events whose date range holds an ex-date get `xd`: [{date, kind, text, pct?}] — context only, never a cause by itself.
    pct = cash dividend / price before the ex-date (the mechanical drop). Stock dividends/splits are already adjusted in the price series."""
    for e in events:
        hit = []
        for a in actions:
            if e['date'] <= a['date'] <= e['end']:
                x = dict(date=a['date'], kind=a['kind'])
                if a['kind'] == 'cash' and a.get('amount') and a.get('price_before'):
                    x['pct'] = round(a['amount'] / a['price_before'] * 100, 2)
                    x['text'] = f"XD ปันผล {a['amount']:g} บาท ({x['pct']}% ของราคาก่อน XD)"
                else:
                    x['text'] = f"XD หุ้นปันผล {a.get('ratio') or ''}".strip()
                hit.append(x)
        if hit:
            e['xd'] = hit


def link_days(events):
    """window events list the same-direction day events inside their range; those days point back."""
    days = [e for e in events if e['kind'] == 'day']
    for w in (e for e in events if e['kind'] == 'window'):
        w['days'] = []
        for d in days:
            if w['date'] <= d['date'] <= w['end'] and d['ret'] * w['ret'] > 0:
                w['days'].append(f"{d['date']}_day")
                d['in_window'] = f"{w['date']}_window"


def weekly_events(P, thr):
    out, i = [], 1
    while i < len(P):
        r = pct(P[i - 1]['p'], P[i]['p'])
        if r is not None and abs(r) >= thr:
            j = i
            while j + 1 < len(P):
                r2 = pct(P[j]['p'], P[j + 1]['p'])
                if r2 is None or abs(r2) < thr or (r2 > 0) != (r > 0):
                    break
                j += 1
            out.append(_event(P, i, j, 'week'))
            i = j + 1
        else:
            i += 1
    return out


def trend_events(P, thr, max_w):
    """zigzag on closes: a pivot is confirmed once price reverses >= thr% from the running extreme."""
    x = [r['p'] for r in P]
    piv, d, hi, lo, ext = [], 0, 0, 0, 0
    for i in range(1, len(x)):
        if d == 0:
            hi = i if x[i] > x[hi] else hi
            lo = i if x[i] < x[lo] else lo
            if pct(x[lo], x[i]) >= thr:
                piv, d, ext = [lo], 1, i
            elif pct(x[hi], x[i]) <= -thr:
                piv, d, ext = [hi], -1, i
        elif d * (x[i] - x[ext]) > 0:
            ext = i
        elif d * pct(x[ext], x[i]) <= -thr:
            piv.append(ext)
            d, ext = -d, i
    if d:
        piv.append(ext)
    out = []
    for a, b in zip(piv, piv[1:]):
        if b - a >= 2 and b - a <= max_w and abs(pct(P[a]['p'], P[b]['p'])) >= thr:
            out.append(_event(P, a + 1, b, 'trend'))
    return out


def detect(P, week=5.0, trend=15.0, max_trend_w=52):
    ev = weekly_events(P, week) + trend_events(P, trend, max_trend_w)
    seen, res = set(), []
    for e in sorted(ev, key=lambda e: (e['date'], e['kind'] != 'week')):
        k = (e['date'], e['end'])
        if k not in seen:
            seen.add(k)
            res.append(e)
    return res


def _overlap(a, b):
    s, e = max(a['date'], b['date']), min(a['end'], b['end'])
    if s > e:
        return 0.0
    span = lambda x: (date.fromisoformat(x['end']) - date.fromisoformat(x['date'])).days + 1
    return ((date.fromisoformat(e) - date.fromisoformat(s)).days + 1) / max(span(a), span(b))


CONF_RANK = {'high': 3, 'mid': 2, 'low': 1}


def _as_list(ev):
    if not ev:
        return []
    return ev if isinstance(ev, list) else [{'src': ev}]


def carry_over(new, prev, keep_low=False):
    """copy analysis fields from prev events of the same direction that overlap >=50% or lie inside the
    new event (a merged multi-week event can absorb several old ones: highest conf is the base, the
    others' why/evidence are appended). prev events matching nothing but already researched (mid/high, or with
    keep_low any draft carrying hypothesis/next_check) are kept as kind='manual'."""
    prev = [dict(p, end=p.get('end') or _end(p['date'])) for p in prev]
    used = set()
    for e in new:
        hit = [i for i, p in enumerate(prev) if i not in used and (p.get('ret', 0) > 0) == (e['ret'] > 0)
               and (_overlap(e, p) >= 0.5 or e['date'] <= p['date'] and p['end'] <= e['end'])]
        if not hit:
            continue
        hit.sort(key=lambda i: (CONF_RANK.get(prev[i].get('conf'), 0), _overlap(e, prev[i])), reverse=True)
        used.update(hit)
        base = prev[hit[0]]
        e.update({k: base[k] for k in KEEP if k in base})
        for i in hit[1:]:
            o = prev[i]
            if o.get('why'):
                e['why'] = f"{e.get('why', '')} · [{o['date']}] {o['why']}".strip(' ·')
            e['evidence'] = _as_list(e.get('evidence')) + _as_list(o.get('evidence'))
            e['sources_checked'] = sorted(set(e.get('sources_checked', [])) | set(o.get('sources_checked', [])))
    for i, p in enumerate(prev):
        if i not in used and (p.get('conf') in ('mid', 'high') or keep_low and (p.get('hypothesis') or p.get('next_check'))):
            new.append(dict(p, kind='manual', market_hint=p.get('market_hint', False)))
    return sorted(new, key=lambda e: e['date'])


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('price'); ap.add_argument('out'); ap.add_argument('--prev')
    ap.add_argument('--mode', choices=('daily', 'weekly', 'both'), default='daily')
    ap.add_argument('--years', type=int, default=5)
    ap.add_argument('--recon', help='price_recon.json from price_daily.py — sets price_mismatch / price_verified on every event')
    ap.add_argument('--week', type=float, default=5.0); ap.add_argument('--trend', type=float, default=15.0)
    ap.add_argument('--max-trend-w', type=int, default=52)
    ap.add_argument('--xd', help='JSON list of {date, kind, amount?, ratio?, price_before?} (corp_actions.py) — adds `xd` context to events whose range holds an ex-date')
    a = ap.parse_args()
    P = [r for r in json.load(open(a.price, encoding='utf-8')) if r.get('p')]
    if a.mode == 'both':
        ev = daily_events(P, a.week) + window_events(P)
    else:
        ev = daily_events(P, a.week) if a.mode == 'daily' else detect(P, a.week, a.trend, a.max_trend_w)
    ev = within_years(ev, P, a.years)
    if a.prev and not os.path.exists(a.prev):
        print(f'NOTE: --prev {a.prev} not found — treating this as a first run', file=sys.stderr)
        a.prev = None
    if a.prev:
        prev = json.load(open(a.prev, encoding='utf-8'))
        prev = prev['events'] if isinstance(prev, dict) else prev
        if a.mode == 'daily':  # weekly/trend analyses describe a different window — never copy them onto a single day
            prev = [p for p in prev if p.get('kind') in ('day', 'manual')]
        if a.mode == 'both':  # carry per kind, otherwise a window absorbs the analysis of the days inside it
            ev = carry_over([e for e in ev if e['kind'] == 'day'], [p for p in prev if p.get('kind') in ('day', 'manual')], keep_low=True) + \
                carry_over([e for e in ev if e['kind'] == 'window'], [p for p in prev if p.get('kind') == 'window'], keep_low=True)
            ev.sort(key=lambda e: (e['date'], e['kind']))
        else:
            ev = carry_over(ev, prev)
    if a.mode == 'both':
        link_days(ev)
    if a.xd and os.path.exists(a.xd):
        add_xd(ev, json.load(open(a.xd, encoding='utf-8')))
    if a.recon:
        rc = json.load(open(a.recon, encoding='utf-8'))
        bad, lo, hi = {m['d'] for m in rc.get('mismatches', [])}, rc.get('verified_from'), rc.get('verified_to')
        for e in ev:
            hit = any(e['date'] <= d <= e['end'] for d in bad) if e['kind'] == 'window' else e['date'] in bad
            e['price_mismatch'] = hit
            e['price_verified'] = bool(lo and hi and lo <= e['date'] and e['end' if e['kind'] == 'window' else 'date'] <= hi and not hit)
    json.dump(ev, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    n_w = sum(e['kind'] in ('week', 'day') for e in ev)
    print(f'events={len(ev)} {a.mode}={n_w} trend={len(ev) - n_w} market_hint={sum(e["market_hint"] for e in ev)} '
          f'carried={sum("conf" in e for e in ev)} -> {a.out}')
