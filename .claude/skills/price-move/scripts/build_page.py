"""รวมเหตุการณ์ ข้อสรุป งบ และราคา เป็น price_move.json + HTML ไฟล์เดียว
usage: python build_page.py TICKER --events E --takeaways T --pnl P --price-dir D --out-dir O [--public --out FILE]
  E : ผลจาก merge_research.py (list ของ event)   T : {catalysts:[{text, ids, watch}], risks:[...]}   P : ผลจาก pnl_breakdown.py
  D : โฟลเดอร์ที่มี price_daily.json + price_recon.json   O : <_output>/PriceMove/ (ไฟล์ HTML อยู่ใต้ YYYYQQ/ ที่นี่)
  --public : สร้างหน้าสำหรับ repo Public ที่ --out เท่านั้น: ใช้ market_view_public ตัดแหล่งโบรกทั้งหมด และหยุด (exit 1) ถ้ายังพบชื่อโบรกหรือราคาเป้าหมาย
สถานะ: known ต้องมี conf high/mid + direction_match + หลักฐานที่ไม่ใช่โบรกซึ่งออกก่อนหรือระหว่างเหตุการณ์ · ที่เหลือ draft
"""
import argparse, json, os, re, sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, '..', 'assets', 'page_template.html')
NAMES = os.path.join(HERE, '..', 'assets', 'broker_names.txt')
FIN_KIND = {'day': 'รายวัน', 'window': 'รอบ 5–6 วัน', 'manual': 'จากรอบก่อน'}
BROKER_DOMAINS = ('globlex', 'yuanta', 'kgieworld', 'kgi.co.th', 'daol', 'krungsrisecurities', 'kasikornsecurities', 'kssecurities', 'scbs', 'asiaplus', 'bualuang',
                  'innovestx', 'trinitythai', 'maybank', 'cgsi', 'phillip', 'kkpsecurities', 'finansia', 'pi.financial', 'pisecurities', 'liberator', 'lhsec', 'thanachart')
TERMS = re.compile(r'ราคาเป้าหมาย|ประมาณการ|target\s+price|(?<![A-Za-z])TP(?![A-Za-z])|/broker/|routines4_broker', re.I)
LOOKBACK_DAYS = 7  # หลักฐานต้องอยู่ในช่วงไม่เกิน 7 วันก่อนเหตุการณ์ (งบเย็นวันศุกร์ + วันหยุดยาว)


def is_broker(x):
    src = str(x.get('src') or '').replace('\\', '/').lower()
    return bool(x.get('broker')) or '/broker/' in src or any(d in src for d in BROKER_DOMAINS)


def hhmm(t):
    m = re.match(r'^(\d{1,2}):(\d{2})', t or '')
    return f'{int(m.group(1)):02d}:{m.group(2)}' if m else ''


def in_time(x, start, end):
    """หลักฐานต้องออกไม่เกิน LOOKBACK_DAYS ก่อนเริ่มและไม่หลังจบเหตุการณ์ · วันเดียวกันหลัง 16:30 น. ตลาดตอบสนองไม่ทัน
    หลักฐานวันเดียวกันที่ไม่มีเวลาให้นับ (สื่อรายงานภายในวัน) ตาม ruling ใน ledger"""
    d = x.get('date')
    lo = (date.fromisoformat(start) - timedelta(days=LOOKBACK_DAYS)).isoformat()
    if not d or d > end or d < lo:
        return False
    return not (d == end and hhmm(x.get('time')) >= '16:30')


def status_of(e):
    if e.get('conf') not in ('high', 'mid') or e.get('direction_match') is not True:
        return 'draft'
    return 'known' if any(not is_broker(x) and in_time(x, e['date'], e['end']) for x in e.get('evidence') or []) else 'draft'


def normalize(e):
    if e.get('price_mismatch') and e.get('conf') == 'high':
        e['conf'] = 'mid'
    e['id'] = f"{e['date']}_{e['kind']}"
    e['status'] = status_of(e)


