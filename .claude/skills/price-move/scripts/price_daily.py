"""Daily closes from TWO independent sources + a reconciliation report (price_daily.json, price_recon.json).
usage: python price_daily.py TICKER OUT_DIR --tv TV_JSON [--tv-set TV_SET_JSON] [--yahoo-file FILE | --yahoo-symbol KTC.BK]
                             [--years 5] [--compare returns|levels] [--tol 0.5] [--ret-tol 0.5]
  --tv         : TradingView MCP `get_ohlcv(symbol="SET:<T>", interval="1D", count=N)` result saved as JSON
                 (the raw tool result {"bars":[{t,o,h,l,c,v}]} or just the bars list). The script cannot call MCP itself and
                 every bar passes through the agent's context (~70 chars/bar): 5 years ~ 1,260 bars. Yahoo is fetched by this
                 script (zero tokens) but its history can be SHORT (TIDLOR: 353 bars only) — see PRIMARY below.
  --tv-set     : same for `SET:SET` (adds the `set` field used for informational vs-SET columns)
  --single-source : Yahoo only, no --tv needed. Must be asked for explicitly: recon status = single_source, every day v=false
  --market-file   : local JSON of daily SET index closes ({"points": {date: close}} or {date: close}) that fills `set` when --tv-set is
                    absent. Preferred over --market-symbol (e.g. data/set_index_history.json, 5 years of the real index)
  --market-symbol : Yahoo symbol that fills `set` when neither --tv-set nor --market-file is given (e.g. TDEX.BK, because ^SET.BK has no history)
  Yahoo volume/open are used (when the Yahoo file/response carries them) to add `vr` (volume / mean of the previous 20 days) and
  `gap` (open vs previous close, %) to every primary row from the 21st bar on
  --yahoo-file : Yahoo chart API JSON saved to disk (offline / tests). Default: fetch
                 https://query1.finance.yahoo.com/v8/finance/chart/<T>.BK?range=<years>y&interval=1d
  --years      : analysis window ending at the newest bar (default 5)
  --compare    : returns (default) = compare each day's % return, tolerant of a level offset between sources (TradingView may
                 adjust history for dividends, Yahoo `close` does not) · levels = also require close within --tol %
  --ret-tol    : max |daily-return difference| in percentage points. An ex-dividend day shows up here on purpose: one source
                 treats the dividend as a price drop, the other does not — look at that event as `dividend_xd`
PRIMARY = the source whose history covers the whole window (Yahoo when both do: free). Only primary dates enter price_daily.json
(levels of two adjustment bases are never mixed). If neither covers the window, the longer one is used and recon says so.
writes OUT_DIR/price_daily.json : [{d, p, set?, src, v}] oldest first, window only. v=true when the other source agrees that day
       OUT_DIR/price_recon.json : {primary, secondary, window_from, covers_window, n_*, verified_from/to, level_ratio{...},
                                   mismatches[], only_other[], status}
Dates outside [verified_from, verified_to] are single-source: detect_events marks those events price_verified=false.
exit 1 when a source is missing/empty so a gap is never silent.
"""
import argparse, json, os, statistics, sys, urllib.request
from datetime import date, datetime, timedelta, timezone

BKK = timezone(timedelta(hours=7))
UA = {'User-Agent': 'Mozilla/5.0'}


def bkk_date(ts):
    return datetime.fromtimestamp(ts, BKK).date().isoformat()


def load_tv(path):
    """-> {date: close}"""
    o = json.load(open(path, encoding='utf-8'))
    bars = o.get('bars') if isinstance(o, dict) else o
    return {bkk_date(b['t']): float(b['c']) for b in bars or [] if b.get('c') is not None}


def parse_yahoo(o):
    """Yahoo chart JSON -> {date: close} (`close`: split-adjusted, not dividend-adjusted)"""
    r = o['chart']['result'][0]
    ts, cl = r.get('timestamp') or [], r['indicators']['quote'][0]['close']
    return {bkk_date(t): float(c) for t, c in zip(ts, cl) if c is not None}


def fetch_yahoo_json(symbol, years=5):
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={years}y&interval=1d'
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as f:
        return json.load(f)


def fetch_yahoo(symbol, years=5):
    return parse_yahoo(fetch_yahoo_json(symbol, years))


