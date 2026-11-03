"""ตรวจความครบของ price_move.json ก่อนรายงานว่าเสร็จ
usage: python check_page.py PRICE_MOVE_JSON   (exit 1 และพิมพ์รายการถ้ามีข้อผิดพลาด)
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', '..', 'thai-stock-fundamental-dashboard', 'scripts'))
import detect_events as de  # noqa: E402


def check(page):
    err = []
    P = page['price']['rows']
    ids = {e['id'] for e in page['events']}
    want = de.daily_events(P, 5.0) + de.window_events(P)
    for e in want:
        i = f"{e['date']}_{e['kind']}"
        if i not in ids:
            err.append(f'{i} ไม่อยู่ในหน้า')
    known = {e['id'] for e in page['events'] if e['status'] == 'known'}
    for e in page['events']:
        if e['status'] not in ('known', 'draft'):
            err.append(f"{e['id']} สถานะไม่ถูกต้อง: {e['status']}")
        if not e.get('tip') and e['status'] == 'known':
            err.append(f"{e['id']} ไม่มีข้อความในกล่องเมื่อเลื่อนเมาส์")
        if e['status'] == 'known' and not e.get('inherited_from'):
            for f in ('what', 'why', 'market_view', 'outlook'):
                if not str(e.get(f) or '').strip():
                    err.append(f"{e['id']} การ์ดขาด {f}")
            if not e.get('pnl') and not e.get('pnl_note'):
                err.append(f"{e['id']} การ์ดขาดข้อกระทบงบ")
            if not e.get('evidence'):
                err.append(f"{e['id']} การ์ดขาดที่มา")
        br = (e.get('pnl') or {}).get('bridge')
        if br:
            np_ = next(x['delta'] for x in br if x['line'] == 'np')
            if abs(sum(x['delta'] for x in br if x['line'] != 'np') - np_) > 0.05:
                err.append(f"{e['id']} สะพานกำไรรวมไม่ตรง")
    for side in ('catalysts', 'risks'):
        for t in page['takeaways'].get(side) or []:
            if not t.get('ids'):
                err.append(f"Key takeaway ไม่อ้างเหตุการณ์: {t.get('text')}")
            for i in t.get('ids') or []:
                if i not in known:
                    err.append(f'Key takeaway อ้าง {i} ซึ่งไม่ใช่เหตุการณ์ที่รู้สาเหตุ')
    x = page.get('extras') or {}
    if x.get('oppday') and not str(x['oppday'].get('file') or '').strip():
        err.append('Oppday ไม่ระบุไฟล์ต้นทาง')
    for f in x.get('factors') or []:
        if not str(f.get('src') or '').strip():
            err.append(f"ปัจจัย {f.get('f')} ไม่มีที่มา")
    for n in x.get('next') or []:
        if not str(n.get('basis') or '').strip():
            err.append(f"เหตุการณ์ถัดไป {n.get('t')} ไม่มีเหตุผลรองรับวันที่")
    refs = {r['src']: r for r in page['references']}
    for e in page['events']:
        for key in ('evidence', 'context', 'market_view_src'):
            for s in e.get(key) or []:
                if s.get('src') and s['src'] not in refs:
                    err.append(f"{e['id']} แหล่ง {s['src']} ไม่อยู่ใน Reference")
    for r in refs.values():
        if r['src'].startswith('http') and not r.get('accessed'):
            err.append(f"{r['src']} ไม่มีวันที่เข้าถึง")
    return err


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    errors = check(json.load(open(sys.argv[1], encoding='utf-8')))
    for x in errors:
        print('FAIL', x)
    print(f'errors={len(errors)}')
    sys.exit(1 if errors else 0)
