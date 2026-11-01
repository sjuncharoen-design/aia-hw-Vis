"""รวมข้อมูลของทุกหุ้น -> output/events_all.json + output/events_all.csv (ใช้โดย build_dashboard.py)
usage: python scripts/make_events_all.py
input : output/prices_<T>.csv · events_<T>_raw.csv · calendar_<T>.json · coverage_<T>.json (จาก fetch_events / disclosure_calendar / scan_evidence)
กติกา: สาเหตุใส่เฉพาะที่มีหลักฐาน · ที่เหลือ = driver "unknown", conf "low", why "ยังไม่พบสาเหตุที่ยืนยันได้" · วันที่ตรงปฏิทินบริษัทเป็นแค่ "ข้อสังเกต" ไม่ใช่สาเหตุ
conf: mid = มีหลักฐานตรงวันและตรงเรื่อง แต่ยังไม่ครบเกณฑ์ high (tier A >=1 หรือ tier B >=2 ที่เปิดอ่านหน้าเต็ม) · low = ยังไม่พบสาเหตุ
"""
import csv, json, os
from datetime import date

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'output')
TICKERS = [('TIDLOR', 'ติดล้อ โฮลดิ้งส์', 'การเงิน non-bank'), ('DOHOME', 'ดูโฮม', 'ค้าปลีกวัสดุก่อสร้าง'),
           ('MOSHI', 'โมชิ โมชิ รีเทล', 'ค้าปลีกไลฟ์สไตล์'), ('PR9', 'โรงพยาบาลพระรามเก้า', 'โรงพยาบาล')]
KIND_TH = {'audit_signed': 'วันลงนามรายงานผู้สอบบัญชี (กรรมการอนุมัติงบ)', 'oppday': 'วันประชุมนักวิเคราะห์ (Oppday)',
           'fs_filed': 'วันยื่นงบต่อ SET', 'set_news': 'ข่าว SET', 'xd': 'วัน XD ปันผล'}
SEARCHED = 'ค้นเว็บแล้วบางส่วน ยังไม่พบข่าวหรือประกาศที่ตรงวันนี้'

OVERRIDES = {
    ('TIDLOR', '2026-05-21'): dict(
        driver='dividend_buyback', conf='mid',
        why='บอร์ดอนุมัติปันผลระหว่างกาล 0.69 บาท/หุ้น (สูงกว่าตลาดคาด) พร้อมโครงการซื้อหุ้นคืนไม่เกิน 2,400 ล้านบาท และกำไร Q1/2569 นิวไฮ 1,613.7 ล้านบาท (+34.7%)',
        evidence=[dict(tier='B', src='https://www.posttoday.com/business/stockholder/742750', note='รายงานหุ้นพุ่ง 10.56% วันที่ 21 พ.ค. 2569 หลังประกาศปันผลและซื้อหุ้นคืน (อ่านจากผลค้นหา ยังไม่ได้เปิดหน้าเต็ม)'),
                  dict(tier='B', src='https://www.share2trade.com/news/55701/', note='กำไร Q1/69 นิวไฮ 1,613.7 ล้านบาท โต 34.7% (อ่านจากผลค้นหา ยังไม่ได้เปิดหน้าเต็ม)'),
                  dict(tier='B', src='https://trade.innovestx.co.th/cafeinvest/research/company-analysis/high-conviction/tidlor-hc-20260521', note='บทวิเคราะห์ระบุปันผล 0.69 บาท สูงกว่าตลาดคาด · XD 2 มิ.ย. 2569'),
                  dict(tier='B', src='https://finance.yahoo.com/quote/TIDLOR.BK/history', note='ข้อมูล Yahoo แสดงเงินปันผล 0.69 บาท วัน XD 2 มิ.ย. 2569 ตรงกับข่าว')],
        note='ยังไม่มีเอกสารบริษัท (tier A) ในชุดนี้และยังไม่ได้เปิดอ่านหน้าเต็ม จึงยังไม่ให้ high'),
    ('DOHOME', '2025-06-23'): dict(
        driver='news_negative', conf='mid',
        why='ข่าวว่าเจ้าหน้าที่เข้าตรวจพบสินค้าไม่ได้มาตรฐาน ทำให้หุ้นดิ่งติดฟลอร์ โบรกมองผลกระทบทางการเงินเล็กแต่กระทบความเชื่อมั่นผู้บริโภค',
        evidence=[dict(tier='B', src='https://www.share2trade.com/news/44592', note='"DOHOME ดิ่งติดฟลอร์ เซ่นปมข่าวฉาว สินค้าไม่ได้มาตรฐาน" (อ่านจากผลค้นหา ยังไม่ได้เปิดหน้าเต็ม)'),
                  dict(tier='B', src='https://today.line.me/th/v3/article/JPGrY27', note='บทความลงวันที่ 23 มิ.ย. 2025 เวลา 06:37 (ก่อนตลาดเปิด) — อาจเป็นการนำข่าวมาเผยแพร่ซ้ำ ไม่นับเป็นแหล่งอิสระ')],
        note='มีแหล่งอิสระเดียวที่ยืนยัน จึงยังเป็น mid · วันก่อนหน้า (19 มิ.ย. −10.0%) และวัน 25 มิ.ย. (+12.31%) อยู่ในช่วงเดียวกัน ยังไม่ยืนยันว่าเกี่ยวกับข่าวนี้'),
}
NOTES_EXTRA = {
    ('DOHOME', '2025-06-25'): 'ช่วงเดียวกับบทวิเคราะห์ที่ระบุว่าบริษัทเพิ่มมาตรการตรวจคุณภาพสินค้า (ลงวันที่ราว 24–26 มิ.ย. 2025 ยังไม่ยืนยันวันที่) [ยังไม่ยืนยัน]',
    ('MOSHI', '2022-12-23'): 'วันซื้อขายที่ 2 ตามข้อมูล Yahoo (แท่งแรก 22 Dec 2022) น่าจะเป็นช่วงหลังเข้าจดทะเบียน [ยังไม่ยืนยันวัน IPO จาก SET]',
}


