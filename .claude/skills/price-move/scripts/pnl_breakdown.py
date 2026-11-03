"""แยกงบกำไรขาดทุนรายไตรมาสเทียบปีก่อน พร้อมสะพานกำไรและวันยื่นงบ
usage: python pnl_breakdown.py TICKER OUT_JSON [--raw AllCompany] [--browser-news FILE] [--quarterly FILE]
input : <raw>/<T>/Financial statement/<YYYYQ#>_FS_<T>*.extracted.md (ไม่เปิดไฟล์ต้นฉบับ) · <raw>/<T>/News/set_news_*.jsonl · --browser-news
output: {ticker, unit, finance, missing, quarters:{q:{cur, prior, yoy, bridge, drivers, filed:{date, time, est, src}}}}
หน่วยล้านบาท · Q4 = ทั้งปี − 9 เดือน · finance = COGS ต่ำกว่า 5% ของรายได้รวม (ธุรกิจการเงิน ไม่มี GPM และใช้รายได้รวม)
สะพานกำไร: Δกำไรขั้นต้น = ผลจากรายได้ (Δรายได้ × GPM ปีก่อน) + ผลจากมาร์จิ้น (ส่วนที่เหลือ) · other = รายการอื่น ภาษี รายได้อื่น
วันยื่นงบ: ข่าว SET ก่อน แล้วชื่อไฟล์/โฟลเดอร์ FIN<DDMMYYYY><hhmm> ภายใน 15–100 วันหลังสิ้นไตรมาส ไม่พบให้ประมาณจากสิ้นไตรมาส + 45 วัน (est = true)
"""
import argparse, glob, json, os, re, statistics, sys
from datetime import date, timedelta

NUM_FIX = None
ROWS = [('rev_main', r'^(รายได้จากการขาย|รายได้จากการขายและการให้บริการ|รายได้ค่าบริการ|รายได้จากการประกอบกิจการโรงพยาบาล)$'), ('tot_rev', r'^รวมรายได้'),
        ('cogs', r'^(ต้นทุนขาย|ต้นทุนในการประกอบกิจการโรงพยาบาล)'), ('sell', r'^(ค่าใช้จ่ายในการขาย|ต้นทุนในการจัดจำหน่าย)'), ('admin', r'^ค่าใช้จ่ายในการบริหาร'),
        ('fin', r'^ต้นทุนทางการเงิน'), ('ecl', r'^ผลขาดทุนด้านเครดิต'), ('np', r'^กำไร\s*(\(ขาดทุน\))?\s*(สุทธิ)?\s*สำหรับ')]
NUM = re.compile(r'^-?\d+(\.\d+)?$')
NAMES = {'rev': 'ผลจากรายได้', 'gpm': 'ผลจากมาร์จิ้น (GPM)', 'sell': 'ค่าใช้จ่ายขาย', 'admin': 'ค่าใช้จ่ายบริหาร', 'ecl': 'ผลขาดทุนเครดิต', 'fin': 'ต้นทุนการเงิน', 'other': 'รายการอื่น ภาษี รายได้อื่น', 'np': 'Δ กำไรสุทธิ'}


UNIT = re.compile(r'หน่วย\s*:?\s*(พันบาท|ล้านบาท|บาท)|Unit\s*:?\s*(Thousand|Million)?\s*Baht|^\|\s*(พันบาท|ล้านบาท|บาท)\s*\|', re.I)
SCALE = {'พันบาท': 1e-3, 'thousand': 1e-3, 'ล้านบาท': 1.0, 'million': 1.0, 'บาท': 1e-6, '': 1e-6}


def fix_text(line):
    return line.replace('\u0e4d\u0e32', '\u0e33')  # สระอำแยกรูปในไฟล์สกัดบางบริษัท


def num(c):
    """ค่าในเซลล์: ว่างหรือ - = 0 · ตัดจุลภาค · (1,234) = -1234 · ไม่ใช่ตัวเลข = None"""
    c = c.strip().replace(',', '')
    if c in ('', '-', '–'):
        return 0.0
    neg = c.startswith('(') and c.endswith(')')
    c = c.strip('()')
    return (-float(c) if neg else float(c)) if NUM.match(c) else None


