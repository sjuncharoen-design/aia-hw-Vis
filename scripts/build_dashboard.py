"""สร้าง output/dashboard.html (ไฟล์เดียว ไม่พึ่ง CDN, หน้าเดียวสลับหุ้นด้วยแท็บ) จาก output/events_all.json
usage: python scripts/build_dashboard.py
ตัวเลขทุกตัวในหน้ามาจากข้อมูลที่ฝังเป็น JSON ไม่ได้พิมพ์ลงใน markup
"""
import csv, json, os

OUT = os.path.join(os.path.dirname(__file__), '..', 'output')
stocks = json.load(open(os.path.join(OUT, 'events_all.json'), encoding='utf-8'))

# ตัวเลขจากเอกสารบริษัท (Oppday Q2/2026, tier A) อ่านผ่าน .extracted.md — pg = หน้าสไลด์ · ที่สกัดข้อความไม่ชัดไม่ใส่ตัวเลข
OPPDAY = {
 'TURBO': dict(
    file='Oppday Q2/2026 ของ TURBO (13 ส.ค. 2026) — ไฟล์ในเครื่องของผู้เรียน ไม่ได้นำขึ้น repo · ตัวเลขในกราฟสกัดข้อความได้ไม่แยกชัด ใส่เฉพาะที่อ่านได้แน่นอน',
    drivers=[
        dict(t='กำไรสุทธิโต +69.5% YoY (−11.9% QoQ) [ตัวเลขล้านบาทในกราฟปนกัน ยังไม่ยืนยัน]', pg='หน้า 3'),
        dict(t='ผลดำเนินงาน 1H26 ดีกว่าที่คาด: เร่งสินเชื่อ ลด NPL เพิ่มสำรอง ลดต้นทุนเงินทุน (ตามข้อความของบริษัท)', pg='หน้า 10'),
        dict(t='คุณภาพสินเชื่อดีขึ้น: Stage 3 ลดลงต่อเนื่อง และ Cost-to-income ลดลงจากการใช้ AI/เทคโนโลยี', pg='หน้า 6, 8, 10'),
        dict(t='ธุรกิจนายหน้าประกันโตต่อเนื่องเป็นไตรมาสที่ 3', pg='หน้า 10'),
    ],
    risk_note='บริษัทระบุเองในเอกสารชุดเดียวกัน',
    risks=[
        dict(t='ความสามารถชำระหนี้ของลูกค้า: หนี้ครัวเรือนสูง โดยเฉพาะลูกค้าที่รายได้ผูกกับฤดูกาลเกษตร', pg='หน้า 10'),
        dict(t='ความตึงเครียดภูมิรัฐศาสตร์/นโยบายการค้า ผ่านราคาพลังงาน ห่วงโซ่อุปทาน และความเชื่อมั่น', pg='หน้า 10'),
        dict(t='Credit cost เพิ่มเล็กน้อยจากการตั้งสำรองเผื่อ (management overlay)', pg='หน้า 7'),
    ],
    guidance=[['สินเชื่อโตปี 2026', '12.5–20.5%', '[ยังไม่ยืนยัน]'], ['Credit cost (คาดลดใน 18–24 เดือน)', '4.25–5.25%', '[ยังไม่ยืนยัน]'],
              ['ROA ปรับดีขึ้น', '100–150 bps', '[ยังไม่ยืนยัน]']]),
 'DOHOME': dict(
    file='Oppday Q2/2026 ของ DOHOME — ไฟล์ในเครื่องของผู้เรียน ไม่ได้นำขึ้น repo',
    drivers=[
        dict(t='รายได้รวม Q2/26 = 7,848.55 ล้านบาท (+6.64% YoY) · SSSG +1.8%', pg='หน้า 5, 6'),
        dict(t='กำไรขั้นต้น 1,540.87 ล้านบาท (+17.5% YoY) อัตรากำไรขั้นต้น 19.77% เทียบ 18.00% ปีก่อน — บริษัทระบุว่ามาจากสัดส่วนสินค้าและกลุ่มวัสดุก่อสร้างที่มาร์จิ้นสูงขึ้น', pg='หน้า 6, 9'),
        dict(t='ดอกเบี้ยจ่าย 76.13 ล้านบาท ลดลง 30.4% YoY · D/E 1.49 เท่า (6M26) จาก 1.79 ในปี 2023', pg='หน้า 6, 12'),
        dict(t='กำไรสุทธิ 305.38 ล้านบาท (+94.3% YoY) · EBITDA 729.57 ล้านบาท (+31.4%)', pg='หน้า 6'),
    ],
    risk_note='ข้อสังเกตจากตัวเลขในเอกสาร (ไม่ใช่ความเสี่ยงที่บริษัทระบุเอง)',
    risks=[
        dict(t='กำไรโตเร็วกว่ายอดขายมาก (กำไรสุทธิ +94% เทียบรายได้ +6.6%, SSSG +1.8%) กำไรจึงพึ่งอัตรากำไรขั้นต้นและดอกเบี้ยจ่ายที่ลด', pg='หน้า 5, 6'),
        dict(t='ภาษีจ่ายเพิ่มเป็นสองเท่า (63.98 เทียบ 31.74 ล้านบาท) และรายได้อื่นลด 28.6%', pg='หน้า 6'),
        dict(t='สินค้าคงคลัง 178 วัน และวงจรเงินสด 151 วัน (6M26) ยังสูง', pg='หน้า 12'),
    ], guidance=[]),
 'MOSHI': dict(
    file='Earning Call 2Q2026 ของ MOSHI (19 ส.ค. 2026) — ไฟล์ในเครื่องของผู้เรียน ไม่ได้นำขึ้น repo',
    drivers=[
        dict(t='รายได้ Q2/26 = 956.10 ล้านบาท (+17.2% YoY) · ขายปลีก 826.80 ล้านบาท (+17.9%) จากสาขาสุทธิเพิ่ม 36 แห่งและยอดช่วง Back to School', pg='หน้า 9, 11'),
        dict(t='อัตรากำไรขั้นต้น 56.4% (55.0% ปีก่อน) จากสัดส่วนขายปลีกและสินค้านำเข้ามาร์จิ้นสูง · กำไรสุทธิ 161.86 ล้านบาท (+20.4%)', pg='หน้า 12, 16'),
        dict(t='ออนไลน์ +176.6% YoY (สัดส่วนเพียงราว 3% ของรายได้) · สาขาทั้งหมด 218 แห่ง', pg='หน้า 5, 11'),
    ],
    risk_note='บริษัทระบุเองในเอกสารชุดเดียวกัน ยกเว้นข้อแรกที่เป็นข้อสังเกตจากกราฟ',
    risks=[
        dict(t='SSSG ชะลอลงต่อเนื่องตามลำดับในกราฟ: 15.2% (1Q25) → 7.9% → 6.0% → 3.8% → 4.0% → 1.6% (2Q26) [ลำดับจากข้อความ PDF ยังไม่ยืนยันกับภาพกราฟ]', pg='หน้า 9'),
        dict(t='อัตรากำไรขั้นต้นไตรมาสนี้ได้แรงจากการกลับรายการสำรองสินค้าครั้งเดียว (one-time reversal) · กำไรขั้นต้นลด 2.3% QoQ ตามฤดูกาล', pg='หน้า 12 (หมายเหตุ)'),
        dict(t='แผนลงทุน 500 ล้านบาท (ธุรกิจหลัก 200 · คลังสินค้า 220 · ที่ดิน 80)', pg='หน้า 26'),
    ],
    guidance=[['รายได้โต YoY', '15–20%', '17.4% (6M26)'], ['อัตรากำไรขั้นต้น', '54.5–57.5%', '56.5% (6M26)'],
              ['เปิดสาขาใหม่', '35 แห่ง (standalone ≥5)', '17 แห่งใน 1H26 · แผน 18 แห่งใน 2H26']]),
 'PR9': dict(
    file='Oppday Q2/2026 ของ PR9 — ไฟล์ในเครื่องของผู้เรียน ไม่ได้นำขึ้น repo · สกัดข้อความจากสไลด์ได้ไม่แยกชัด ใส่เฉพาะตัวเลขที่อ่านได้แน่นอน',
    drivers=[
        dict(t='รายได้ผู้ป่วยต่างชาติรวม +10.8% YoY และ +13.7% QoQ · กลุ่มตะวันออกกลาง (Arab) โตแรงที่สุด [ตัวเลขรายกลุ่มปนกันในข้อความ PDF ยังไม่ยืนยัน]', pg='หน้า 5'),
        dict(t='ลงทุนเพิ่มความสามารถ: ห้อง HD ระดับพรีเมียม, เครื่อง Biplane Angiography, ศูนย์ HBOT, ICU/CCU ใหม่', pg='หน้า 10, 13, 14'),
    ],
    risk_note='ข้อสังเกตจากตัวเลขในเอกสาร (ไม่ใช่ความเสี่ยงที่บริษัทระบุเอง)',
    risks=[
        dict(t='ผู้ป่วยนอกต่อวัน Q2/26 = 1,474 คน เทียบ 1,537 คน Q2/25 (−4.1% YoY) คำนวณจากอนุกรมในสไลด์', pg='หน้า 6'),
        dict(t='ลูกค้าจีน −17.1% YoY ในรายได้ต่างชาติ [ข้อความ PDF ปนกัน ยังไม่ยืนยัน]', pg='หน้า 5'),
    ], guidance=[]),
}