def inherit_window(events):
    """รอบที่ยังไม่มีข้อสรุปของตัวเอง ใช้สาเหตุจากวันที่รู้สาเหตุซึ่งอยู่ในรอบและทิศเดียวกัน"""
    known = {f"{e['date']}_{e['kind']}": e for e in events if e.get('status') == 'known'}
    for w in events:
        if w['kind'] != 'window' or w.get('status') == 'known' or w.get('direction_match') is False:
            continue
        ids = [i for i in w.get('days') or [] if i in known]
        share = sum(known[i]['ret'] for i in ids) / w['ret'] if w.get('ret') else 0
        if ids and share >= 0.5:  # วันที่รู้สาเหตุต้องอธิบายอย่างน้อยครึ่งหนึ่งของการขยับทั้งรอบ
            w['status'], w['inherited_from'] = 'known', ids


def tip_of(e, by_id):
    if e['status'] == 'known':
        if e.get('inherited_from'):
            return ' · '.join(by_id[i].get('why') or '' for i in e['inherited_from'])
        return e.get('why') or ''
    return 'Draft: ยังไม่ทราบสาเหตุที่ยืนยันได้'


def quarter_label(pnl):
    return max(pnl['quarters']) if pnl.get('quarters') else 'NA'


def assemble(ticker, events, takeaways, pnl, prices, recon, extras=None, series=None):
    if not prices:
        sys.exit('หยุด: ไม่มีราคา (price_daily.json ว่าง) รันขั้นราคาใหม่ก่อน')
    events = [dict(e) for e in events]
    seen = {}
    for e in events:
        normalize(e)
        n = seen[e['id']] = seen.get(e['id'], 0) + 1
        if n > 1:
            e['id'] = f"{e['id']}_{n}"  # วันเดียวกัน ชนิดเดียวกัน เช่น manual สองรายการ
    inherit_window(events)
    by_id = {e['id']: e for e in events}
    for e in events:
        e['tip'] = tip_of(e, by_id) or ('ยังไม่มีคำอธิบาย' if e['status'] == 'known' else '')
        if e.get('xd'):
            e['tip'] += ' · ' + ' · '.join(x['text'] for x in e['xd'])
        if e.get('vol_ratio') is not None:
            e['tip'] += f" · volume {e['vol_ratio']:g} เท่า"

        e['kind_th'] = FIN_KIND.get(e['kind'], e['kind'])
        q = e.get('pnl_quarter')
        if q:
            e['pnl'] = pnl.get('quarters', {}).get(q)
            if e['pnl'] is None:
                e['pnl_note'] = f'ไม่มีข้อมูลงบงวด {q}'
            elif str(e.get('pnl_note') or '').startswith('ไม่มีข้อมูลงบงวด'):
                e['pnl_note'] = None  # หมายเหตุเก่าจากรอบก่อนที่งวดนี้ยังอ่านไม่ได้
    first, last = prices[0]['d'], prices[-1]['d']
    bars = []
    for q in sorted(pnl.get('quarters', {})):
        x = pnl['quarters'][q]
        if first <= x['filed']['date'] <= last and x['cur'].get('np') is not None:
            bars.append(dict(q=q, x=x['filed']['date'], est=x['filed']['est'], np=x['cur']['np'], prior=x['prior'].get('np'), yoy=(x['yoy'].get('np') or {}).get('pct')))
    refs = {}
    for e in events:
        for s in [x for key in ('evidence', 'context', 'market_view_src') for x in e.get(key) or []] + list((e.get('vs_consensus') or {}).get('src') or []):
            if s.get('src'):
                r = refs.setdefault(s['src'], dict(src=s['src'], tier=s.get('tier'), accessed=s.get('accessed'), broker=is_broker(s), events=[]))
                if e['id'] not in r['events']:
                    r['events'].append(e['id'])
    for sr in series or []:
        for s in sr.get('src') or []:
            r = refs.setdefault(s['src'], dict(src=s['src'], tier=s.get('tier'), accessed=s.get('accessed'), broker=False, events=[]))
            r['events'].append('series:' + sr['id']) if 'series:' + sr['id'] not in r['events'] else None
    conflicts = [dict(c, event=e['id']) for e in events for c in e.get('conflicts') or []]
    return dict(ticker=ticker, label=quarter_label(pnl), finance=pnl.get('finance', False), missing_quarters=pnl.get('missing', []), public=False,
                price=dict(rows=[dict(d=r['d'], p=r['p']) for r in prices], recon=recon), bars=bars, events=events, takeaways=takeaways, extras=extras or {}, series=series or [],
                references=sorted(refs.values(), key=lambda r: (r['tier'] or 'Z', r['src'])), conflicts=conflicts)


