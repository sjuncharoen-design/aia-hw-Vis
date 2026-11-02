"""รวมข้อมูลของทุกหุ้น -> output/events_all.json + output/events_all.csv (ใช้โดย build_dashboard.py)
usage: python scripts/make_events_all.py
input : output/prices_<T>.csv · events_<T>_raw.csv · calendar_<T>.json · coverage_<T>.json · context_<T>.json
status: found = มีหลักฐานเนื้อหาและทิศทางสอดคล้อง · lead = เวลาตรงหรือพฤติกรรมราคาชี้ แต่ยังไม่มีเนื้อหายืนยัน · unknown = ยังไม่พบ
เกณฑ์งบ found: ราคาขยับในวันแรกที่ตลาดตอบสนองได้ + กำไรไปทิศเดียวกับราคา + volume >= 1.5 เท่า · เทียบ YoY เท่านั้น ยังไม่ได้เทียบกับที่ตลาดคาด
conf: high = หลักฐาน tier A และสื่อที่เปิดอ่านเต็มระบุเรื่องเดียวกัน · mid = หลักฐานตรงเวลาและตรงเรื่อง แต่ไม่มีเอกสารใดบอกตรง ๆ ว่าราคาขยับเพราะเรื่องนี้ · low = ยังไม่พบ
"""
import csv, json, os, statistics as st
from datetime import date

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'output')
TICKERS = [('TURBO', 'เงินเทอร์โบ', 'การเงิน non-bank'), ('DOHOME', 'ดูโฮม', 'ค้าปลีกวัสดุก่อสร้าง'),
           ('MOSHI', 'โมชิ โมชิ รีเทล', 'ค้าปลีกไลฟ์สไตล์'), ('PR9', 'โรงพยาบาลพระรามเก้า', 'โรงพยาบาล')]
KIND_TH = {'set_fs': 'งบการเงินตามหน้า SET', 'fs_filed': 'วันยื่นงบ (จากชื่อไฟล์)', 'audit_signed': 'วันลงนามผู้สอบบัญชี (ใช้แทนวันยื่นงบ)', 'oppday': 'วันประชุมนักวิเคราะห์',
           'set_news': 'ข่าว SET', 'xd': 'วัน XD ปันผล', 'xd_stock': 'วัน XD หุ้นปันผล'}
SEARCHED_LOCAL = 'สแกนเอกสารใน AllCompany และดูข่าว SET ช่วง 4 วันก่อนหน้าแล้ว ไม่พบเรื่องที่อธิบายวันนี้ (ยังไม่ได้ค้นเว็บวันนี้)'
SEARCHED_WEB = 'สแกนเอกสารใน AllCompany ดูข่าว SET ช่วง 4 วันก่อนหน้า และค้นเว็บข่าวไทยแล้ว ไม่พบเรื่องที่ยืนยันวันนี้'
WEB_SEARCHED = {('DOHOME', d) for d in ('2025-06-19', '2025-11-10', '2022-03-09', '2025-06-25')} | {('MOSHI', d) for d in ('2023-05-31', '2024-07-31', '2022-12-23', '2025-07-17')} | \
    {('PR9', d) for d in ('2023-04-10', '2026-01-12', '2026-03-02')} | {('TURBO', '2026-08-20')}
SET_URL = 'https://www.set.or.th/th/market/news-and-alert/news?source=company&symbol={}&securityType=S&fromDate={}&toDate={}'
LOCAL = 'ไฟล์งบในเครื่องของผู้เรียน ไม่ได้นำขึ้น repo'
CLASS_TH = {'xd': 'วัน XD', 'earnings': 'ช่วงตอบสนองต่องบ', 'market': 'ตามตลาด', 'reversal': 'เด้งกลับจากวันแรงก่อนหน้า', 'low_volume': 'volume ไม่ผิดปกติ', 'mid_volume': 'volume สูงปานกลาง', 'high_volume': 'volume สูงมาก'}
TYPE_TH = {'earnings': 'งบการเงิน', 'company_news': 'ข่าวบริษัท', 'market': 'ตลาด/มหภาค'}


def fs(t, d, pct_note, file_note):
    return dict(type='earnings', conf='mid', why=pct_note, evidence=[dict(tier='A', src=SET_URL.format(t, d, d), note='เวลาและหัวข้อจากหน้าข่าว SET'), dict(tier='A', src='', note=f'{file_note} — {LOCAL}')],
                note='ไม่มีเอกสารใดบอกตรง ๆ ว่าราคาขยับเพราะงบ · ยังไม่ได้เทียบกับที่ตลาดคาด')


