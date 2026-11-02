"""ดึงราคารายวันของหุ้นจาก Yahoo Finance แล้วหาวันที่ปิดขยับมากกว่า 5% เทียบวันก่อน
usage: python scripts/fetch_events.py TICKER OUT_DIR   (เช่น TURBO output)
เขียน OUT_DIR/prices_<T>.csv (date,close,ret_pct,open,high,low,volume) · events_<T>_raw.csv (เฉพาะวันที่ |ret| > 5%) · corp_actions_<T>.json (ปันผล/หุ้นปันผล ทุกครั้ง)
ข้อจำกัด: Yahoo `close` ปรับ split ไม่ปรับปันผล · หุ้นปันผลบางครั้ง Yahoo บันทึกเป็น split · TURBO มีข้อมูลแค่ ~12 เดือน · แหล่งเดียว ยังไม่ได้ cross-check กับ TradingView
"""
import csv, json, os, sys, urllib.request
from datetime import datetime, timedelta, timezone

T, OUT = sys.argv[1], sys.argv[2]
URL = f'https://query1.finance.yahoo.com/v8/finance/chart/{T}.BK?range=5y&interval=1d&events=div,split'
BKK = timezone(timedelta(hours=7))
o = json.load(urllib.request.urlopen(urllib.request.Request(URL, headers={'User-Agent': 'Mozilla/5.0'}), timeout=30))
r = o['chart']['result'][0]
q = r['indicators']['quote'][0]
day = lambda ts: datetime.fromtimestamp(int(ts), BKK).date().isoformat()
rows = [(day(t), q['close'][i], q['open'][i], q['high'][i], q['low'][i], q['volume'][i]) for i, t in enumerate(r['timestamp']) if q['close'][i]]
ev = r.get('events', {})
divs = {day(k): v['amount'] for k, v in (ev.get('dividends') or {}).items()}
splits = {day(k): f"{v['numerator']:g}:{v['denominator']:g}" for k, v in (ev.get('splits') or {}).items()}
os.makedirs(OUT, exist_ok=True)
rnd = lambda v: round(v, 2) if v else ''
n = 0
with open(os.path.join(OUT, f'prices_{T}.csv'), 'w', newline='', encoding='utf-8') as f, \
     open(os.path.join(OUT, f'events_{T}_raw.csv'), 'w', newline='', encoding='utf-8') as g:
    w, e = csv.writer(f), csv.writer(g)
    w.writerow(['date', 'close', 'ret_pct', 'open', 'high', 'low', 'volume']); e.writerow(['date', 'close', 'prev_close', 'ret_pct', 'xd_dividend', 'xd_split'])
    prev = None
    for d, c, op, hi, lo, vol in rows:
        ret = round((c / prev - 1) * 100, 2) if prev else ''
        w.writerow([d, round(c, 2), ret, rnd(op), rnd(hi), rnd(lo), vol or 0])
        if prev and abs((c / prev - 1) * 100) > 5:
            e.writerow([d, round(c, 2), round(prev, 2), ret, divs.get(d, ''), splits.get(d, '')])
            n += 1
        prev = c
json.dump(dict(dividends=divs, splits=splits), open(os.path.join(OUT, f'corp_actions_{T}.json'), 'w', encoding='utf-8'), indent=1)
print(f'{T}: bars={len(rows)} {rows[0][0]}..{rows[-1][0]} events>5%={n} dividends={len(divs)} splits={splits}')