def positions(parts):
    """ตำแหน่งคอลัมน์ตัวเลขของแถวหลัก ตัดคอลัมน์เลขหมายเหตุที่นำหน้า"""
    pos = [i for i, c in enumerate(parts) if i > 0 and NUM.match(c.strip().replace(',', ''))]
    if len(pos) >= 3:
        a, b = num(parts[pos[0]]), num(parts[pos[1]])
        if a == int(a) and 1 <= a <= 99 and abs(b) >= 1000:
            pos = pos[1:]
    return pos


def blocks(path):
    """บล็อกงบกำไรขาดทุนทุกบล็อกในไฟล์ พร้อมหน่วยที่ประกาศไว้ก่อนบล็อก · บล็อกที่ไม่พบแถวกำไรถูกทิ้ง"""
    out, cur, unit = [], None, None
    for line in open(path, encoding='utf-8', errors='ignore'):
        line = fix_text(line)
        m = UNIT.search(line.strip())
        if m:
            unit = SCALE[(m.group(1) or m.group(2) or m.group(3) or '').lower()]
        if not line.startswith('|'):
            continue
        parts = [c.strip() for c in line.strip().strip('|').split('|')]
        label = parts[0]
        has_num = any(num(c) not in (None, 0.0) for c in parts[1:])
        if label == 'รายได้' and not has_num:
            cur = {k: [] for k, _ in ROWS}  # หัวบล็อกใหม่ ทิ้งบล็อกเดิมที่ยังไม่พบแถวกำไร
            cur['unit'] = unit
            continue
        if cur is None or not has_num:
            continue
        for key, pat in ROWS:
            if re.match(pat, label) and (key == 'rev_main' or not cur[key]):
                cur[key].append(parts)
        if re.match(ROWS[-1][1], label):
            out.append(cur)
            cur = None
    return out


def anchor(b):
    row = (b['tot_rev'] or b['rev_main'] or [None])[0]
    return positions(row) if row else []


def cell(row, pos, idx):
    if idx >= len(pos):
        return None
    if pos[idx] >= len(row):
        return None
    return num(row[pos[idx]])


def scale_of(b):
    if b.get('unit'):
        return b['unit']
    pos = anchor(b)
    row = (b['tot_rev'] or b['rev_main'])[0]
    t = cell(row, pos, 0) or 0
    return 1e-6 if abs(t) > 5e7 else 1e-3


def values(b, idx):
    sc, pos = scale_of(b), anchor(b)
    v = {}
    main = [cell(r, pos, idx) for r in b['rev_main']]
    main = [x for x in main if x is not None]
    v['rev_main'] = sum(abs(x) for x in main) * sc if main else None
    for k in ('tot_rev', 'cogs', 'sell', 'admin', 'fin', 'ecl'):
        x = cell(b[k][0], pos, idx) if b[k] else None
        v[k] = abs(x) * sc if x is not None else None
    x = cell(b['np'][0], pos, idx) if b['np'] else None
    v['np'] = x * sc if x is not None else None
    return v


def sub(a, b):
    return {k: a[k] - b[k] if a[k] is not None and b[k] is not None else None for k in a}


def total(b):
    return (values(b, 0)['tot_rev'] or 0) if b['tot_rev'] else 0


def read_blocks(base, t, q):
    """บล็อกที่ผ่านการตรวจ: Q2/Q3 ต้องมีบล็อกสะสมที่ใหญ่กว่าบล็อก 3 เดือน"""
    files = sorted(glob.glob(os.path.join(base, f'{q}_FS_{t}*.extracted.md')), key=lambda p: ('.pdf' in p.lower(), p))
    for p in files:
        bl = blocks(p)
        if not bl:
            continue
        if q[5] in '23' and (len(bl) < 2 or total(bl[1]) < total(bl[0]) * 1.3):
            continue
        return bl
    return None


