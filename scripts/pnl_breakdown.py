"""แยกงบกำไรขาดทุนรายไตรมาส (รายได้ ต้นทุน GPM ค่าขาย ค่าบริหาร ต้นทุนการเงิน ผลขาดทุนเครดิต กำไรสุทธิ) เทียบปีก่อน และสะพานกำไร
usage: python scripts/pnl_breakdown.py [--raw DIR]   (default DIR = D:/3_Stocks_Analyst/AllCompany)
input : <DIR>/<T>/Financial statement/<YYYYQ#>_FS_<T>*.extracted.md (อ่านผ่าน .extracted.md เท่านั้น) · output/calendar_<T>.json
output: output/pnl_<T>.json = {quarters:{YYYYQ#:{cur,prior,yoy,bridge}}, events:{วันที่:ไตรมาส}}
หน่วยล้านบาท · Q4 = ทั้งปี − 9 เดือน · สะพานกำไร = Δกำไรขั้นต้น − Δค่าขาย − Δค่าบริหาร − Δต้นทุนการเงิน − Δผลขาดทุนเครดิต (ส่วนที่เหลือ = รายการอื่น ภาษี)
ธุรกิจการเงิน (TURBO) ไม่มีต้นทุนขาย: ใช้รายได้รวม และ opex อยู่ในค่าใช้จ่ายในการบริหาร
"""
import argparse, glob, json, os, re, sys

sys.stdout.reconfigure(encoding='utf-8')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'output')
NONBANK = {'TURBO'}
ROWS = [('rev_main', r'^(รายได้จากการขาย|รายได้จากการขายและการให้บริการ|รายได้ค่าบริการ|รายได้จากการประกอบกิจการโรงพยาบาล)$'), ('tot_rev', r'^รวมรายได้'), ('cogs', r'^(ต้นทุนขาย|ต้นทุนในการประกอบกิจการโรงพยาบาล)'),
        ('sell', r'^(ค่าใช้จ่ายในการขาย|ต้นทุนในการจัดจำหน่าย)'), ('admin', r'^ค่าใช้จ่ายในการบริหาร'), ('fin', r'^ต้นทุนทางการเงิน'), ('ecl', r'^ผลขาดทุนด้านเครดิต'), ('np', r'^กำไร\s*(\(ขาดทุน\))?\s*(สุทธิ)?\s*สำหรับ')]
NUM = re.compile(r'^-?\d+(\.\d+)?$')


def cells(line):
    line = line.replace('ํา', 'ำ')
    parts = [c.strip() for c in line.strip().strip('|').split('|')]
    nums = [float(c) for c in parts[1:] if NUM.match(c)]
    if len(nums) >= 3 and nums[0] == int(nums[0]) and 1 <= nums[0] <= 99 and abs(nums[1]) >= 1000:
        nums = nums[1:]
    return parts[0], nums


def blocks(path):
    out, cur = [], None
    for line in open(path, encoding='utf-8', errors='ignore'):
        if not line.startswith('|'):
            continue
        label, nums = cells(line)
        if re.match(r'^รายได้$', label) and not nums:
            cur = {k: [] for k, _ in ROWS}  # หัวบล็อกใหม่ ทิ้งบล็อกเดิมที่ยังไม่พบแถวกำไร
            continue
        if cur is None:
            continue
        for key, pat in ROWS:
            if re.match(pat, label) and nums:
                cur[key].append(nums) if key in ('rev_main',) else cur[key].append(nums) if not cur[key] else None
        if re.match(ROWS[-1][1], label) and nums:
            out.append(cur)
            cur = None
    return out


def valid_blocks(bl, n):
    """Q1 มี 1 บล็อก · Q2/Q3 ต้องมี 3 เดือนและสะสม (สะสมต้องใหญ่กว่า) · Q4 บล็อกแรกคือทั้งปี"""
    if not bl:
        return None
    if n in ('2', '3'):
        if len(bl) < 2 or not (bl[0]['tot_rev'] and bl[1]['tot_rev']) or bl[1]['tot_rev'][0][0] < bl[0]['tot_rev'][0][0] * 1.3:
            return None
    return bl


def values(b, idx, scale):
    v = {}
    v['rev_main'] = sum(abs(r[idx]) for r in b['rev_main'] if len(r) > idx) * scale if b['rev_main'] else None
    for k in ('tot_rev', 'cogs', 'sell', 'admin', 'fin', 'ecl', 'np'):
        v[k] = abs(b[k][0][idx]) * scale if b[k] and len(b[k][0]) > idx else None
    if b['np'] and len(b['np'][0]) > idx:
        v['np'] = b['np'][0][idx] * scale
    return v


def scale_of(b):
    t = b['tot_rev'][0][0] if b['tot_rev'] else 0
    return 1e-6 if t > 5e7 else 1e-3


def find_fs(base, t, q):
    c = sorted(glob.glob(os.path.join(base, f'{q}_FS_{t}*.extracted.md')), key=lambda p: ('.pdf' in p.lower(), p))
    return c


def quarter(base, t, q):
    for p in find_fs(base, t, q):
        bl = valid_blocks(blocks(p), q[5])
        if bl:
            return bl, p
    return None, None


def sub(a, b):
    return {k: (a[k] - b[k]) if a[k] is not None and b[k] is not None else None for k in a}