FOUND = {
    ('TURBO', '2026-02-25'): fs('TURBO', '2026-02-24', 'งบปี 2568 ออกหลังตลาดปิด 24 ก.พ. 17:54 น. กำไรสุทธิ 503.1 ล้านบาท เทียบ 141.6 ล้านบาท (+255% YoY) พร้อมแจ้งงดจ่ายปันผล', '2025Q4_FS_TURBO'),
    ('DOHOME', '2024-02-21'): fs('DOHOME', '2024-02-20', 'งบปี 2566 ออก 20 ก.พ. 20:47 น. กำไรปีลด 24% แต่เฉพาะ Q4/66 พลิกเป็นกำไร 196.9 ล้านบาท จากขาดทุน 51.1 ล้านบาท (คำนวณจากทั้งปีลบ 9 เดือน) พร้อมประกาศปันผล', '2023Q4_FS และ 2023Q3_FS'),
    ('DOHOME', '2025-08-07'): fs('DOHOME', '2025-08-06', 'งบ Q2/68 ออก 6 ส.ค. 17:24 น. กำไร 157.2 ล้านบาท ลด 18.4% YoY และยอดขายลด 9.1%', '2025Q2_FS'),
    ('DOHOME', '2025-11-10'): fs('DOHOME', '2025-11-07', 'งบ Q3/68 ออก 7 พ.ย. 17:59 น. กำไร 102.1 ล้านบาท เพิ่ม 32.4% YoY แม้ยอดขายลด 8.7%', '2025Q3_FS'),
    ('DOHOME', '2026-02-23'): fs('DOHOME', '2026-02-20', 'งบปี 2568 ออก 20 ก.พ. 20:30 น. เฉพาะ Q4/68 กำไร 96.8 ล้านบาท ลด 39.5% YoY (คำนวณจากทั้งปีลบ 9 เดือน) และยอดขายทั้งปีลด 6.1%', '2025Q4_FS และ 2025Q3_FS'),
    ('MOSHI', '2023-02-28'): fs('MOSHI', '2023-02-27', 'งบปี 2565 ออก 27 ก.พ. 20:20 น. กำไร 253.2 ล้านบาท เพิ่ม 92.9% YoY และรายได้เพิ่ม 50%', '2022Q4_FS'),
    ('MOSHI', '2024-08-13'): fs('MOSHI', '2024-08-09', 'งบ Q2/67 ออก 9 ส.ค. 17:02 น. (12 ส.ค. เป็นวันหยุด) กำไร 81.2 ล้านบาท ลด 3.6% YoY แม้รายได้เพิ่ม 7.6%', '2024Q2_FS'),
    ('PR9', '2023-05-16'): fs('PR9', '2023-05-15', 'งบ Q1/66 ออก 15 พ.ค. 17:03 น. กำไร 108.8 ล้านบาท ลด 30.7% YoY', '2023Q1_FS'),
    ('PR9', '2025-02-19'): fs('PR9', '2025-02-19', 'งบปี 2567 ออกก่อนเปิดตลาด 19 ก.พ. 07:59 น. กำไรปี 712.7 ล้านบาท เพิ่ม 27.8% YoY เฉพาะ Q4 เพิ่ม 9.9% พร้อมมติปันผล', '2024Q4_FS'),
    ('DOHOME', '2025-06-23'): dict(type='company_news', conf='high', why='เจ้าหน้าที่ สมอ. ตรวจพบสินค้าไม่ได้มาตรฐานที่สาขาในนนทบุรี รวมเหล็กเส้นตกเกรดกว่า 99 ตัน มูลค่า 2.2 ล้านบาท ราคาลงถึงฟลอร์ระหว่างวัน โบรกมองว่ากระทบความเชื่อมั่นมากกว่าตัวเลขเงิน',
                                   evidence=[dict(tier='B', src='https://www.share2trade.com/news/44592', note='เปิดอ่านหน้าเต็มแล้ว 2 Nov 2026 ระบุหุ้นดิ่งเพราะข่าวนี้'),
                                             dict(tier='A', src=SET_URL.format('DOHOME', '2025-06-24', '2025-06-24'), note='บริษัทชี้แจงต่อ SET วันที่ 24 มิ.ย. 12:37 น.')],
                                   note='ราคาฟื้นแรงในวันถัดมา: +12.31% วันที่ 25 มิ.ย. และ T+5 จากวันนี้ +18.25%'),
    ('PR9', '2025-04-10'): dict(type='market', conf='mid', why='ตลาดทั้งตลาดฟื้นหลังสหรัฐฯ ประกาศชะลอภาษีนำเข้า 90 วัน ดัชนี SET ปิด +4.21%', evidence=[dict(tier='B', src='https://www.mitihoon.com/?p=536085', note='อ่านจากผลค้นหา ยังไม่ได้เปิดหน้าเต็ม')], note=None),
    ('TURBO', '2026-03-02'): dict(type='market', conf='mid', why='ตลาดทั้งเอเชียลงจากความขัดแย้งสหรัฐฯ–อิหร่านและราคาน้ำมัน ดัชนี SET ปิด −3.06%', evidence=[dict(tier='B', src='https://thaipublica.org/2026/04/set-monthly-march/', note='สรุปภาพรวมเดือนมีนาคม อ่านจากผลค้นหา'), dict(tier='B', src='https://www.finnomena.com/?p=277057', note='ตัวเลขดัชนีปิด อ่านจากผลค้นหา')], note='ข่าวจัดตั้งบริษัทย่อยออกหลังตลาดปิด 17:29 น. จึงไม่ใช่เหตุของวันนี้'),
}
LEADS = {
    ('TURBO', '2025-10-02'): 'วันซื้อขายที่ 3 หลังเข้าตลาด (เริ่มซื้อขาย 30 ก.ย. 2025 ราคา IPO 1.50 บาท) Yahoo ไม่มีข้อมูล 4 วันแรก จึงเพิ่มจาก TradingView · ยังไม่พบข่าวอธิบายวันนี้',
    ('TURBO', '2025-11-12'): 'งบ Q3/68 ออก 11 พ.ย. 19:09 น. กำไร 125.7 ล้านบาท จาก 26.7 ล้านบาท (+371% YoY) แต่ราคาลง และตลาด (TDEX) ลง 1.5% วันเดียวกัน ทิศทางจึงสวนกัน',
    ('DOHOME', '2023-05-08'): 'งบ Q1/66 ออกก่อนเปิดตลาด 06:47 น. กำไร 258.4 ล้านบาท ลด 43.8% YoY (คำนวณจาก 6 เดือนลบ Q2) แต่ราคาขึ้น ทิศทางสวนกัน',
    ('DOHOME', '2023-07-11'): 'SET แจ้งว่าหุ้นเพิ่มทุนเริ่มซื้อขาย 11 ก.ค. 2566 ตรงวัน แต่ยังไม่รู้จำนวนและประเภทหุ้น [ยังไม่ยืนยัน]',
    ('DOHOME', '2023-08-09'): 'งบ Q2/66 ออก 8 ส.ค. 21:02 น. กำไรลด 87.5% YoY แต่ราคาขึ้น และ volume แค่ 1.19 เท่า ทิศทางสวนกัน',
    ('DOHOME', '2025-02-20'): 'งบปี 2567 ออก 19 ก.พ. 21:27 น. กำไรปีเพิ่ม 15.2% แต่เฉพาะ Q4 ลด 18.7% ผลออกมาผสมกัน พร้อมมติปันผลและ ESOP',
    ('DOHOME', '2025-02-21'): 'วันที่ 2 หลังงบปี 2567 ราคาขึ้นต่อ แต่ volume แค่ 1.08 เท่า',
    ('DOHOME', '2025-05-08'): 'ราคาลงก่อนงบ Q1/68 ออก (17:40 น.) จึงไม่ได้เกิดจากการอ่านงบ อาจเป็นการคาดการณ์ล่วงหน้า',
    ('DOHOME', '2025-05-09'): 'งบ Q1/68 ออก 8 พ.ค. 17:40 น. กำไร 245.1 ล้านบาท แทบไม่เปลี่ยน (+0.3% YoY) แต่ราคาลง ต้องเทียบกับที่ตลาดคาด [ยังไม่ยืนยัน]',
    ('DOHOME', '2025-05-21'): 'SET แจ้งกรรมการตรวจสอบลาออก 21 พ.ค. 08:33 น. ก่อนเปิดตลาด ตรงวัน แต่ไม่มีหลักฐานว่าเป็นเหตุของราคา [ยังไม่ยืนยัน]',
    ('DOHOME', '2025-05-22'): 'วันที่ 2 หลังข่าวกรรมการตรวจสอบลาออก [ยังไม่ยืนยัน]',
    ('DOHOME', '2025-06-25'): 'วันถัดจากบริษัทชี้แจงกรณี สมอ. (24 มิ.ย. 12:37 น.) น่าจะเป็นการฟื้นหลังลงแรง แต่ยังไม่มีเอกสารยืนยัน',
    ('DOHOME', '2025-06-26'): 'share2trade ลงวันที่ 26 มิ.ย. 2025 ว่าบริษัทเพิ่มมาตรการตรวจคุณภาพสินค้า อยู่ในช่วงเดียวกัน แต่ยังไม่ยืนยันเหตุ',
    ('DOHOME', '2026-06-26'): 'ไม่มีข่าวบริษัทในช่วงนี้ · finnews ระบุว่าหุ้นอยู่ในกลุ่ม oversold 22–24 มิ.ย. และมีบทวิเคราะห์ 19 มิ.ย. คาดกำไร Q2/69 ดีจากยอดขายและสต็อกเหล็กต้นทุนต่ำ (อ่านจากผลค้นหา) ยังไม่ยืนยัน',
    ('MOSHI', '2022-12-23'): 'วันซื้อขายที่ 2 หลังเข้าตลาด 22 ธ.ค. 2565 (ราคา IPO 21 บาท) เป็นช่วงหลัง IPO volume เทียบกับฐาน 1 วันจึงใช้ไม่ได้',
    ('MOSHI', '2023-05-02'): 'วัน XD ปันผล 0.10 บาท และหุ้นปันผล 11:10 แต่ปันผลเงินอธิบายได้แค่ราว 0.2% และราคาถูกปรับหุ้นปันผลแล้ว จึงอธิบาย −5.15% ไม่ได้ทั้งหมด',
    ('MOSHI', '2023-05-31'): 'SET แจ้งว่าหุ้นเพิ่มทุนเริ่มซื้อขาย 1 มิ.ย. 2566 แต่ไม่ได้อธิบายการขึ้นแรงวันนี้ [ยังไม่ยืนยัน]',
    ('PR9', '2022-05-17'): 'วันที่ 2 หลังงบ Q1/65 (13 พ.ค. 07:41 น.) กำไร 157.1 ล้านบาท จาก 38.5 ล้านบาท แต่ไม่ใช่วันแรกที่ตลาดตอบสนองได้',
    ('PR9', '2026-03-02'): 'ตลาดลงแรงวันเดียวกัน (TDEX −3.66%) แต่หักผลตลาดแล้วยังลงเกิน 5% · วันเดียวกันมีเพียงข่าวผลประกอบการปี 2568 ที่ออกตั้งแต่ 18 ก.พ.',
}
MARKET_NOTE = 'ตลาดขยับทิศเดียวกันมาก (TDEX) ยังไม่ได้ค้นว่าเพราะข่าวอะไร เพราะเป็นเหตุจากตลาดซึ่งนำไปใช้ติดตามรายหุ้นได้น้อย'