def window_start(m, years):
    """first date of the analysis window = newest bar minus `years` years."""
    last = date.fromisoformat(max(m))
    try:
        return last.replace(year=last.year - years).isoformat()
    except ValueError:  # 29 Feb
        return last.replace(year=last.year - years, day=28).isoformat()


def covers(m, start, slack_days=7):
    return bool(m) and min(m) <= (date.fromisoformat(start) + timedelta(days=slack_days)).isoformat()


def pick_primary(tv, yh, years=5):
    """-> (name, window_from, covers_window). Yahoo preferred when it covers the window (free)."""
    start = window_start(tv if max(tv) >= max(yh) else yh, years)
    if covers(yh, start):
        return 'yahoo', start, True
    if covers(tv, start):
        return 'tv', start, True
    return ('yahoo' if min(yh) <= min(tv) else 'tv'), start, False


def _rets(m):
    ds = sorted(m)
    return {d: (m[d] / m[p] - 1) * 100 for p, d in zip(ds, ds[1:]) if m[p]}


def reconcile(tv, yh, tol=0.5, ret_tol=0.5, compare='returns', start=None):
    start = start or ''
    both = [d for d in sorted(set(tv) & set(yh)) if d >= start]
    rt, ry = _rets(tv), _rets(yh)
    mism = []
    for d in both:
        diff = (tv[d] / yh[d] - 1) * 100 if yh[d] else None
        rd = abs(rt[d] - ry[d]) if d in rt and d in ry else 0.0
        level_bad = compare == 'levels' and (diff is None or abs(diff) > tol)
        if level_bad or rd > ret_tol:
            mism.append({'d': d, 'tv': tv[d], 'yahoo': yh[d], 'diff_pct': None if diff is None else round(diff, 2),
                         'ret_diff_pp': round(rd, 2)})
    ratios = [tv[d] / yh[d] for d in both if yh[d]]
    lo = both[0] if both else None
    hi = both[-1] if both else None
    in_rng = lambda d: lo is not None and lo <= d <= hi
    return {'compare': compare, 'tol_pct': tol, 'ret_tol_pp': ret_tol, 'n_tv': len(tv), 'n_yahoo': len(yh), 'n_both': len(both),
            'verified_from': lo, 'verified_to': hi,
            'level_ratio': ({'median': round(statistics.median(ratios), 4), 'min': round(min(ratios), 4), 'max': round(max(ratios), 4)}
                            if ratios else None),
            'mismatches': mism,
            'only_tv': sorted(d for d in tv if d not in yh and in_rng(d)),
            'only_yahoo': sorted(d for d in yh if d not in tv and in_rng(d)),
            'status': 'ok' if not mism else 'mismatch'}


def parse_yahoo_extra(o):
    """Yahoo chart JSON -> ({date: volume}, {date: open}) for bars that have a close"""
    r = o['chart']['result'][0]
    q = r['indicators']['quote'][0]
    ts, cl = r.get('timestamp') or [], q['close']
    vol, opn = q.get('volume') or [None] * len(ts), q.get('open') or [None] * len(ts)
    v = {bkk_date(t): float(x) for t, c, x in zip(ts, cl, vol) if c is not None and x}
    p = {bkk_date(t): float(x) for t, c, x in zip(ts, cl, opn) if c is not None and x}
    return v, p


def load_market(path):
    o = json.load(open(path, encoding='utf-8'))
    pts = o.get('points') if isinstance(o, dict) and 'points' in o else o
    return {d: float(c) for d, c in pts.items() if c}


def add_context(rows, vol, opn):
    """vr = volume / mean(volume of the previous 20 bars) · gap = open / previous close - 1 (%)"""
    for i, r in enumerate(rows):
        if i >= 20 and r['d'] in vol:
            base = [vol[x['d']] for x in rows[i - 20:i] if x['d'] in vol]
            if len(base) >= 10 and sum(base):
                r['vr'] = round(vol[r['d']] / (sum(base) / len(base)), 2)
        if i >= 1 and r['d'] in opn and rows[i - 1]['p']:
            r['gap'] = round((opn[r['d']] / rows[i - 1]['p'] - 1) * 100, 2)
    return rows


