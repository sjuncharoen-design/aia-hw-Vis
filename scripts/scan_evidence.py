"""สแกน "ทุกไฟล์" ของหุ้นหนึ่งตัว (ผ่าน .extracted.md ไม่เปิดไฟล์ต้นฉบับ pdf/xlsx/docx) หาข้อความที่เอ่ยถึงวัน T และ T+1 ของแต่ละ event
usage: python scripts/scan_evidence.py TICKER [--raw DIR]   (default DIR = D:/3_Stocks_Analyst/AllCompany)
input : output/events_<T>_raw.csv (จาก fetch_events.py)
output: output/coverage_<T>.json = {coverage} เท่านั้น (ขึ้น repo ได้)
        <tmp>/evidence_<T>.json = {coverage, events:[{date, window, news[], hits[]}]} เป็นบันทึกงานชั่วคราวนอก repo เพราะมีข้อความตัดมาจากเอกสาร/บทวิเคราะห์โบรก (ลิขสิทธิ์ ห้ามขึ้น Public)
- เอกสารต้นทางอยู่นอก repo (ไม่นำขึ้น Public) — ใน output เก็บเฉพาะชื่อไฟล์ เลขบรรทัด และข้อความสั้นที่ตรงวัน
- ไฟล์ที่ชื่อเป็นของหุ้นตัวอื่น (YYYYQ#_ชนิด_OTHER) ถูกข้าม · ไฟล์ซ้ำ (sha256 เดียวกัน) นับครั้งเดียว · coverage บอกจำนวนที่สแกน/ข้ามพร้อมเหตุผล
- T+1: วันถัดไป (วันศุกร์รวมถึงวันจันทร์) เพราะข่าวหลังตลาดปิดส่งผลวันถัดไป
"""
import argparse, csv, glob, json, os, re, sys, tempfile
from datetime import date, timedelta

sys.stdout.reconfigure(encoding='utf-8')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'output')
TH = ['มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน', 'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม']
THA = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.']
EN = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
PRIORITY = ('News', 'Earning Call', 'Financial statement', 'OneReport', 'Analysis Report')  # Broker อ่านเพื่อประกอบ ไม่คัดลอกเนื้อหา


def patterns(d):
    """regex ที่จับวันที่ d ในรูปแบบไทย/อังกฤษ/ตัวเลข ทั้ง ค.ศ. และ พ.ศ."""
    day, m, y = d.day, d.month - 1, d.year
    be = y + 543
    dd = rf'0?{day}'
    yy = rf'(?:{y}|{be}|{str(be)[2:]}|{str(y)[2:]})'
    ps = [rf'(?<!\d){dd}\s*(?:{TH[m]}|{THA[m].replace(".", r"\.")})\s*{yy}(?!\d)',
          rf'(?<!\d){dd}\s*(?:{EN[m]}|{EN[m][:3]})\.?,?\s*{yy}(?!\d)',
          rf'(?<!\d){dd}[/.\-]0?{m + 1}[/.\-]{yy}(?!\d)',
          rf'{y}-{m + 1:02d}-{day:02d}']
    return re.compile('|'.join(ps), re.I)


def next_day(d):
    return d + timedelta(days=3 if d.weekday() == 4 else 1)


def sha_of(head):
    m = re.search(r'^source_sha256:\s*(\w+)', head, re.M)
    return m.group(1) if m else None


def other_ticker(name, t):
    if t in re.split(r'[_.\s-]', name):
        return None
    m = re.match(r'\d{4}Q[1-4]_[A-Za-z]+_([A-Z0-9]+)(?=[._]|$)', name)
    return m.group(1) if m else None


