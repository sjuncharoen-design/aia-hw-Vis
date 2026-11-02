"""ปฏิทินเปิดเผยข้อมูลของบริษัท จากเอกสารในเครื่อง (อ่านผ่าน .extracted.md / ชื่อไฟล์ / ชื่อโฟลเดอร์ / ข่าว SET) แล้วเทียบกับวันที่ราคาขยับ >5%
usage: python scripts/disclosure_calendar.py TICKER [--raw DIR]   (default DIR = D:/3_Stocks_Analyst/AllCompany)
input : output/events_<T>_raw.csv · prices_<T>.csv · corp_actions_<T>.json (จาก fetch_events.py)
output: output/calendar_<T>.json = {items:[{date,time?,kind,src,react_date?}], matches:[{event_date, rel, item}]}
kind: fs_filed (ยื่นงบต่อ SET จากชื่อไฟล์/โฟลเดอร์ FIN<DDMMYYYY><hhmm..>) · audit_signed (วันลงนามรายงานผู้สอบบัญชี ใช้แทนวันยื่นเฉพาะงวดที่ไม่มี fs_filed)
      oppday (วันประชุมนักวิเคราะห์ จากหัวไฟล์ 'meeting YYYY-MM-DD') · set_news (ข่าว SET ที่เก็บไว้) · xd (Yahoo dividends) · xd_stock (Yahoo splits = หุ้นปันผล/แตกพาร์)
rel: 'R' = event เป็นวันแรกที่ตลาดตอบสนองต่อรายการได้ · 'R+1' = วันทำการถัดจากนั้น · 'XD' = วัน XD พอดี
วันแรกที่ตอบสนองได้: รายการที่ออกหลัง 16:30 น. (หรือไม่รู้เวลาแบบ audit_signed) = วันทำการถัดไป · ข่าวที่ออกหลังวัน T ไม่นับเป็นสาเหตุของวัน T
"""
import argparse, csv, glob, json, os, re, sys
from datetime import date

sys.stdout.reconfigure(encoding='utf-8')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'output')
TH = ['มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน', 'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม']
EN = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
PERIOD_ENDS = {(3, 31), (6, 30), (9, 30), (12, 31)}  # วันสิ้นงวดที่ตามท้ายรายงาน ไม่ใช่วันลงนาม


def parse_date_text(s):
    """วันที่สุดท้ายที่พบในข้อความ (ไทย/อังกฤษ, พ.ศ./ค.ศ.) ที่ไม่ใช่วันสิ้นงวด"""
    best = None
    for m in re.finditer(r'(\d{1,2})\s*(' + '|'.join(TH) + '|' + '|'.join(EN) + r')\s*(?:พ\.ศ\.\s*)?(\d{4})', s):
        mon = (TH + EN).index(m.group(2)) % 12 + 1
        y = int(m.group(3))
        y = y - 543 if y > 2400 else y
        if (mon, int(m.group(1))) in PERIOD_ENDS:
            continue
        try:
            best = date(y, mon, int(m.group(1)))
        except ValueError:
            pass
    return best


def add_filing(items, name, rel):
    m = re.search(r'FIN(\d{2})(\d{2})(\d{4})(\d{2})(\d{2})', name)
    if m:
        try:
            items.append(dict(date=date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat(), time=f'{m.group(4)}:{m.group(5)}', kind='fs_filed', src=rel))
        except ValueError:
            pass


def build(raw, t):
    items = []
    for root, dirs, _ in os.walk(raw):
        for name in dirs:
            add_filing(items, name, os.path.relpath(os.path.join(root, name), raw).replace('\\', '/'))
    for p in glob.glob(os.path.join(raw, '**', '*'), recursive=True):
        if not os.path.isfile(p):
            continue
        name, rel = os.path.basename(p), os.path.relpath(p, raw).replace('\\', '/')
        if not name.lower().endswith('.extracted.md'):
            add_filing(items, name, rel)
        if 'auditreport' in name.lower() and name.endswith('.extracted.md'):
            d = parse_date_text(open(p, encoding='utf-8', errors='ignore').read()[-3500:])
            if d:
                items.append(dict(date=d.isoformat(), kind='audit_signed', src=rel))
        if 'Earning' in rel and name.endswith('.txt'):
            m = re.search(r'meeting (\d{4}-\d{2}-\d{2})', open(p, encoding='utf-8', errors='ignore').read(400))
            if m:
                items.append(dict(date=m.group(1), kind='oppday', src=rel))
        if name.startswith('set_news_') and name.endswith('.jsonl'):
            for line in open(p, encoding='utf-8', errors='ignore'):
                try:
                    n = json.loads(line)
                    items.append(dict(date=n['datetime'][:10], time=n['datetime'][11:16], kind='set_news', src=rel, title=n.get('title', '')[:120], url=n.get('url', '')))
                except (ValueError, KeyError):
                    pass
    seen, uniq = set(), []
    for i in sorted(items, key=lambda i: (i['date'], i['kind'], i.get('time', ''))):
        k = (i['date'], i['kind'], i.get('time'))
        if k not in seen:
            seen.add(k)
            uniq.append(i)
    filed = [date.fromisoformat(i['date']) for i in uniq if i['kind'] == 'fs_filed']
    return [i for i in uniq if i['kind'] != 'audit_signed' or not any(abs((f - date.fromisoformat(i['date'])).days) <= 7 for f in filed)]