def derive(base, t, q):
    bl = read_blocks(base, t, q)
    if not bl:
        return None
    if q[5] != '4':
        return values(bl[0], 0), values(bl[0], 1)
    b9 = read_blocks(base, t, f'{q[:4]}Q3')
    if not b9 or total(bl[0]) <= total(b9[1]):
        return None
    return sub(values(bl[0], 0), values(b9[1], 0)), sub(values(bl[0], 1), values(b9[1], 1))


def metrics(v, finance):
    partial = v['rev_main'] is not None and v['tot_rev'] and v['rev_main'] < 0.5 * v['tot_rev']  # บรรทัดรายได้หลักที่รู้จักครอบไม่ถึงครึ่ง
    rev = v['tot_rev'] if finance or v['rev_main'] is None or partial else v['rev_main']
    gp = None if finance or partial or rev is None or v['cogs'] is None else rev - v['cogs']
    m = dict(rev=rev, cogs=v['cogs'], gp=gp, sell=v['sell'], admin=v['admin'], fin=v['fin'], ecl=v['ecl'], np=v['np'], gpm=None, sell_pct=None, admin_pct=None)
    if rev:
        m['gpm'] = None if gp is None else gp / rev * 100
        m['sell_pct'] = None if v['sell'] is None else v['sell'] / rev * 100
        m['admin_pct'] = None if v['admin'] is None else v['admin'] / rev * 100
    return m


def bridge(cur, pri, finance):
    """รายการผลต่อกำไร · คืน None ถ้าบรรทัดใดมีแค่ฝั่งเดียว เพราะสะพานจะรวมไม่ตรง"""
    if cur['np'] is None or pri['np'] is None or cur['rev'] is None or pri['rev'] is None:
        return None
    items = []
    if finance:
        items.append(('rev', cur['rev'] - pri['rev']))
    else:
        if cur['gp'] is None or pri['gp'] is None or not pri['rev']:
            return None
        rev_eff = (cur['rev'] - pri['rev']) * pri['gp'] / pri['rev']
        items += [('rev', rev_eff), ('gpm', cur['gp'] - pri['gp'] - rev_eff)]
    for k in ('sell', 'admin', 'ecl', 'fin'):
        if cur[k] is None and pri[k] is None:
            continue
        if cur[k] is None or pri[k] is None:
            return None
        items.append((k, -(cur[k] - pri[k])))
    dnp = cur['np'] - pri['np']
    items = [(k, round(x, 2)) for k, x in items]
    items.append(('other', round(dnp - sum(x for _, x in items), 2)))
    items.append(('np', round(dnp, 2)))
    return [dict(line=k, name=NAMES[k], delta=x) for k, x in items]


def quarter_of_title(title):
    if 'งบการเงิน' not in (title or ''):
        return None
    m = re.search(r'ไตรมาสที่ (\d)/(\d{4})', title)
    if m:
        return f'{int(m.group(2)) - 543}Q{m.group(1)}'
    m = re.search(r'ประจำปี (\d{4})', title)
    return f'{int(m.group(1)) - 543}Q4' if m else None


def news_filings(raw_t, browser_news=None):
    files = glob.glob(os.path.join(raw_t, 'News', 'set_news_*.jsonl')) + ([browser_news] if browser_news and os.path.exists(browser_news) else [])
    out = {}
    for f in files:
        for line in open(f, encoding='utf-8', errors='ignore'):
            try:
                n = json.loads(line)
                q, dt = quarter_of_title(n.get('title')), n['datetime']
            except (ValueError, KeyError):
                continue
            if q and (q not in out or dt < out[q]['dt']):
                out[q] = dict(dt=dt, date=dt[:10], time=dt[11:16], est=False, src=os.path.basename(f))
    return out


def fin_dates(raw_t):
    found = []
    for _, dirs, files in os.walk(raw_t):
        for name in dirs + files:
            m = re.search(r'FIN(\d{2})(\d{2})(\d{4})(\d{2})(\d{2})', name)
            if m:
                try:
                    found.append((date(int(m.group(3)), int(m.group(2)), int(m.group(1))), f'{m.group(4)}:{m.group(5)}', name))
                except ValueError:
                    pass
    return sorted(found)


