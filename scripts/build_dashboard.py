"""สร้าง output/dashboard.html (ไฟล์เดียว ไม่พึ่ง CDN, หน้าเดียวสลับหุ้นด้วยแท็บ) จาก output/events_all.json
usage: python scripts/build_dashboard.py
ตัวเลขทุกตัวในหน้ามาจากข้อมูลที่ฝังเป็น JSON ไม่ได้พิมพ์ลงใน markup
"""
import csv, json, os

OUT = os.path.join(os.path.dirname(__file__), '..', 'output')
stocks = json.load(open(os.path.join(OUT, 'events_all.json'), encoding='utf-8'))

# ตัวเลขจากเอกสารบริษัท (Oppday Q2/2026, tier A) — หน้าอ้างอิงตามสไลด์
OPPDAY = dict(
    file='Oppday Q2/2026 (ประกาศ 17 ส.ค. 2026) — ไฟล์ในเครื่องของผู้เรียน ไม่ได้นำขึ้น repo',
    drivers=[
        dict(t='กำไรสุทธิ 1H26 = 3,147 ล้านบาท (+26% YoY) · Q2/26 = 1,533 (+18% YoY) · Q1/26 = 1,614', pg='หน้า 8'),
        dict(t='พอร์ตสินเชื่อรวม 112.5 พันล้านบาท (+2.4% QoQ) · ลูกค้าสินเชื่อ +9% YoY · สาขา 1,918 (+45 จากสิ้นปี 25)', pg='หน้า 9'),
        dict(t='ค่านายหน้าประกันวินาศภัยโตเหนือตลาด: เบี้ย 1H26 +10% YoY เทียบตลาด +2.5%', pg='หน้า 10'),
        dict(t='ต้นทุนเงินทุนคาดลดลงราว 5–10 bps ใน 2H26 เทียบ 1H26', pg='หน้า 13'),
    ],
    risks=[
        dict(t='สินเชื่อโตต่ำกว่าเป้า: 2.7% YTD เทียบ guidance 5–10% (บริษัทคาดเร่งตัวใน 2H26)', pg='หน้า 14'),
        dict(t='ตลาดประกันรถยนต์โตช้าและแข่งราคา อาจกดเบี้ยเฉลี่ยต่อกรมธรรม์', pg='หน้า 10, 13'),
        dict(t='ตัวเลขต้นทุนความเสี่ยงเครดิตยังไม่รวมการตั้งสำรองเพิ่มกรณีน้ำท่วม (overlay) — ตามต่อว่าต้องตั้งเพิ่มหรือไม่', pg='หน้า 12 (หมายเหตุ)'),
        dict(t='ตลาดรถบรรทุกมือสองฟื้นช้า พอร์ตรถบรรทุกฟื้นแบบค่อยเป็นค่อยไป', pg='หน้า 13'),
    ],
    guidance=[
        ['สินเชื่อโต YTD', '5–10%', '2.7%'], ['เบี้ยประกันวินาศภัย YoY', '5–10%', '10%'], ['NPL', '1.5–1.8%', '1.54%'],
        ['Credit cost', '2.0–2.5% (ปรับลดจาก 2.2–2.8%)', '1.88%'], ['Cost-to-income', 'ราว 55% (Mid-50%)', '54.8%'],
    ])

data = dict(stocks=stocks, oppday={'TIDLOR': OPPDAY})
html = open(os.path.join(os.path.dirname(__file__), 'dashboard_template.html'), encoding='utf-8').read()
html = html.replace('/*DATA*/null', json.dumps(data, ensure_ascii=False).replace('</', '<\\/'))
open(os.path.join(OUT, 'dashboard.html'), 'w', encoding='utf-8').write(html)
print(f'dashboard.html {len(html):,} bytes · stocks={list(stocks)} events={sum(len(v["events"]) for v in stocks.values())}')