def list_docs(raw, t):
    docs, skipped, seen = [], [], {}
    for p in sorted(glob.glob(os.path.join(raw, '**', '*'), recursive=True)):
        if not os.path.isfile(p):
            continue
        name, rel = os.path.basename(p), os.path.relpath(p, raw).replace('\\', '/')
        low = name.lower()
        if low.endswith(('.pdf', '.xlsx', '.xls', '.xlsm', '.docx', '.doc', '.pptx', '.zip', '.png', '.jpg')) or '.extracted.idx.' in low:
            continue  # ไฟล์ต้นฉบับ: อ่านผ่าน .extracted.md เท่านั้น
        if not low.endswith(('.md', '.txt', '.jsonl', '.json', '.csv', '.html')):
            continue
        ot = other_ticker(name, t)
        if ot:
            skipped.append((rel, f'ชื่อไฟล์เป็นของ {ot}'))
            continue
        try:
            head = open(p, encoding='utf-8', errors='ignore').read(800)
        except OSError:
            skipped.append((rel, 'เปิดไม่ได้'))
            continue
        st = re.search(r'^status:\s*(\w+)', head, re.M)
        if st and st.group(1) == 'empty':
            skipped.append((rel, 'PDF สแกน (status empty)'))
            continue
        sha = sha_of(head)
        if sha and sha in seen:
            skipped.append((rel, f'ไฟล์ซ้ำของ {seen[sha]}'))
            continue
        if sha:
            seen[sha] = rel
        docs.append((p, rel))
    return docs, skipped


def kind_of(rel):
    return rel.split('/')[0]


def scan(t, raw):
    ev = list(csv.DictReader(open(os.path.join(OUT, f'events_{t}_raw.csv'), encoding='utf-8')))
    docs, skipped = list_docs(raw, t)
    pats = {}
    for e in ev:
        d = date.fromisoformat(e['date'])
        pats[e['date']] = (patterns(d), patterns(next_day(d)), next_day(d))
    res = {e['date']: dict(date=e['date'], ret_pct=float(e['ret_pct']), window=[e['date'], pats[e['date']][2].isoformat()], news=[], hits=[]) for e in ev}
    for p, rel in docs:
        k = kind_of(rel)
        try:
            lines = open(p, encoding='utf-8', errors='ignore').read().splitlines()
        except OSError:
            continue
        if p.endswith('.jsonl') and '/News/' in rel.replace('\\', '/') + '/':
            for ln, line in enumerate(lines, 1):
                try:
                    n = json.loads(line)
                    nd = date.fromisoformat(n['datetime'][:10])
                except (ValueError, KeyError, TypeError):
                    continue
                for e in ev:
                    d0 = date.fromisoformat(e['date'])
                    if d0 - timedelta(days=1) <= nd <= pats[e['date']][2]:
                        res[e['date']]['news'].append(dict(file=rel, line=ln, datetime=n['datetime'][:16], title=n.get('title', '')[:160], url=n.get('url', '')))
            continue
        for ln, line in enumerate(lines, 1):
            if len(line) < 6:
                continue
            for e in ev:
                a, b, _ = pats[e['date']]
                m = a.search(line) or b.search(line)
                if m and len(res[e['date']]['hits']) < 40:
                    s = max(0, m.start() - 70)
                    res[e['date']]['hits'].append(dict(file=rel, kind=k, line=ln, which='T' if a.search(line) else 'T+1', text=line[s:s + 200].strip()))
    for r in res.values():
        r['news'] = sorted({(n['file'], n['line']): n for n in r['news']}.values(), key=lambda n: n['datetime'])
        r['hits'].sort(key=lambda h: (PRIORITY.index(h['kind']) if h['kind'] in PRIORITY else 9, h['file'], h['line']))
    cov = dict(ticker=t, raw_dir='(นอก repo) AllCompany/' + t, files_scanned=len(docs), files_skipped=len(skipped),
               skipped=[dict(file=a, reason=b) for a, b in skipped],
               by_kind={k: sum(1 for _, r in docs if kind_of(r) == k) for k in sorted({kind_of(r) for _, r in docs})},
               events=len(ev), events_with_local_evidence=sum(1 for r in res.values() if r['news'] or r['hits']))
    json.dump(dict(coverage=cov), open(os.path.join(OUT, f'coverage_{t}.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    json.dump(dict(coverage=cov, events=list(res.values())), open(os.path.join(tempfile.gettempdir(), f'evidence_{t}.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f"{t}: scanned={cov['files_scanned']} skipped={cov['files_skipped']} events={cov['events']} with_local_evidence={cov['events_with_local_evidence']} by_kind={cov['by_kind']}")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('ticker'); ap.add_argument('--raw', default='D:/3_Stocks_Analyst/AllCompany')
    a = ap.parse_args()
    if not os.path.isdir(os.path.join(a.raw, a.ticker)):
        sys.exit(f'ไม่พบโฟลเดอร์ข้อมูลดิบ: {os.path.join(a.raw, a.ticker)}')
    scan(a.ticker, os.path.join(a.raw, a.ticker))