def build_series(primary, other, start, setmap=None, bad=()):
    """primary = {date: close}. Only primary dates, only the window. v = the other source agrees on that date."""
    rows = []
    for d in sorted(d for d in primary if d >= start):
        row = {'d': d, 'p': primary[d], 'src': '', 'v': d in other and d not in bad}
        if setmap and d in setmap:
            row['set'] = setmap[d]
        rows.append(row)
    return rows


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('ticker'); ap.add_argument('out'); ap.add_argument('--tv'); ap.add_argument('--tv-set')
    ap.add_argument('--single-source', action='store_true'); ap.add_argument('--market-symbol'); ap.add_argument('--market-file')
    ap.add_argument('--yahoo-file'); ap.add_argument('--yahoo-symbol')
    ap.add_argument('--tol', type=float, default=0.5); ap.add_argument('--ret-tol', type=float, default=0.5)
    ap.add_argument('--years', type=int, default=5); ap.add_argument('--compare', choices=('returns', 'levels'), default='returns')
    a = ap.parse_args()
    if not a.tv and not a.single_source:
        ap.error('--tv is required unless --single-source is given')
    tv = load_tv(a.tv) if a.tv else {}
    if a.yahoo_file:
        yraw = json.load(open(a.yahoo_file, encoding='utf-8'))
        yh = parse_yahoo(yraw)
    else:
        try:
            yraw = fetch_yahoo_json(a.yahoo_symbol or f'{a.ticker}.BK', a.years)
            yh = parse_yahoo(yraw)
        except Exception as ex:  # noqa: BLE001 — report, never fall back silently
            print(f'FAIL: Yahoo unavailable ({ex}); only one source — events cannot be cross-checked', file=sys.stderr)
            sys.exit(1)
    if (not tv and not a.single_source) or not yh:
        print(f'FAIL: empty source (tv={len(tv)} yahoo={len(yh)})', file=sys.stderr)
        sys.exit(1)
    if tv:
        name, start, full = pick_primary(tv, yh, a.years)
        rec = reconcile(tv, yh, a.tol, a.ret_tol, a.compare, start)
    else:
        name, start = 'yahoo', window_start(yh, a.years)
        full = covers(yh, start)
        rec = {'compare': None, 'n_tv': 0, 'n_yahoo': len(yh), 'n_both': 0, 'verified_from': None, 'verified_to': None, 'level_ratio': None,
               'mismatches': [], 'only_tv': [], 'only_yahoo': [], 'status': 'single_source'}
    primary, other = (yh, tv) if name == 'yahoo' else (tv, yh)
    rec.update({'primary': name, 'secondary': ('tv' if name == 'yahoo' else 'yahoo') if tv else None, 'window_from': start, 'covers_window': full,
                'bars_in_window': sum(d >= start for d in primary)})
    setmap = load_tv(a.tv_set) if a.tv_set else None
    rec['market_source'] = 'SET:SET' if a.tv_set else None
    if not setmap and a.market_file:
        setmap = load_market(a.market_file)
        rec['market_source'] = os.path.basename(a.market_file)
    if not setmap and a.market_symbol:
        try:
            setmap = fetch_yahoo(a.market_symbol, a.years)
            rec['market_source'] = a.market_symbol
        except Exception as ex:  # noqa: BLE001 — market comparison is optional, but say so
            print(f'WARN: market symbol {a.market_symbol} unavailable ({ex})', file=sys.stderr)
    rec['only_other'] = sorted(d for d in other if d >= start and d not in primary and (rec['verified_from'] or '') <= d <= (rec['verified_to'] or ''))
    os.makedirs(a.out, exist_ok=True)
    series = build_series(primary, other, start, setmap, {m['d'] for m in rec['mismatches']})
    if name == 'yahoo':
        add_context(series, *parse_yahoo_extra(yraw))
    for r in series:
        r['src'] = name
    json.dump(series, open(os.path.join(a.out, 'price_daily.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    json.dump(rec, open(os.path.join(a.out, 'price_recon.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    unver = sum(not r['v'] for r in series)
    print(f"primary={name} window={start}..{max(primary)} bars={len(series)} covers_window={full} | other source both={rec['n_both']} "
          f"mismatches={len(rec['mismatches'])} unverified_days={unver} level_ratio={rec['level_ratio']} -> {a.out}")
    if not full:
        print(f'WARN: no source covers the {a.years}-year window — price_daily.json starts at {min(primary)}', file=sys.stderr)