def to_public(page):
    """ตัดเนื้อหาโบรกออกทั้งหมด เหลือมุมมองแบบรวมที่เขียนไว้ใน market_view_public"""
    page = json.loads(json.dumps(page, ensure_ascii=False))
    page['public'] = True
    for e in page['events']:
        e['market_view'] = e.pop('market_view_public', None) or 'ไม่แสดงในหน้าสาธารณะ'
        e.pop('market_view_src', None)
        for key in ('evidence', 'context'):
            e[key] = [x for x in e.get(key) or [] if not is_broker(x)]
        if e.get('vs_consensus'):
            e['vs_consensus']['src'] = [x for x in e['vs_consensus'].get('src') or [] if not is_broker(x)]
    page['references'] = [r for r in page['references'] if not r['broker']]
    return page


def forbidden(text):
    names = [n.strip() for n in open(NAMES, encoding='utf-8') if n.strip() and not n.startswith('#')]
    found = [n for n in names if re.search(r'(?<![A-Za-z])' + re.escape(n) + r'(?![A-Za-z])', text, 0 if len(n) <= 3 else re.I)]
    low = text.lower()
    return found + [d for d in BROKER_DOMAINS if d in low] + TERMS.findall(text)


def render(page):
    html = open(TEMPLATE, encoding='utf-8').read()
    return html.replace('/*DATA*/null', json.dumps(page, ensure_ascii=False).replace('<', '\\u003c'))  # ไม่มี < ดิบในสคริปต์ JSON ยังถูกต้อง


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('ticker')
    for f in ('--events', '--takeaways', '--pnl', '--price-dir', '--out-dir'):
        ap.add_argument(f, required=True)
    ap.add_argument('--series', action='append', default=[], help='ไฟล์ซีรีส์เสริม (series_import.py) ใช้ซ้ำได้')
    ap.add_argument('--extras', help='JSON ส่วนเสริม: oppday/watch/next/factors (ไม่บังคับ)')
    ap.add_argument('--public', action='store_true'); ap.add_argument('--out')
    a = ap.parse_args()
    if a.public and not a.out:
        ap.error('--public ต้องระบุ --out')
    rd = lambda p: json.load(open(p, encoding='utf-8'))
    page = assemble(a.ticker, rd(a.events), rd(a.takeaways), rd(a.pnl), rd(os.path.join(a.price_dir, 'price_daily.json')), rd(os.path.join(a.price_dir, 'price_recon.json')), rd(a.extras) if a.extras else None, [rd(f) for f in a.series])
    if a.public:
        page = to_public(page)
        sys.path.insert(0, HERE)
        import check_page
        errs = check_page.check(page)
        if errs:
            sys.exit('หยุด: หน้าสาธารณะไม่ผ่านการตรวจ ' + '; '.join(errs[:5]))
        html = render(page)
        bad = forbidden(json.dumps(page, ensure_ascii=False))
        if bad:
            sys.exit(f'หยุด: หน้าสาธารณะยังมีคำต้องห้าม {sorted(set(bad))}')
        out = a.out
    else:
        html = render(page)
        os.makedirs(a.out_dir, exist_ok=True)
        json.dump(page, open(os.path.join(a.out_dir, 'price_move.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        out = os.path.join(a.out_dir, page['label'], f"{page['label']}_PriceMove_{a.ticker}.html")
        if page['label'] == 'NA':
            out = os.path.join(a.out_dir, f'PriceMove_{a.ticker}.html')
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    open(out, 'w', encoding='utf-8').write(html)
    n = {k: sum(e['status'] == k for e in page['events']) for k in ('known', 'draft')}
    print(f"{a.ticker}: events={len(page['events'])} {n} refs={len(page['references'])} -> {out}")