def load(t):
    p = [dict(d=r['date'], p=float(r['close'])) for r in csv.DictReader(open(os.path.join(OUT, f'prices_{t}.csv'), encoding='utf-8'))]
    ev = list(csv.DictReader(open(os.path.join(OUT, f'events_{t}_raw.csv'), encoding='utf-8')))
    cal = json.load(open(os.path.join(OUT, f'calendar_{t}.json'), encoding='utf-8'))
    cov = json.load(open(os.path.join(OUT, f'coverage_{t}.json'), encoding='utf-8'))['coverage']
    return p, ev, cal, cov


def build():
    allv, rows = {}, []
    for t, name, group in TICKERS:
        prices, raw, cal, cov = load(t)
        by_date = {}
        for m in cal['matches']:
            by_date.setdefault(m['event_date'], []).append(m)
        events, prev = [], None
        cid = 0
        for r in raw:
            d, ret = r['date'], float(r['ret_pct'])
            gap = (date.fromisoformat(d) - date.fromisoformat(prev)).days if prev else 999
            cid = cid + 1 if gap > 8 else cid
            prev = d
            ov = OVERRIDES.get((t, d))
            tags = [dict(kind=m['item']['kind'], rel=m['rel'], date=m['item']['date'], time=m['item'].get('time'), label=KIND_TH[m['item']['kind']], src=m['item']['src'],
                         title=m['item'].get('title')) for m in by_date.get(d, []) if m['item']['kind'] != 'set_news' or True]
            e = dict(date=d, close=float(r['close']), prev_close=float(r['prev_close']), ret=ret, dir='up' if ret > 0 else 'down', cluster=cid,
                     driver=ov['driver'] if ov else 'unknown', conf=ov['conf'] if ov else 'low',
                     why=ov['why'] if ov else 'ยังไม่พบสาเหตุที่ยืนยันได้', evidence=ov['evidence'] if ov else [],
                     searched=None if ov else SEARCHED if (t, d) in NOTES_EXTRA or t == 'TIDLOR' else 'สแกนเอกสารในเครื่องทุกไฟล์แล้ว ไม่พบข้อความที่อธิบายการขยับของวันนี้',
                     calendar=tags, note=(ov or {}).get('note') or NOTES_EXTRA.get((t, d)))
            events.append(e)
        sizes = {}
        for e in events:
            sizes[e['cluster']] = sizes.get(e['cluster'], 0) + 1
        for e in events:
            e['cluster_n'] = sizes[e['cluster']]
        divs = [dict(date=r['date'], amount=r['xd_dividend']) for r in raw if r.get('xd_dividend')]
        allv[t] = dict(ticker=t, name=name, group=group, prices=prices, events=events, coverage=cov,
                       first=prices[0]['d'], last=prices[-1]['d'], bars=len(prices),
                       explained=sum(e['conf'] != 'low' for e in events), with_calendar=sum(bool(e['calendar']) for e in events))
        for e in events:
            rows.append([t, e['date'], e['close'], e['prev_close'], e['ret'], e['driver'], e['conf'], e['why'],
                         '; '.join(f"{c['label']} {c['date']} ({c['rel']})" for c in e['calendar']), ' | '.join(x['src'] for x in e['evidence'])])
    json.dump(allv, open(os.path.join(OUT, 'events_all.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, 'events_all.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['ticker', 'date', 'close', 'prev_close', 'ret_pct', 'driver', 'conf', 'why', 'company_calendar', 'evidence_urls'])
        w.writerows(rows)
    for t, v in allv.items():
        print(f"{t}: events={len(v['events'])} explained={v['explained']} with_calendar={v['with_calendar']} bars={v['bars']} {v['first']}..{v['last']} "
              f"files_scanned={v['coverage']['files_scanned']}")


if __name__ == '__main__':
    build()