steel = json.load(open(os.path.join(OUT, 'factor_DOHOME.json'), encoding='utf-8'))
ONE = 'One Report ล่าสุดของบริษัท (ไฟล์ในเครื่อง)'

# หัวข้อติดตาม: signal เป็นเงื่อนไขที่ตรวจได้ · next คือการวิเคราะห์ต่อ ไม่ใช่คำสั่งซื้อขาย · hist = ประเภทสาเหตุสำหรับดึงสถิติจาก stats
WATCH = {
 'TURBO': [
    dict(t='Credit cost', latest='ยังไม่ได้ตัวเลขจากกราฟ [ยังไม่ยืนยัน]', target='4.25–5.25% (คาดลดใน 18–24 เดือน)', signal='เกินกรอบ 5.25% หรือสำรองเผื่อเพิ่มขึ้นต่อเนื่อง', hist='earnings', next='อ่านตัวเลข credit cost และ Stage 3 ในงบ Q3/69', src='Oppday Q2/26 หน้า 7, 11'),
    dict(t='การเติบโตสินเชื่อ', latest='พอร์ตราว 12,000 ล้านบาท +11.3% YoY ณ 30 มิ.ย. 2569 (สื่อ อ่านจากผลค้นหา)', target='12.5–20.5% ในปี 2026', signal='ต่ำกว่า 12.5% เมื่อจบปี', hist=None, next='เทียบยอดสินเชื่อกับเป้าเมื่องบ Q3/69 ออก', src='Oppday Q2/26 หน้า 11 · infoquest'),
    dict(t='กำไรเทียบปีก่อน', latest='Q2/26 กำไร +69.5% YoY และ −11.9% QoQ', target='ROA ดีขึ้น 100–150 bps', signal='กำไรลด QoQ ติดกัน 2 ไตรมาส', hist='earnings', next='แยกว่ากำไรมาจากสินเชื่อหรือจากสำรองที่ลดลง', src='Oppday Q2/26 หน้า 3, 11'),
    dict(t='การจ่ายปันผล', latest='งดจ่ายปันผลของปี 2568', target='—', signal='ประกาศนโยบายหรือเริ่มจ่ายปันผล', hist=None, next='ตรวจมติคณะกรรมการตอนงบปี 2569', src='ข่าว SET 24 ก.พ. 2569'),
 ],
 'DOHOME': [
    dict(t='อัตรากำไรขั้นต้น', latest='19.77% ใน Q2/26 เทียบ 18.00% ปีก่อน', target='—', signal='ต่ำกว่า 18% หรือลด 2 ไตรมาสติด', hist='earnings', next='แยกผลจากราคาเหล็ก กับผลจากสัดส่วนสินค้า', src='Oppday Q2/26 หน้า 6, 9'),
    dict(t='ราคาเหล็กและสต๊อก', latest=f"HRC เปลี่ยนทิศเดียวกับอัตรากำไรขั้นต้น {steel['same_direction']} จาก {steel['n']} ไตรมาส · สินค้าคงคลัง 178 วัน", target='—', signal='ราคาเหล็กลงแรงขณะสต๊อกยังสูง', hist=None, next='หาสัดส่วนเหล็กในยอดขายจากเอกสารบริษัท (ตอนนี้มีแค่ตัวเลขจากโบรกผ่านสื่อราว 30%)', src='factor_DOHOME.json · Oppday หน้า 12 · share2trade'),
    dict(t='ยอดขายสาขาเดิม', latest='SSSG +1.8% และรายได้ +6.64% ใน Q2/26', target='—', signal='SSSG ติดลบ', hist=None, next='ดูว่ากำไรโตเพราะยอดขายหรือเพราะมาร์จิ้น', src='Oppday Q2/26 หน้า 5, 6'),
    dict(t='คุณภาพสินค้าและชื่อเสียง', latest='เคยถูก สมอ. ตรวจ มิ.ย. 2025 ราคาลงถึงฟลอร์ แล้ว T+5 +18.25%', target='—', signal='มีข่าวตรวจซ้ำ หรือกระทบยอดขายในงบ', hist='company_news', next='ตามข่าว SET และ SSSG ไตรมาสถัดจากเหตุการณ์', src='ข่าว SET 24 มิ.ย. 2568 · share2trade'),
 ],
 'MOSHI': [
    dict(t='ยอดขายสาขาเดิม (SSSG)', latest='1.6% ใน Q2/26 ชะลอจาก 15.2% ใน Q1/25 [ลำดับกราฟยังไม่ยืนยัน]', target='—', signal='SSSG ติดลบ', hist='earnings', next='ตรวจตัวเลขกับภาพกราฟ แล้วตามงบ Q3/69', src='Earning Call Q2/26 หน้า 9'),
    dict(t='รายได้และสาขาใหม่', latest='รายได้ +17.4% ใน 6M26 · เปิดสาขา 17 แห่งจากแผน 35', target='รายได้ +15–20% · 35 สาขา', signal='รายได้ต่ำกว่า 15% หรือเปิดสาขาช้ากว่าแผน', hist=None, next='เทียบกับเป้าเมื่องบ Q3/69 ออก', src='Earning Call Q2/26 หน้า 28'),
    dict(t='อัตรากำไรขั้นต้น', latest='56.4% ใน Q2/26 ส่วนหนึ่งมาจากกลับรายการสำรองครั้งเดียว', target='54.5–57.5%', signal='ต่ำกว่า 54.5%', hist=None, next='ตัดรายการครั้งเดียวออกก่อนเทียบ', src='Earning Call Q2/26 หน้า 12'),
 ],
 'PR9': [
    dict(t='ผู้ป่วยต่างชาติ', latest='รายได้ต่างชาติ +10.8% YoY ใน Q2/26', target='—', signal='รายได้ต่างชาติลด YoY', hist='earnings', next='แยกตามกลุ่มประเทศ โดยเฉพาะตะวันออกกลาง', src='Oppday Q2/26 หน้า 5'),
    dict(t='ผู้ป่วยนอกต่อวัน', latest='1,474 คน ลด 4.1% YoY', target='—', signal='ลดต่อเนื่องอีก 2 ไตรมาส', hist=None, next='ดูว่ารายได้ต่อคนชดเชยได้หรือไม่', src='Oppday Q2/26 หน้า 6'),
    dict(t='กำไรรายไตรมาส', latest='ลงแรงที่สุดในกลุ่มที่พบสาเหตุคือ Q1/66 กำไร −30.7% YoY ราคา −9.95%', target='—', signal='กำไรลดเกิน 20% YoY', hist='earnings', next='อ่าน MD&A ทันทีที่งบออก', src='ข่าว SET 15 พ.ค. 2566 · งบในเครื่อง'),
 ],
}
NEXT = {
 'TURBO': [dict(t='งบ Q3/2569', d='ราว 11 พ.ย. 2026', basis='ปีก่อนออก 11 พ.ย. 2025 19:09 น.')],
 'DOHOME': [dict(t='งบ Q3/2569', d='ราว 7 พ.ย. 2026', basis='ปีก่อนออก 7 พ.ย. 2025 17:59 น.')],
 'MOSHI': [dict(t='งบ Q3/2569', d='ราว 13 พ.ย. 2026', basis='ปีก่อนออก 13 พ.ย. 2025 17:53 น.')],
 'PR9': [dict(t='งบ Q3/2569', d='ราว 7 พ.ย. 2026', basis='ปีก่อนออก 7 พ.ย. 2025 17:46 น.')],
}
# ระดับหลักฐาน: company = บริษัทระบุเอง · tested = ทดสอบกับข้อมูลแล้ว · hypothesis = สมมติฐาน
FACTORS = {
 'TURBO': [
    dict(f='หนี้ครัวเรือนและรายได้เกษตร', force='อำนาจลูกค้า / คุณภาพลูกค้า', swot='Threat', channel='Credit cost, NPL', metric='Credit cost, Stage 3', nature='รอบเศรษฐกิจ', level='company', src='Oppday Q2/26 หน้า 10 · ' + ONE + ' หน้า 9'),
    dict(f='อัตราดอกเบี้ยและต้นทุนเงินทุน', force='อำนาจเจ้าหนี้ (ซัพพลายเออร์เงินทุน)', swot='Threat', channel='ต้นทุนการเงิน, สเปรด', metric='Finance cost %', nature='รอบดอกเบี้ย', level='company', src=ONE + ' หน้า 9'),
    dict(f='กฎเกณฑ์ผู้กำกับและการกระจุกตัวของธุรกิจ', force='ภาครัฐ / อุปสรรคการเข้าตลาด', swot='Threat', channel='เพดานดอกเบี้ย, รายได้', metric='Yield on loan', nature='โครงสร้าง', level='company', src=ONE + ' หน้า 8'),
    dict(f='การแข่งขันสินเชื่อรายย่อย', force='การแข่งขันในอุตสาหกรรม', swot='Threat', channel='การเติบโต, Yield', metric='การเติบโตสินเชื่อ, จำนวนสาขา', nature='โครงสร้าง', level='company', src=ONE + ' หน้า 8'),
 ],
 'DOHOME': [
    dict(f='ราคาเหล็กผันผวน', force='อำนาจซัพพลายเออร์ และการแข่งขันด้านราคา (สินค้า commodity)', swot='Threat', channel='อัตรากำไรขั้นต้น, กำไร/ขาดทุนจากสต๊อก', metric='อัตรากำไรขั้นต้น, วันสินค้าคงคลัง, สัดส่วนเหล็ก',
         nature='รอบวัฏจักร', level='tested', src=f"เทียบ HRC=F (สหรัฐฯ เป็นตัวแทน) ได้ทิศเดียวกัน {steel['same_direction']}/{steel['n']} ไตรมาส ค่าสหสัมพันธ์ {steel['corr']} เป็นแค่ความสอดคล้อง · บริษัทระบุความเสี่ยงราคาวัตถุดิบและมูลค่าสินค้าลดลงโดยไม่เอ่ยเหล็ก ({ONE} หน้า 8) · ยอดขายเหล็กราว 30% เป็นตัวเลขจากโบรกผ่าน share2trade"),
    dict(f='คุณภาพสินค้าและชื่อเสียง', force='อำนาจลูกค้า', swot='Weakness', channel='ความเชื่อมั่น, ยอดขาย', metric='SSSG, ข่าว สมอ.', nature='เหตุการณ์ครั้งเดียว ต้องตามว่าซ้ำหรือไม่', level='company', src=ONE + ' หน้า 8 · ข่าว SET 24 มิ.ย. 2568'),
    dict(f='สต๊อกสินค้าสูง', force='—', swot='Weakness', channel='เงินทุนหมุนเวียน, ดอกเบี้ย, ด้อยค่าสินค้า', metric='วันสินค้าคงคลัง 178 วัน, วงจรเงินสด 151 วัน', nature='โครงสร้าง', level='company', src=ONE + ' หน้า 8 · Oppday Q2/26 หน้า 12'),
    dict(f='การแข่งขันค้าปลีกวัสดุก่อสร้าง', force='การแข่งขันในอุตสาหกรรม', swot='Threat', channel='ยอดขาย, อัตรากำไร', metric='SSSG, อัตรากำไรขั้นต้น', nature='โครงสร้าง', level='company', src=ONE + ' หน้า 8'),
 ],
 'MOSHI': [
    dict(f='การแข่งขันด้านราคาจากร้านค้าและออนไลน์', force='การแข่งขัน และสินค้าทดแทน', swot='Threat', channel='ยอดขาย, อัตรากำไรขั้นต้น', metric='SSSG, อัตรากำไรขั้นต้น', nature='โครงสร้าง', level='company', src=ONE + ' หน้า 41'),
    dict(f='กำลังซื้อและโครงสร้างประชากร', force='อำนาจลูกค้า', swot='Threat', channel='ยอดขายสาขาเดิม', metric='SSSG', nature='ระยะยาว', level='company', src=ONE + ' หน้า 37'),
    dict(f='ค่าเงินและสินค้านำเข้า', force='อำนาจซัพพลายเออร์', swot='Threat', channel='ต้นทุนสินค้า', metric='อัตรากำไรขั้นต้น, USDTHB', nature='รอบค่าเงิน', level='hypothesis', src='บริษัทระบุว่าสินค้านำเข้ามาร์จิ้นสูง (Earning Call หน้า 12) แต่ยังไม่ได้ทดสอบผลของค่าเงิน'),
 ],
 'PR9': [
    dict(f='ผู้ป่วยต่างชาติ และความขัดแย้งตะวันออกกลาง', force='อำนาจลูกค้า', swot='Opportunity / Threat', channel='รายได้ต่างชาติ', metric='รายได้ต่างชาติรายกลุ่ม', nature='เหตุการณ์ภายนอก', level='hypothesis', src='บริษัทระบุกลุ่มตะวันออกกลางเป็นลูกค้าเติบโต (' + ONE + ' หน้า 6) · ผลกระทบจากสงครามยังไม่ได้ทดสอบ'),
    dict(f='ปริมาณผู้ป่วยนอกลดลง', force='การแข่งขัน', swot='Weakness', channel='รายได้', metric='ผู้ป่วยนอกต่อวัน', nature='ยังสรุปไม่ได้', level='hypothesis', src='คำนวณจาก Oppday Q2/26 หน้า 6 ยังไม่รู้เหตุ'),
    dict(f='การแข่งขันโรงพยาบาลและเทคโนโลยี AI', force='การแข่งขันในอุตสาหกรรม', swot='Threat', channel='ส่วนแบ่งตลาด, คุณภาพบริการ', metric='รายได้, จำนวนผู้ป่วย', nature='โครงสร้าง', level='company', src=ONE + ' หน้า 44'),
 ],
}

