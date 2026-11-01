"""ปฏิทินเปิดเผยข้อมูลของบริษัท จากเอกสารในเครื่อง (อ่านผ่าน .extracted.md / ชื่อไฟล์ / ข่าว SET) แล้วเทียบกับวันที่ราคาขยับ >5%
usage: python scripts/disclosure_calendar.py TICKER [--raw DIR]
output: output/calendar_<T>.json = {items:[{date,time?,kind,src}], matches:[{event_date, rel, item}]}
kind: fs_filed (ยื่นงบต่อ SET จากชื่อไฟล์ FIN<DDMMYYYY><hhmm..>) · audit_signed (วันลงนามรายงานผู้สอบบัญชี = วันกรรมการอนุมัติงบ)
      oppday (วันประชุมนักวิเคราะห์ จากหัวไฟล์ 'meeting YYYY-MM-DD') · set_news (ข่าว SET ที่เก็บไว้) · xd (Yahoo dividends)
rel: ความสัมพันธ์วันของ event (T) กับรายการ: 'T-1' = รายการเกิดก่อนหนึ่งวัน ... 'T' = วันเดียวกัน, 'T+1' = วันถัดไป
หมายเหตุ: งบที่ยื่นหลัง ~16:30 น. กระทบราคาวันทำการถัดไป
"""
import argparse, csv, glob, json, os, re, sys
from datetime import date, datetime, timedelta

sys.stdout.reconfigure(encoding='utf-8')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'output')
TH = ['มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน', 'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม']
EN = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']


def parse_date_text(s):
    """วันที่สุดท้ายที่พบในข้อความ (ไทย/อังกฤษ, พ.ศ./ค.ศ.)"""
    best = None
    for m in re.finditer(r'(\d{1,2})\s*(' + '|'.join(TH) + '|' + '|'.join(EN) + r')\s*(?:พ\.ศ\.\s*)?(\d{4})', s):
        mon = (TH + EN).index(m.group(2)) % 12 + 1
        y = int(m.group(3))
        y = y - 543 if y > 2400 else y
        try:
            best = date(y, mon, int(m.group(1)))
        except ValueError:
            pass
    return best


def build(raw, t):
    items = []
    for p in glob.glob(os.path.join(raw, '**', '*'), recursive=True):
        if not os.path.isfile(p):
            continue
        name, rel = os.path.basename(p), os.path.relpath(p, raw).replace('\\', '/')
        m = re.search(r'FIN(\d{2})(\d{2})(\d{4})(\d{2})(\d{2})', name)
        if m and not name.lower().endswith('.extracted.md'):
            try:
                items.append(dict(date=date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat(), time=f'{m.group(4)}:{m.group(5)}', kind='fs_filed', src=rel))
            except ValueError:
                pass
        if 'auditreport' in name.lower() and name.endswith('.extracted.md'):
            d = parse_date_text(open(p, encoding='utf-8', errors='ignore').read()[-3500:])
            if d:
                items.append(dict(date=d.isoformat(), kind='audit_signed', src=rel))
        if 'Earning' in rel and name.endswith('.txt'):
            m = re.search(r'meeting (\d{4}-\d{2}-\d{2})', open(p, encoding='utf-8', errors='ignore').read(400))
            if m:
                items.append(dict(date=m.group(1), kind='oppday', src=rel))
        if name.startswith('set_news_') and name.endswith('.jsonl'):
            for ln, line in enumerate(open(p, encoding='utf-8', errors='ignore'), 1):
                try:
                    n = json.loads(line)
                    items.append(dict(date=n['datetime'][:10], time=n['datetime'][11:16], kind='set_news', src=rel, title=n.get('title', '')[:120], url=n.get('url', '')))
                except (ValueError, KeyError):
                    pass
    # dedupe
    seen, uniq = set(), []
    for i in sorted(items, key=lambda i: (i['date'], i['kind'], i.get('time', ''))):
        k = (i['date'], i['kind'], i.get('time'))
        if k not in seen:
            seen.add(k)
            uniq.append(i)
    return uniq


def match(items, events):
    out = []
    for e in events:
        t0 = date.fromisoformat(e['date'])
        for i in items:
            dd = (date.fromisoformat(i['date']) - t0).days
            if -1 <= dd <= 1:
                out.append(dict(event_date=e['date'], rel={-1: 'T-1', 0: 'T', 1: 'T+1'}[dd], item=i))
    return out


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('ticker'); ap.add_argument('--raw', default='D:/3_Stocks_Analyst/Routines5_rawdata')
    a = ap.parse_args()
    events = list(csv.DictReader(open(os.path.join(OUT, f'events_{a.ticker}_raw.csv'), encoding='utf-8')))
    items = build(os.path.join(a.raw, a.ticker), a.ticker)
    for e in events:
        if e.get('xd_dividend'):
            items.append(dict(date=e['date'], kind='xd', src='Yahoo dividends', amount=e['xd_dividend']))
    m = match(items, events)
    json.dump(dict(ticker=a.ticker, items=items, matches=m), open(os.path.join(OUT, f'calendar_{a.ticker}.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    kinds = {}
    for i in items:
        kinds[i['kind']] = kinds.get(i['kind'], 0) + 1
    ev_hit = {x['event_date'] for x in m}
    print(f"{a.ticker}: calendar items={len(items)} {kinds} · events with a disclosure within T-1..T+1 = {len(ev_hit)}/{len(events)}")
