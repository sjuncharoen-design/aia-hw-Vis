---
name: price-move
description: "สร้างหน้า HTML ไฟล์เดียวอธิบายว่าราคาหุ้นไทยขยับแรงแต่ละครั้งเพราะอะไร: กราฟราคาปิดรายวันคู่กำไรสุทธิ จุดที่ปิดขยับเกิน 5% ต่อวันและเกิน 10% ในรอบ 5–6 วันทำการ เลื่อนเมาส์เห็นสาเหตุ สรุป Catalyst/Risk เฉพาะที่รู้สาเหตุ การ์ดเจาะลึก ตาราง Draft และ Reference ใช้เมื่อผู้ใช้สั่ง /price-move TICKER หรือถามว่าทำไมหุ้นตัวนี้ขึ้นลงแรง"
effort: high
disable-model-invocation: true
---

> สำเนาให้อ่าน ตัวรันจริงและสคริปต์อยู่ที่ repo `3_Stocks_Analyst` (`.claude/skills/price-move/`) เพราะต้องใช้ข้อมูลดิบและสรุปโบรกที่ขึ้น repo Public ไม่ได้ ผลลัพธ์แบบ Public อยู่ที่ `output/price_move/`

# Price Move

ตอบเป็นภาษาไทย ใช้ English สำหรับศัพท์เทคนิค กระชับ ไม่ใช่คำแนะนำการลงทุน
ต่อยอดสคริปต์ของ `thai-stock-fundamental-dashboard` ต่างกันตรงที่ไม่บังคับอ่านทุกไฟล์ และรันซ้ำแล้ววิเคราะห์เฉพาะ Draft กับเหตุการณ์ใหม่

ตัวแปร: `S=.claude/skills/thai-stock-fundamental-dashboard/scripts` · `M=.claude/skills/price-move/scripts` · `O=AllCompany/[T]/_output/PriceMove` · `D=<scratchpad>/[T]_data` · `K=<scratchpad>/[T]_pack`

## กติกา
- เกณฑ์: ปิดรายวันมากกว่า 5% · ปิดเทียบ 5 หรือ 6 วันทำการก่อนมากกว่า 10% (พอดีไม่นับ)
- สถานะมี 2 แบบ **รู้สาเหตุ** และ **Draft** สคริปต์ตัดสินจากหลักฐาน: conf high/mid, ตรงทิศราคา, มีหลักฐานที่ไม่ใช่โบรกซึ่งออกก่อนหรือระหว่างเหตุการณ์
- ลำดับแหล่ง: ข่าว SET → MD&A → Oppday/Earning call → งบและ One Report → สรุปโบรกและสื่อ ใช้ทุกแหล่งพร้อมที่มา **ถ้าขัดกันเชื่อ SET ก่อน** และบันทึกใน `conflicts`
- งบที่ออกหลัง 16:30 น. นับวันทำการถัดไป ข่าวที่ออกหลังเหตุการณ์ไม่ใช่สาเหตุ
- โบรกใช้เฉพาะสรุปเป็นคำของเราเอง ใส่ใน `market_view` ไม่ใช้ยืนยันสาเหตุ ห้ามคัดลอกข้อความหรือตาราง
- ไม่มีคำแนะนำซื้อขาย `outlook` เป็นการตีความ เขียนเป็นเงื่อนไขที่ตรวจได้
- อ่านเอกสารผ่าน `.extracted.md` เท่านั้น เขียน JSON ด้วย python เท่านั้น ห้ามแก้ชั้นเอกสารใน `AllCompany` ห้ามเดาตัวเลข

## 1. เตรียมข้อมูล
```bash
# TradingView ใช้ได้: เซฟผล get_ohlcv(symbol="SET:[T]", interval="1D", count=1300) เป็น $D/tv.json
python $S/price_daily.py [T] $D --tv $D/tv.json --market-symbol TDEX.BK
# TradingView ใช้ไม่ได้: หน้าเว็บจะแจ้งว่าแหล่งเดียว
python $S/price_daily.py [T] $D --single-source --market-symbol TDEX.BK

python $S/detect_events.py $D/price_daily.json $D/events_raw.json --mode both --recon $D/price_recon.json --years 5 --prev $O/price_move.json
python $M/pnl_breakdown.py [T] $D/pnl.json --quarterly $D/quarterly.json --browser-news $O/set_news_browser.jsonl
```
- รันครั้งแรกไม่มี `price_move.json` ให้ตัด `--prev` ออก
- **ข่าว SET:** ใช้ `AllCompany/[T]/News/set_news_*.jsonl` ก่อน ถ้าไม่ครอบวันเกิดเหตุ เปิดหน้าข่าวสาธารณะใน browser ที่ `https://www.set.or.th/th/market/news-and-alert/news?source=company&symbol=[T]&securityType=S&fromDate=YYYY-MM-DD&toDate=YYYY-MM-DD` แล้วเขียน `$O/set_news_browser.jsonl` แถวละ `{"title","datetime","url"}` **ห้ามเรียก API หรือเลี่ยง bot check** ถ้าติด CAPTCHA ให้หยุดแล้วถามผู้ใช้