FACTORS['TURBO'].append(dict(f='ประสิทธิภาพต้นทุนจากเทคโนโลยี/AI', force='—', swot='Strength', channel='ค่าใช้จ่ายในการบริหาร (opex), Cost-to-income', metric='Cost-to-income', nature='โครงสร้าง', level='company', src='Oppday Q2/26 หน้า 6, 10, 11'))

# บรรทัดงบ -> ปัจจัยในแผนที่ (ชื่อ f ต้องตรงกับ FACTORS) · [] = ยังไม่มีปัจจัยในแผนที่ ต้องเพิ่มเมื่อมีหลักฐาน · โยงด้วยตรรกะว่าบรรทัดนั้นได้รับผลจากอะไร ไม่ใช่การพิสูจน์
LINE_LINK = {
 'TURBO': {'rev': ['การแข่งขันสินเชื่อรายย่อย'], 'ecl': ['หนี้ครัวเรือนและรายได้เกษตร'], 'fin': ['อัตราดอกเบี้ยและต้นทุนเงินทุน'], 'admin': ['ประสิทธิภาพต้นทุนจากเทคโนโลยี/AI'], 'gpm': [], 'sell': []},
 'DOHOME': {'rev': ['การแข่งขันค้าปลีกวัสดุก่อสร้าง', 'คุณภาพสินค้าและชื่อเสียง'], 'gpm': ['ราคาเหล็กผันผวน', 'สต๊อกสินค้าสูง'], 'sell': ['การแข่งขันค้าปลีกวัสดุก่อสร้าง'], 'admin': [], 'fin': ['สต๊อกสินค้าสูง']},
 'MOSHI': {'rev': ['กำลังซื้อและโครงสร้างประชากร', 'การแข่งขันด้านราคาจากร้านค้าและออนไลน์'], 'gpm': ['ค่าเงินและสินค้านำเข้า'], 'sell': ['การแข่งขันด้านราคาจากร้านค้าและออนไลน์'], 'admin': [], 'fin': []},
 'PR9': {'rev': ['ผู้ป่วยต่างชาติ และความขัดแย้งตะวันออกกลาง', 'ปริมาณผู้ป่วยนอกลดลง'], 'gpm': ['ปริมาณผู้ป่วยนอกลดลง'], 'sell': ['การแข่งขันโรงพยาบาลและเทคโนโลยี AI'], 'admin': [], 'fin': []},
}
LINE_TH = {'rev': 'รายได้', 'gpm': 'GPM (กำไรขั้นต้น/COGS)', 'sell': 'ค่าใช้จ่ายขาย', 'admin': 'ค่าใช้จ่ายบริหาร', 'fin': 'ต้นทุนการเงิน', 'ecl': 'ผลขาดทุนเครดิต'}
BRIDGE_KEY = {'รายได้รวม': 'rev', 'กำไรขั้นต้น': 'gpm', 'ค่าใช้จ่ายขาย': 'sell', 'ค่าใช้จ่ายบริหาร': 'admin', 'ค่าใช้จ่ายในการบริหาร (opex)': 'admin', 'ต้นทุนการเงิน': 'fin', 'ผลขาดทุนด้านเครดิต': 'ecl'}


