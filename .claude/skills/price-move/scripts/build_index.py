"""สร้าง dashboard.html หน้าสรุปรวมทุกหุ้นจากหน้า Price Move ที่สร้างแล้ว (อ่าน JSON ที่ฝังในแต่ละหน้า)
usage: python build_index.py --pages-dir output/price_move --out output/dashboard.html
หยุดและไม่เขียนไฟล์ถ้าพบชื่อโบรกหรือคำต้องห้ามในข้อมูล (ใช้รายการเดียวกับ build_page --public)"""
import argparse, glob, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, '..', 'assets', 'index_template.html')
sys.path.insert(0, HERE)
import build_page  # noqa: E402


def summarize(path, base):
    html = open(path, encoding='utf-8').read()
    m = re.search(r'<script id="data" type="application/json">(.*?)</script>', html, re.S)
    if not m:
        sys.exit(f'หยุด: {path} ไม่ใช่หน้า Price Move (ไม่พบข้อมูลฝัง)')
    bad = build_page.forbidden(m.group(1))
    if bad:
        sys.exit(f'หยุด: {os.path.basename(path)} ยังมีคำต้องห้าม {sorted(set(bad))}')
    p = json.loads(m.group(1))
    ev = p['events']
    cnt = lambda kind, st: sum(e['kind'] == kind and e['status'] == st for e in ev)
    rows = p['price']['rows']
    take = lambda side: [dict(text=t['text'], ids=t['ids'], watch=t.get('watch')) for t in p['takeaways'].get(side) or []]
    return dict(ticker=p['ticker'], href=os.path.relpath(path, base).replace(os.sep, '/'), label=p['label'], public=p['public'], first=rows[0]['d'], last=rows[-1]['d'], bars=len(rows),
                price_status=(p['price']['recon'] or {}).get('status'), mismatches=len((p['price']['recon'] or {}).get('mismatches') or []),
                day=sum(e['kind'] == 'day' for e in ev), window=sum(e['kind'] == 'window' for e in ev),
                known=cnt('day', 'known'), draft=cnt('day', 'draft'), w_known=cnt('window', 'known'), w_draft=cnt('window', 'draft'),
                catalysts=take('catalysts'), risks=take('risks'), extras=bool(p.get('extras')), np_bars=len(p['bars']))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('--pages-dir', required=True); ap.add_argument('--out', required=True)
    a = ap.parse_args()
    files = sorted(f for f in glob.glob(os.path.join(a.pages_dir, '*.html')))
    if not files:
        sys.exit('หยุด: ไม่พบหน้า Price Move ในโฟลเดอร์')
    data = dict(stocks=[summarize(f, os.path.dirname(os.path.abspath(a.out))) for f in files])
    text = json.dumps(data, ensure_ascii=False)
    bad = build_page.forbidden(text)
    if bad:
        sys.exit(f'หยุด: ข้อมูลหน้าสรุปยังมีคำต้องห้าม {sorted(set(bad))}')
    html = open(TEMPLATE, encoding='utf-8').read().replace('/*DATA*/null', text.replace('<', '\u003c'))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    open(a.out, 'w', encoding='utf-8').write(html)
    print(f'{len(data["stocks"])} stocks -> {a.out}')