## 2. อ่านหลักฐาน
```bash
python $S/build_evidence_pack.py [T] $D/events_raw.json $D/quarterly.json $K --depth normal
```
ได้ `$K/<date>_<kind>.md` และ `$K/batches.json` เหตุการณ์ที่รู้สาเหตุแล้วจะถูกข้าม ส่ง sub-agent ทุก batch ในข้อความเดียว:
`Agent(subagent_type="general-purpose", model="sonnet", description="หาสาเหตุราคา [T] batch N")`
```
คุณคือผู้ช่วยนักวิเคราะห์หุ้นไทย หาสาเหตุที่ราคา <T> ขยับในเหตุการณ์ของ batch <N> ใน <K>/batches.json อ่าน pack แต่ละใบ แล้วอ่านเอกสารที่ pack ชี้ และ <O>/set_news_browser.jsonl ถ้ามี
ลำดับแหล่ง: ข่าว SET → MD&A → Oppday/Earning call → งบและ One Report → สรุปโบรกและสื่อ ถ้าขัดกันเชื่อ SET และบันทึกใน conflicts · อ่านผ่าน .extracted.md เท่านั้น
แยกข้อเท็จจริงกับการตีความ ห้ามเดา ข้อที่ไม่มีข้อมูลเขียนว่าไม่มี · ไม่มีคำแนะนำซื้อขาย · ห้ามคัดลอกข้อความโบรก สรุปเป็นคำของเราเอง
หลักฐานต้องมี date และ time ถ้าทราบ และ accessed ถ้าเป็น URL · direction_match = เนื้อหาไปทิศเดียวกับราคาหรือไม่
ถ้ายังไม่แน่ใจให้ conf=low พร้อม hypothesis และ next_check · pnl_quarter = งวดที่เกี่ยวข้อง ถ้าไม่เกี่ยวกับงบใช้ pnl_note
pnl_links โยงบรรทัดงบ (rev|gpm|cogs|sell|admin|fin|ecl) กับปัจจัย SWOT/5 Forces พร้อม level ถ้าบริษัทไม่ได้ระบุเองให้ใช้ hypothesis
รูปแบบผลลัพธ์: .claude/skills/price-move/assets/result_schema.json · เขียน <K>/result_<N>.json ด้วย python · ตอบสั้น ๆ ว่ารู้สาเหตุกี่เหตุการณ์
```
```bash
python $S/merge_research.py $D/events_raw.json $K $D/events.json
```

## 3. สรุป (model หลัก)
ทบทวนผลเหตุการณ์ที่ conf high/mid แล้วเขียน `$D/takeaways.json` ด้วย python:
```json
{"catalysts": [{"text": "...", "ids": ["2024-02-21_day"], "watch": "..."}], "risks": []}
```
- อ้างเฉพาะเหตุการณ์ที่รู้สาเหตุ รวมเหตุการณ์ที่เป็นเรื่องเดียวกัน Catalyst = ฝั่งขึ้น Risk = ฝั่งลง
- ถ้าจะทำหน้า Public ให้เขียน `market_view_public` ของเหตุการณ์ที่รู้สาเหตุด้วย

## 4. สร้างและตรวจหน้า
```bash
python $M/build_page.py [T] --events $D/events.json --takeaways $D/takeaways.json --pnl $D/pnl.json --price-dir $D --out-dir $O
python $M/check_page.py $O/price_move.json
```
- `check_page.py` ต้อง exit 0 ถ้าไม่ผ่าน ห้ามรายงานว่าเสร็จ
- ไฟล์ออก: `$O/YYYYQQ/YYYYQQ_PriceMove_[T].html` เปิดใน browser เพื่อตรวจการเลื่อนเมาส์และจอแคบ
- รายงานผู้ใช้: จำนวนรู้สาเหตุ/Draft, ราคาตรวจกี่แหล่ง, งวดงบที่อ่านไม่ได้, สิ่งที่ยังไม่ได้ตรวจ

**หน้าสำหรับ repo Public:** เพิ่ม `--public --out <ไฟล์>` คำสั่งจะตัดชื่อโบรก ราคาเป้าหมาย และแหล่งจากโฟลเดอร์ Broker และหยุดถ้ายังพบคำต้องห้าม (`assets/broker_names.txt`) ให้แก้ข้อความแล้วรันใหม่ ไม่ใช่แก้รายการคำ