def pnl_for(t, q):
    return json.load(open(os.path.join(OUT, f'pnl_{t}.json'), encoding='utf-8'))['quarters'].get(q)


def lines_of(t, x):
    """ตารางบรรทัดงบของไตรมาส: ค่า, ปีก่อน, ผลต่างและผลต่อกำไร, ปัจจัยที่โยง"""
    nb, c, p, y = t == 'TURBO', x['cur'], x['prior'], x['yoy']
    eff = {b['item']: b['delta'] for b in (x['bridge'] or [])}
    bk = {BRIDGE_KEY[k]: v for k, v in eff.items() if k in BRIDGE_KEY}
    bridge = x['bridge']
    if not nb and bk.get('gpm') is not None and c.get('gpm') is not None and p.get('gpm') is not None:
        # แยก Δกำไรขั้นต้น = ผลจากรายได้ (Δรายได้ × GPM ปีก่อน) + ผลจากมาร์จิ้น (ΔGPM × รายได้ปีนี้) ผลรวมเท่ากับ Δกำไรขั้นต้นเดิมพอดี
        bk['rev'] = round((c['rev'] - p['rev']) * p['gpm'] / 100, 2)
        bk['gpm'] = round(bk['gpm'] - bk['rev'], 2)
        bridge = [dict(item='ผลจากรายได้ (Δรายได้ × GPM ปีก่อน)', delta=bk['rev']), dict(item='ผลจากมาร์จิ้น (ΔGPM × รายได้ปีนี้)', delta=bk['gpm'])] + [b for b in x['bridge'] if b['item'] != 'กำไรขั้นต้น']
    spec = [('rev', 'rev', 'ล้านบาท'), ('gpm', 'gpm', '%'), ('sell', 'sell', 'ล้านบาท'), ('admin', 'admin', 'ล้านบาท'), ('fin', 'fin', 'ล้านบาท')] if not nb else [('rev', 'rev', 'ล้านบาท'), ('admin', 'admin', 'ล้านบาท'), ('ecl', 'ecl', 'ล้านบาท'), ('fin', 'fin', 'ล้านบาท')]
    rows = []
    for key, f, unit in spec:
        if c.get(f) is None:
            continue
        d = y.get(f)
        rows.append(dict(line=key, name=LINE_TH[key], unit=unit, cur=c[f], prior=p.get(f), delta=d['delta'] if d else None, pct=d['pct'] if d else None, profit_effect=bk.get(key), links=LINE_LINK[t].get(key, [])))
    if not nb and c.get('cogs') is not None:
        rows.insert(2, dict(line='cogs', name='COGS (ต้นทุนขาย)', unit='ล้านบาท', cur=c['cogs'], prior=p.get('cogs'), delta=y['cogs']['delta'] if 'cogs' in y else None, pct=y['cogs']['pct'] if 'cogs' in y else None, profit_effect=None, links=LINE_LINK[t].get('gpm', [])))
    ranked = sorted([(k, v) for k, v in bk.items() if v is not None], key=lambda kv: -abs(kv[1]))[:2]
    return dict(quarter=None, rows=rows, bridge=bridge, drivers=[dict(line=LINE_TH[k], effect=v) for k, v in ranked])