def load(t):
    p = [dict(d=r['date'], p=float(r['close'])) for r in csv.DictReader(open(os.path.join(OUT, f'prices_{t}.csv'), encoding='utf-8'))]
    ev = list(csv.DictReader(open(os.path.join(OUT, f'events_{t}_raw.csv'), encoding='utf-8')))
    cal = json.load(open(os.path.join(OUT, f'calendar_{t}.json'), encoding='utf-8'))
    cov = {k: v for k, v in json.load(open(os.path.join(OUT, f'coverage_{t}.json'), encoding='utf-8'))['coverage'].items() if k != 'skipped'}  # ไม่ฝังรายชื่อไฟล์ที่ข้ามลงหน้า
    ctx = json.load(open(os.path.join(OUT, f'context_{t}.json'), encoding='utf-8'))
    return p, ev, cal, cov, ctx


def stats(events):
    """ประวัติราคาหลังสาเหตุประเภทเดียวกัน คำนวณเฉพาะวันที่พบสาเหตุ"""
    out = {}
    for key in TYPE_TH:
        rows = [e for e in events if e['status'] == 'found' and e['type'] == key]
        a5 = [e['ctx']['after5'] for e in rows if e['ctx']['after5'] is not None]
        out[key] = dict(n=len(rows), up=sum(e['dir'] == 'up' for e in rows), down=sum(e['dir'] == 'down' for e in rows), median_after5=round(st.median(a5), 2) if a5 else None, cont=sum(1 for e in rows if e['ctx']['after5'] is not None and e['ctx']['after5'] * e['ret'] > 0))
    return out