def reaction_day(item, days):
    """ดัชนีวันทำการแรกที่ตลาดตอบสนองต่อรายการได้"""
    j = next((n for n, d in enumerate(days) if d >= item['date']), None)
    if j is None:
        return None
    t = item.get('time')
    after_close = item['kind'] == 'audit_signed' or (t and t.replace(':', '') >= '1630')
    return j + 1 if days[j] == item['date'] and after_close else j


def match(items, events, days):
    out, ev = [], {e['date'] for e in events}
    for i in items:
        if i['kind'] in ('xd', 'xd_stock'):
            if i['date'] in ev:
                out.append(dict(event_date=i['date'], rel='XD', item=i))
            continue
        j = reaction_day(i, days)
        if j is None:
            continue
        i['react_date'] = days[j] if j < len(days) else None
        for k, rel in ((j, 'R'), (j + 1, 'R+1')):
            if k < len(days) and days[k] in ev:
                out.append(dict(event_date=days[k], rel=rel, item=i))
    return out


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('ticker'); ap.add_argument('--raw', default='D:/3_Stocks_Analyst/AllCompany')
    a = ap.parse_args()
    if not os.path.isdir(os.path.join(a.raw, a.ticker)):
        sys.exit(f'ไม่พบโฟลเดอร์ข้อมูลดิบ: {os.path.join(a.raw, a.ticker)}')
    events = list(csv.DictReader(open(os.path.join(OUT, f'events_{a.ticker}_raw.csv'), encoding='utf-8')))
    items = build(os.path.join(a.raw, a.ticker), a.ticker)
    # เวลายื่นงบจากหน้าข่าว SET เชื่อถือกว่าเวลาในชื่อไฟล์ FIN จึงแทนที่รายการจากไฟล์ในงวดเดียวกัน
    seturl = f'https://www.set.or.th/th/market/news-and-alert/news?source=company&symbol={a.ticker}&securityType=S'
    curated = json.load(open(os.path.join(OUT, 'set_news.json'), encoding='utf-8')).get(a.ticker, [])
    set_items = [dict(date=d, time=tm, kind='set_fs' if k == 'fs' else 'set_news', title=title, src=f'{seturl}&fromDate={d}&toDate={d}') for d, tm, k, title in curated]
    set_fs = [date.fromisoformat(i['date']) for i in set_items if i['kind'] == 'set_fs']
    items = [i for i in items if i['kind'] not in ('fs_filed', 'audit_signed') or not any(abs((f - date.fromisoformat(i['date'])).days) <= 7 for f in set_fs)] + set_items
    corp = json.load(open(os.path.join(OUT, f'corp_actions_{a.ticker}.json'), encoding='utf-8'))
    items += [dict(date=d, kind='xd', src='Yahoo dividends', amount=v) for d, v in corp['dividends'].items()]
    items += [dict(date=d, kind='xd_stock', src='Yahoo splits', ratio=v) for d, v in corp['splits'].items()]
    days = [r['date'] for r in csv.DictReader(open(os.path.join(OUT, f'prices_{a.ticker}.csv'), encoding='utf-8'))]
    m = match(items, events, days)
    json.dump(dict(ticker=a.ticker, items=items, matches=m), open(os.path.join(OUT, f'calendar_{a.ticker}.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    kinds = {}
    for i in items:
        kinds[i['kind']] = kinds.get(i['kind'], 0) + 1
    print(f"{a.ticker}: calendar items={len(items)} {kinds} · events in reaction window = {len({x['event_date'] for x in m})}/{len(events)}")
