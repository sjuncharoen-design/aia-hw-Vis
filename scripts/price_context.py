"""บริบทราคาของแต่ละวันที่ขยับเกิน 5%: volume, gap, ผลตลาด, beta, z-score, ราคาหลังจากนั้น แล้วจัดกลุ่มเบื้องต้นจากกติกา
usage: python scripts/price_context.py        (อ่าน output/prices_<T>.csv · events_<T>_raw.csv · calendar_<T>.json)
output: output/factors_<ชื่อ>.csv (TDEX, HRC, USDTHB, OIL จาก Yahoo) · output/context_<T>.json
ตัวแทนตลาด = TDEX.BK (กองทุน SET50) เพราะ Yahoo มี ^SET.BK แค่แท่งเดียว จึงอาจไม่สะท้อนหุ้นขนาดกลาง-เล็ก
กลุ่ม (ตัดสินตามลำดับ): xd > earnings > market > reversal > low_volume > mid_volume > high_volume · ทุกกลุ่มเป็นการอนุมานจากเวลา/ราคา ไม่ใช่สาเหตุที่ยืนยันแล้ว
"""
import csv, json, os, statistics as st, sys, urllib.request
from datetime import datetime, timedelta, timezone

sys.stdout.reconfigure(encoding='utf-8')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'output')
TICKERS = ['TURBO', 'DOHOME', 'MOSHI', 'PR9']
FACTORS = {'TDEX': 'TDEX.BK', 'HRC': 'HRC=F', 'USDTHB': 'USDTHB=X', 'OIL': 'CL=F'}
BKK = timezone(timedelta(hours=7))
MKT_MIN, RES_MAX, VOL_LOW, VOL_HIGH = 0.015, 0.05, 1.5, 3.0


def fetch_factor(name, sym):
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=5y&interval=1d'
    r = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=30))['chart']['result'][0]
    rows = [(datetime.fromtimestamp(t, BKK).date().isoformat(), c) for t, c in zip(r['timestamp'], r['indicators']['quote'][0]['close']) if c]
    with open(os.path.join(OUT, f'factors_{name}.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['date', 'close'])
        w.writerows((d, round(c, 4)) for d, c in rows)
    return rows


def context(t, mkt):
    R = [dict(d=r['date'], c=float(r['close']), o=float(r['open'] or 0), v=float(r['volume'] or 0)) for r in csv.DictReader(open(os.path.join(OUT, f'prices_{t}.csv'), encoding='utf-8'))]
    idx = {r['d']: i for i, r in enumerate(R)}
    rets = [R[i]['c'] / R[i - 1]['c'] - 1 for i in range(1, len(R))]
    pairs = [(rets[i - 1], mkt[R[i]['d']]) for i in range(1, len(R)) if R[i]['d'] in mkt and abs(rets[i - 1]) <= .05]
    mx, my = st.mean(b for _, b in pairs), st.mean(a for a, _ in pairs)
    beta = sum((a - my) * (b - mx) for a, b in pairs) / sum((b - mx) ** 2 for _, b in pairs)
    sd = st.pstdev(rets)
    cal = json.load(open(os.path.join(OUT, f'calendar_{t}.json'), encoding='utf-8'))
    first_filing = min((i['date'] for i in cal['items'] if i['kind'] in ('set_fs', 'fs_filed', 'audit_signed')), default=None)
    by = {}
    for m in cal['matches']:
        by.setdefault(m['event_date'], []).append(m)
    out, prev_i, prev_ret = {}, None, 0
    for e in csv.DictReader(open(os.path.join(OUT, f'events_{t}_raw.csv'), encoding='utf-8')):
        d, i = e['date'], idx[e['date']]
        ret = R[i]['c'] / R[i - 1]['c'] - 1
        vols = [x['v'] for x in R[max(0, i - 20):i] if x['v']]
        vr = R[i]['v'] / (sum(vols) / len(vols)) if vols and R[i]['v'] else None
        gap = R[i]['o'] / R[i - 1]['c'] - 1 if R[i]['o'] else None
        m = mkt.get(d)
        res = ret - beta * (m or 0)
        kinds = {x['item']['kind'] for x in by.get(d, [])}
        if kinds & {'xd', 'xd_stock'}:
            cls = 'xd'
        elif kinds & {'set_fs', 'fs_filed', 'audit_signed'}:
            cls = 'earnings'
        elif m is not None and abs(m) >= MKT_MIN and m * ret > 0 and abs(res) <= RES_MAX:
            cls = 'market'
        elif prev_i is not None and i - prev_i <= 2 and prev_ret * ret < 0:
            cls = 'reversal'
        elif vr is None or vr < VOL_LOW:
            cls = 'low_volume'
        elif vr >= VOL_HIGH:
            cls = 'high_volume'
        else:
            cls = 'mid_volume'
        after = lambda n: round((R[i + n]['c'] / R[i]['c'] - 1) * 100, 2) if i + n < len(R) else None
        out[d] = dict(cls=cls, vol_ratio=round(vr, 2) if vr else None, gap=round(gap * 100, 2) if gap is not None else None,
                      mkt=round(m * 100, 2) if m is not None else None, residual=round(res * 100, 2), z=round(ret / sd, 1),
                      after1=after(1), after5=after(5), before_first_filing=bool(first_filing and d < first_filing))
        prev_i, prev_ret = i, ret
    json.dump(dict(ticker=t, beta=round(beta, 2), daily_sd=round(sd * 100, 2), first_filing=first_filing, events=out),
              open(os.path.join(OUT, f'context_{t}.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return beta, sd, out


if __name__ == '__main__':
    rows = {n: fetch_factor(n, s) for n, s in FACTORS.items()}
    tdex = rows['TDEX']
    mkt = {tdex[i][0]: tdex[i][1] / tdex[i - 1][1] - 1 for i in range(1, len(tdex))}
    total = {}
    for t in TICKERS:
        beta, sd, ev = context(t, mkt)
        c = {}
        for v in ev.values():
            c[v['cls']] = c.get(v['cls'], 0) + 1
            total[v['cls']] = total.get(v['cls'], 0) + 1
        print(f'{t}: beta={beta:.2f} sd={sd * 100:.2f}% events={len(ev)} {c}')
    print(sum(total.values()), total)