def derive(base, t, q):
    """คืน (cur, prior) หน่วยล้านบาท ของไตรมาส q"""
    y, n = q[:4], q[5]
    bl, _ = quarter(base, t, q)
    if not bl:
        return None
    sc = scale_of(bl[0])
    if n != '4':
        return values(bl[0], 0, sc), values(bl[0], 1, sc)
    b9, _ = quarter(base, t, f'{y}Q3')
    if not b9 or len(b9) < 2:
        return None
    s9 = scale_of(b9[1])
    return sub(values(bl[0], 0, sc), values(b9[1], 0, s9)), sub(values(bl[0], 1, sc), values(b9[1], 1, s9))


def metrics(v, nonbank):
    rev = v['tot_rev'] if nonbank else v['rev_main']
    gp = None if nonbank or rev is None or v['cogs'] is None else rev - v['cogs']
    m = dict(rev=rev, cogs=v['cogs'], gp=gp, sell=v['sell'], admin=v['admin'], fin=v['fin'], ecl=v['ecl'], np=v['np'])
    if rev:
        m['gpm'] = None if gp is None else gp / rev * 100
        m['sell_pct'] = None if v['sell'] is None else v['sell'] / rev * 100
        m['admin_pct'] = None if v['admin'] is None else v['admin'] / rev * 100
    return m


def build_q(base, t, q):
    d = derive(base, t, q)
    if not d:
        return None
    nb = t in NONBANK
    cur, pri = metrics(d[0], nb), metrics(d[1], nb)
    r = lambda x: None if x is None else round(x, 2)
    yoy = {}
    for k in ('rev', 'cogs', 'gp', 'sell', 'admin', 'fin', 'ecl', 'np'):
        if cur.get(k) is not None and pri.get(k):
            yoy[k] = dict(delta=r(cur[k] - pri[k]), pct=r((cur[k] / pri[k] - 1) * 100))
    for k in ('gpm', 'sell_pct', 'admin_pct'):
        if cur.get(k) is not None and pri.get(k) is not None:
            yoy[k] = dict(delta=r(cur[k] - pri[k]), pct=None)
    parts = {'gp': cur['gp'] - pri['gp'] if cur.get('gp') is not None and pri.get('gp') is not None else None}
    bridge = None
    if nb:
        items = [('รายได้รวม', cur['rev'] - pri['rev']), ('ค่าใช้จ่ายในการบริหาร (opex)', -(cur['admin'] - pri['admin']) if cur['admin'] is not None and pri['admin'] is not None else None),
                 ('ผลขาดทุนด้านเครดิต', -(cur['ecl'] - pri['ecl']) if cur['ecl'] is not None and pri['ecl'] is not None else None), ('ต้นทุนการเงิน', -(cur['fin'] - pri['fin']) if cur['fin'] is not None and pri['fin'] is not None else None)]
    else:
        items = [('กำไรขั้นต้น', parts['gp']), ('ค่าใช้จ่ายขาย', -(cur['sell'] - pri['sell']) if cur['sell'] is not None and pri['sell'] is not None else None),
                 ('ค่าใช้จ่ายบริหาร', -(cur['admin'] - pri['admin']) if cur['admin'] is not None and pri['admin'] is not None else None), ('ต้นทุนการเงิน', -(cur['fin'] - pri['fin']) if cur['fin'] is not None and pri['fin'] is not None else None)]
    if all(v is not None for _, v in items):
        dnp = cur['np'] - pri['np']
        bridge = [dict(item=n, delta=r(v)) for n, v in items] + [dict(item='รายการอื่น/ภาษี/รายได้อื่น', delta=r(dnp - sum(v for _, v in items))), dict(item='Δ กำไรสุทธิ', delta=r(dnp))]
    return dict(cur={k: r(v) for k, v in cur.items()}, prior={k: r(v) for k, v in pri.items()}, yoy=yoy, bridge=bridge)


def quarter_of_title(title):
    m = re.search(r'ไตรมาสที่ (\d)/(\d{4})', title or '')
    if m:
        return f'{int(m.group(2)) - 543}Q{m.group(1)}'
    m = re.search(r'ประจำปี (\d{4})', title or '')
    return f'{int(m.group(1)) - 543}Q4' if m else None


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--raw', default='D:/3_Stocks_Analyst/AllCompany')
    a = ap.parse_args()
    for t in ('TURBO', 'DOHOME', 'MOSHI', 'PR9'):
        base = os.path.join(a.raw, t, 'Financial statement')
        if not os.path.isdir(base):
            sys.exit(f'ไม่พบโฟลเดอร์ข้อมูลดิบ: {base}')
        qs = sorted({os.path.basename(p)[:6] for p in glob.glob(os.path.join(base, f'20??Q?_FS_{t}*.extracted.md'))})
        res, missing = {}, []
        for q in qs:
            if q < '2021Q4':
                continue
            r = build_q(base, t, q)
            if r:
                res[q] = r
            else:
                missing.append(q)
        cal = json.load(open(os.path.join(OUT, f'calendar_{t}.json'), encoding='utf-8'))
        ev = {}
        for m in cal['matches']:
            if m['item']['kind'] == 'set_fs':
                q = quarter_of_title(m['item'].get('title'))
                if q:
                    ev[m['event_date']] = dict(quarter=q, rel=m['rel'], filed=m['item']['date'], time=m['item'].get('time'))
        json.dump(dict(ticker=t, unit='ล้านบาท', quarters=res, missing=missing, events=ev), open(os.path.join(OUT, f'pnl_{t}.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(t, 'quarters', len(res), 'missing', missing, 'events->quarter', len(ev))
