"""ดึงราคาปิดรายวันของหุ้นจาก Yahoo Finance แล้วหาวันที่ปิดขยับมากกว่า 5% เทียบวันก่อน
usage: python scripts/fetch_events.py TICKER OUT_DIR   (เช่น TIDLOR output)
เขียน OUT_DIR/prices_<TICKER>.csv (date,close,ret_pct) และ OUT_DIR/events_<TICKER>_raw.csv (เฉพาะวันที่ |ret| > 5%)
ข้อจำกัด: Yahoo `close` ปรับ split ไม่ปรับปันผล · TIDLOR มีข้อมูลแค่ ~17 เดือน (Yahoo) · แหล่งเดียว ยังไม่ได้ cross-check กับ TradingView
"""
import csv, json, os, sys, urllib.request
from datetime import datetime, timedelta, timezone

T, OUT = sys.argv[1], sys.argv[2]
URL = f'https://query1.finance.yahoo.com/v8/finance/chart/{T}.BK?range=5y&interval=1d&events=div'
BKK = timezone(timedelta(hours=7))
o = json.load(urllib.request.urlopen(urllib.request.Request(URL, headers={'User-Agent': 'Mozilla/5.0'}), timeout=30))
r = o['chart']['result'][0]
rows = [(datetime.fromtimestamp(t, BKK).date().isoformat(), c) for t, c in zip(r['timestamp'], r['indicators']['quote'][0]['close']) if c]
divs = {datetime.fromtimestamp(v['date'], BKK).date().isoformat(): v['amount'] for v in (r.get('events', {}).get('dividends') or {}).values()}
os.makedirs(OUT, exist_ok=True)
with open(os.path.join(OUT, f'prices_{T}.csv'), 'w', newline='', encoding='utf-8') as f, \
     open(os.path.join(OUT, f'events_{T}_raw.csv'), 'w', newline='', encoding='utf-8') as g:
    w, e = csv.writer(f), csv.writer(g)
    w.writerow(['date', 'close', 'ret_pct']); e.writerow(['date', 'close', 'prev_close', 'ret_pct', 'xd_dividend'])
    prev = None
    for d, c in rows:
        ret = round((c / prev - 1) * 100, 2) if prev else ''
        w.writerow([d, round(c, 2), ret])
        if prev and abs((c / prev - 1) * 100) > 5:
            e.writerow([d, round(c, 2), round(prev, 2), ret, divs.get(d, '')])
        prev = c
print(f'{T}: bars={len(rows)} {rows[0][0]}..{rows[-1][0]} events>5%={sum(1 for i in range(1,len(rows)) if abs((rows[i][1]/rows[i-1][1]-1)*100)>5)} dividends={divs}')