for t, v in stocks.items():
    pj = json.load(open(os.path.join(OUT, f'pnl_{t}.json'), encoding='utf-8'))
    for e in v['events']:
        m = pj['events'].get(e['date'])
        if e['status'] == 'found' and e['type'] == 'earnings' and m and pnl_for(t, m['quarter']):
            e['pnl'] = lines_of(t, pnl_for(t, m['quarter']))
            e['pnl']['quarter'] = m['quarter']
            e['pnl']['filed'] = f"{m['filed']} {m['time']}"
        elif e['status'] == 'found' and e['type'] == 'company_news':
            e['pnl_follow'] = [{**lines_of(t, pnl_for(t, q)), 'quarter': q} for q in ('2025Q2', '2025Q3') if pnl_for(t, q)] if t == 'DOHOME' else []
    qs = sorted(pj['quarters'])[-8:]
    v['quarters'] = [dict(q=q, **{k: pj['quarters'][q]['cur'].get(k) for k in ('rev', 'gpm', 'sell_pct', 'admin_pct', 'fin', 'ecl', 'np')}, yoy_np=(pj['quarters'][q]['yoy'].get('np') or {}).get('pct')) for q in qs]
    v['weekly'] = json.load(open(os.path.join(OUT, f'weekly_{t}.json'), encoding='utf-8'))

data = dict(stocks=stocks, oppday=OPPDAY, watch=WATCH, next=NEXT, factors=FACTORS, steel=steel)
html = open(os.path.join(os.path.dirname(__file__), 'dashboard_template.html'), encoding='utf-8').read()
html = html.replace('/*DATA*/null', json.dumps(data, ensure_ascii=False).replace('</', '<\\/'))
open(os.path.join(OUT, 'dashboard.html'), 'w', encoding='utf-8').write(html)
print(f'dashboard.html {len(html):,} bytes · stocks={list(stocks)} events={sum(len(v["events"]) for v in stocks.values())}')