def filing(q, news, fins):
    if q in news:
        return {k: news[q][k] for k in ('date', 'time', 'est', 'src')}
    y, n = int(q[:4]), int(q[5])
    qe = date(y, n * 3, (31, 30, 30, 31)[n - 1])
    for d, tm, name in fins:
        if qe + timedelta(days=15) <= d <= qe + timedelta(days=100):
            return dict(date=d.isoformat(), time=tm, est=False, src=name)
    return dict(date=(qe + timedelta(days=45)).isoformat(), time=None, est=True, src=None)


def build(t, raw, browser_news=None):
    raw_t = os.path.join(raw, t)
    base = os.path.join(raw_t, 'Financial statement')
    if not os.path.isdir(base):
        sys.exit(f'ไม่พบโฟลเดอร์ข้อมูลดิบ: {base}')
    qs = sorted({os.path.basename(p)[:6] for p in glob.glob(os.path.join(base, '20??Q?_FS_*.extracted.md')) if f'_FS_{t}' in os.path.basename(p)})
    raw_vals, missing = {}, []
    for q in qs:
        d = derive(base, t, q)
        if d:
            raw_vals[q] = d
        else:
            missing.append(q)
    ratios = [(c['cogs'] or 0) / c['tot_rev'] for c, _ in raw_vals.values() if c['tot_rev']]
    finance = bool(ratios) and statistics.median(ratios) < 0.05
    news, fins = news_filings(raw_t, browser_news), fin_dates(raw_t)
    r2 = lambda x: None if x is None else round(x, 2)
    quarters = {}
    for q, (c, p) in raw_vals.items():
        cur, pri = metrics(c, finance), metrics(p, finance)
        yoy = {}
        for k in ('rev', 'cogs', 'gp', 'sell', 'admin', 'fin', 'ecl', 'np'):
            if cur[k] is not None and pri[k]:
                yoy[k] = dict(delta=r2(cur[k] - pri[k]), pct=r2((cur[k] / pri[k] - 1) * 100) if pri[k] > 0 else None)
        for k in ('gpm', 'sell_pct', 'admin_pct'):
            if cur[k] is not None and pri[k] is not None:
                yoy[k] = dict(delta=r2(cur[k] - pri[k]), pct=None)
        br = bridge(cur, pri, finance)
        drivers = sorted((b for b in br or [] if b['line'] not in ('other', 'np')), key=lambda b: -abs(b['delta']))[:2]
        quarters[q] = dict(cur={k: r2(x) for k, x in cur.items()}, prior={k: r2(x) for k, x in pri.items()}, yoy=yoy, bridge=br, drivers=drivers, filed=filing(q, news, fins))
    return dict(ticker=t, unit='ล้านบาท', finance=finance, missing=missing, quarters=quarters)


def quarterly_rows(res):
    """แถวรายไตรมาสในรูปแบบที่ build_evidence_pack.py ใช้"""
    rows, prev = [], None
    for q in sorted(res['quarters']):
        x = res['quarters'][q]
        c, y = x['cur'], x['yoy']
        rows.append(dict(q=q, rev=c['rev'], gpm=c['gpm'], np=c['np'], rev_yoy=(y.get('rev') or {}).get('pct'), np_yoy=(y.get('np') or {}).get('pct'),
                         np_qoq=round((c['np'] / prev - 1) * 100, 2) if prev and c['np'] is not None and prev > 0 else None))
        prev = c['np']
    return rows


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('ticker'); ap.add_argument('out')
    ap.add_argument('--raw', default=os.environ.get('PRICE_MOVE_RAW', 'AllCompany')); ap.add_argument('--browser-news'); ap.add_argument('--quarterly', help='เขียนแถวรายไตรมาสสำหรับ build_evidence_pack.py')
    a = ap.parse_args()
    res = build(a.ticker, a.raw, a.browser_news)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(res, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    if a.quarterly:
        json.dump(quarterly_rows(res), open(a.quarterly, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f"{a.ticker}: quarters={len(res['quarters'])} missing={res['missing']} finance={res['finance']} -> {a.out}")