def build():
    allv, rows = {}, []
    for t, name, group in TICKERS:
        prices, raw, cal, cov, ctx = load(t)
        by_date = {}
        for m in cal['matches']:
            by_date.setdefault(m['event_date'], []).append(m)
        events, prev, cid = [], None, 0
        for r in raw:
            d, ret = r['date'], float(r['ret_pct'])
            gap = (date.fromisoformat(d) - date.fromisoformat(prev)).days if prev else 999
            cid = cid + 1 if gap > 8 else cid
            prev = d
            c = ctx['events'][d]
            fo, lead = FOUND.get((t, d)), LEADS.get((t, d))
            if fo:
                status, why, note = 'found', fo['why'], fo.get('note')
            elif lead:
                status, why, note = 'lead', lead, None
            elif c['cls'] == 'market':
                status, why, note = 'lead', 'ตามตลาด: ' + MARKET_NOTE, None
            elif c['cls'] in ('earnings', 'xd'):
                status, why, note = 'lead', f"อยู่ใน{CLASS_TH[c['cls']]} แต่ยังไม่ได้อ่านเนื้อหาของงวดนี้", None
            else:
                status, why, note = 'unknown', 'ยังไม่พบสาเหตุที่ยืนยันได้', None
            tags = [dict(kind=m['item']['kind'], rel=m['rel'], date=m['item']['date'], time=m['item'].get('time'), label=KIND_TH[m['item']['kind']], src=m['item']['src'], title=m['item'].get('title')) for m in by_date.get(d, [])]
            e = dict(date=d, close=float(r['close']), prev_close=float(r['prev_close']), ret=ret, dir='up' if ret > 0 else 'down', cluster=cid, status=status,
                     type=fo['type'] if fo else None, conf=fo['conf'] if fo else 'low', why=why, evidence=fo['evidence'] if fo else [], cls=c['cls'], ctx=c,
                     searched=None if fo else SEARCHED_WEB if (t, d) in WEB_SEARCHED else SEARCHED_LOCAL, calendar=tags, note=note)
            events.append(e)
        sizes = {}
        for e in events:
            sizes[e['cluster']] = sizes.get(e['cluster'], 0) + 1
        for e in events:
            e['cluster_n'] = sizes[e['cluster']]
        counts = {k: sum(e['status'] == k for e in events) for k in ('found', 'lead', 'unknown')}
        allv[t] = dict(ticker=t, name=name, group=group, prices=prices, events=events, coverage=cov, first=prices[0]['d'], last=prices[-1]['d'], bars=len(prices),
                       counts=counts, explained=counts['found'], with_calendar=sum(bool(e['calendar']) for e in events), stats=stats(events), beta=ctx['beta'], daily_sd=ctx['daily_sd'], first_filing=ctx['first_filing'],
                       before_first_filing=sum(e['ctx']['before_first_filing'] for e in events))
        for e in events:
            rows.append([t, e['date'], e['close'], e['prev_close'], e['ret'], e['status'], e['type'] or '', e['cls'], e['conf'], e['why'], e['ctx']['vol_ratio'], e['ctx']['mkt'], e['ctx']['gap'], e['ctx']['after5'],
                         '; '.join(f"{c['label']} {c['date']} ({c['rel']})" for c in e['calendar']), ' | '.join(x['src'] for x in e['evidence'] if x['src'])])
    json.dump(allv, open(os.path.join(OUT, 'events_all.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, 'events_all.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['ticker', 'date', 'close', 'prev_close', 'ret_pct', 'status', 'cause_type', 'class', 'conf', 'why', 'vol_ratio', 'market_pct', 'gap_pct', 'after5_pct', 'company_calendar', 'evidence_urls'])
        w.writerows(rows)
    for t, v in allv.items():
        print(f"{t}: events={len(v['events'])} {v['counts']} bars={v['bars']} {v['first']}..{v['last']} files_scanned={v['coverage']['files_scanned']} {v['coverage']['raw_dir']} earnings_stats={v['stats']['earnings']}")


if __name__ == '__main__':
    build()
