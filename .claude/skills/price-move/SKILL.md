---
name: price-move
description: "สร้างหน้า HTML ไฟล์เดียวอธิบายว่าราคาหุ้นไทยขยับแรงแต่ละครั้งเพราะอะไร: กราฟราคาปิดรายวันคู่กำไรสุทธิ จุดที่ปิดขยับเกิน 5% ต่อวันและเกิน 10% ในรอบ 5–6 วันทำการ เลื่อนเมาส์เห็นสาเหตุ สรุป Catalyst/Risk เฉพาะที่รู้สาเหตุ การ์ดเจาะลึก ตาราง Draft และ Reference ใช้เมื่อผู้ใช้สั่ง /price-move TICKER หรือถามว่าทำไมหุ้นตัวนี้ขึ้นลงแรง"
effort: high
---

# Price Move (เวอร์ชัน Homework)

ตอบเป็นภาษาไทย ใช้ English สำหรับศัพท์เทคนิค กระชับ ไม่ใช่คำแนะนำการลงทุน
repo นี้เป็น **Public**: ห้ามใส่เนื้อหาโบรก ไฟล์ที่ซื้อมา (SETSMART `.xlsx/.csv`) key หรือ path ส่วนตัว ลง repo
โค้ดชุดนี้เป็นสำเนาจาก skill ในเครื่อง ณ 3 พ.ย. 2026 ไม่ซิงก์กันอัตโนมัติ

ตัวแปร: `M=.claude/skills/price-move/scripts` · `D=output/price_move/[T]` (ข้อมูลระหว่างทางที่ commit ได้) · `K=<scratchpad>/[T]_pack` (pack จากเอกสาร **ห้าม commit**) · `PRICE_MOVE_RAW` = โฟลเดอร์ AllCompany ในเครื่องผู้เรียน (นอก repo)

## กติกา
- เกณฑ์: ปิดรายวันมากกว่า 5% · ปิดเทียบ 5 หรือ 6 วันทำการก่อนมากกว่า 10% (พอดีไม่นับ)
- สถานะมี 2 แบบ **รู้สาเหตุ** และ **Draft** สคริปต์ตัดสินจากหลักฐาน: conf high/mid, ตรงทิศราคา, มีหลักฐานที่ไม่ใช่โบรกซึ่งออกก่อนหรือระหว่างเหตุการณ์
- ลำดับแหล่ง: ข่าว SET → MD&A → Oppday/Earning call → งบและ One Report → สื่อ ใช้ทุกแหล่งพร้อมที่มา **ถ้าขัดกันเชื่อ SET ก่อน** และบันทึกใน `conflicts`
- งบที่ออกหลัง 16:30 น. นับวันทำการถัดไป ข่าวที่ออกหลังเหตุการณ์ไม่ใช่สาเหตุ
- โบรกใช้เฉพาะสรุปเป็นคำของเราเอง (`market_view_public` ไม่ระบุชื่อ) ไม่ใช้ยืนยันสาเหตุ ห้ามคัดลอกข้อความหรือตาราง ไม่มีราคาเป้าหมาย/ประมาณการ
- ไม่มีคำแนะนำซื้อขาย `outlook` เป็นการตีความ เขียนเป็นเงื่อนไขที่ตรวจได้
- อ่านเอกสารผ่าน `.extracted.md` เท่านั้น เขียน JSON ด้วย python เท่านั้น ห้ามแก้ชั้นเอกสารใน `AllCompany` ห้ามเดาตัวเลข ไม่มีที่มาให้เขียน `[ยังไม่ยืนยัน]`

## 1. เตรียมข้อมูล
```bash
mkdir -p $D
# ดัชนี SET จริงอยู่ใน repo แล้ว (data/set_index_history.json)
# แหล่งที่สอง: เซฟผล get_ohlcv(symbol="SET:[T]", interval="1D", count=1300) เป็น $D/tv.json
python $M/price_daily.py [T] $D --tv $D/tv.json --market-file data/set_index_history.json
# แหล่งเดียว: หน้าเว็บจะแจ้งว่าแหล่งเดียว
python $M/price_daily.py [T] $D --single-source --market-file data/set_index_history.json

# วัน XD จากไฟล์ SETSMART ในเครื่อง (ไฟล์ไม่ขึ้น repo) เขียนเฉพาะวันและจำนวนเงิน
python $M/corp_actions.py "<path>/[T]-Dividends.xlsx" $D/corp_actions.json

python $M/detect_events.py $D/price_daily.json $D/events_raw.json --mode both --recon $D/price_recon.json --years 5 --xd $D/corp_actions.json --prev $D/events.json
python $M/pnl_breakdown.py [T] $D/pnl.json --quarterly $D/quarterly.json --browser-news $D/set_news_browser.jsonl
```
- รันครั้งแรกไม่มี `events.json` ไม่ต้องตัด `--prev` สคริปต์ถือว่าเป็นรอบแรก
- XD เป็นบริบท ไม่ใช่สาเหตุในตัวเอง ราคา Yahoo ปรับปันผลแล้ว
- เหตุการณ์มี `vol_ratio` (volume เทียบ 20 วัน) และ `gap` (เปิดเทียบปิดก่อนหน้า)
- **ข่าว SET:** เปิดหน้าข่าวสาธารณะใน browser `https://www.set.or.th/th/market/news-and-alert/news?source=company&symbol=[T]&securityType=S&fromDate=YYYY-MM-DD&toDate=YYYY-MM-DD` แล้วเขียน `$D/set_news_browser.jsonl` แถวละ `{"title","datetime","url"}` **ห้ามเรียก API หรือเลี่ยง bot check** ถ้าติด CAPTCHA ให้หยุดแล้วถามผู้ใช้ ทำก่อนรัน `pnl_breakdown.py`

## 2. อ่านหลักฐานและตัดสิน (model หลักทำเอง ไม่ใช้ sub-agent)
```bash
python $M/build_evidence_pack.py [T] $D/events_raw.json $D/quarterly.json $K --depth normal
```
ได้ `$K/<date>_<kind>.md` ต่อเหตุการณ์ และ `$K/batches.json` (ไม่เกิน 6 เหตุการณ์ต่อชุด) เหตุการณ์ที่รู้สาเหตุแล้วจะถูกข้าม

ไล่ทีละชุด: อ่าน pack ของชุดนั้นแล้วเปิดเฉพาะไฟล์ที่ pack ชี้ (ผ่าน `.extracted.md`) พร้อม `$D/set_news_browser.jsonl` จากนั้นเขียนผลต่อเหตุการณ์ลง `$K/result_<ชุด>.json` ตามรูปแบบใน `assets/result_schema.json`:
- แยกข้อเท็จจริงกับการตีความ ห้ามเดา ข้อที่ไม่มีข้อมูลเขียนว่าไม่มี
- หลักฐานต้องมี `date` และ `time` ถ้าทราบ และ `accessed` ถ้าเป็น URL · `direction_match` = เนื้อหาไปทิศเดียวกับราคาหรือไม่
- หลักฐานจากเอกสารในเครื่องใช้ `src` แบบ `AllCompany/[T]/...` (ไม่ใส่ path เครื่อง)
- ถ้ายังไม่แน่ใจให้ `conf=low` พร้อม `hypothesis` และ `next_check`
- `pnl_quarter` / `pnl_note` / `pnl_links` โยงบรรทัดงบ (rev|gpm|cogs|sell|admin|fin|ecl) กับปัจจัย SWOT/5 Forces พร้อม `level`
- วันที่มี XD ให้พิจารณาก่อนว่าเป็นกลไกปันผลหรือไม่

เสร็จทุกชุดแล้วรวมผล และเก็บสำเนาผลที่ commit ได้ไว้ที่ `$D/results.json`:
```bash
python $M/merge_research.py $D/events_raw.json $K $D/events.json
```

## 3. สรุป
เขียน `$D/takeaways.json`:
```json
{"catalysts": [{"text": "...", "ids": ["2024-02-21_day"], "watch": "..."}], "risks": []}
```
อ้างเฉพาะเหตุการณ์ที่รู้สาเหตุ รวมเหตุการณ์เรื่องเดียวกัน
ส่วนเสริม (ไม่บังคับ) `$D/extras.json`: `oppday` {file, drivers[{t,pg}], risks[]} · `watch` [{t,latest,target,signal}] · `next` [{t,d,basis}] · `factors` [{f,force,swot,channel,level,src}] — `check_page` บังคับให้ oppday มี `file`, factors มี `src`, next มี `basis`

## 4. สร้างและตรวจหน้า
```bash
python $M/build_page.py [T] --events $D/events.json --takeaways $D/takeaways.json --pnl $D/pnl.json --price-dir $D --out-dir $K --extras $D/extras.json   # หน้าส่วนตัว (อาจมีสรุปโบรก) เขียนที่ $K ไม่ใช่ใน repo
python $M/check_page.py $K/price_move.json
python $M/build_page.py [T] ... --public --out output/price_move/[T].html
```
- `check_page.py` ต้อง exit 0 ถ้าไม่ผ่าน ห้ามรายงานว่าเสร็จ
- `--public` ตัดชื่อโบรก ราคาเป้าหมาย ประมาณการ และหยุดถ้ายังพบ (`assets/broker_names.txt`) ให้แก้ข้อความแล้วรันใหม่ ไม่ใช่แก้รายการคำ
- ก่อน commit ให้รัน `python -m pytest tests -q` (มี test สแกนไฟล์ที่ commit)
- รายงานผู้ใช้: จำนวนรู้สาเหตุ/Draft, ราคาตรวจกี่แหล่ง, งวดงบที่อ่านไม่ได้, สิ่งที่ยังไม่ได้ตรวจ

### ส่วนเสริมของหน้า (ไม่บังคับ)
- **ซีรีส์เสริมใต้กราฟราคา** (เช่น ดัชนีราคาเหล็ก สนค. ของ DOHOME): `python $M/series_import.py RAW.json $D/<ชื่อ>.json --id ... --name ... --unit ... --freq monthly --note ... --src <URL> --tier A --accessed YYYY-MM-DD` แล้วใส่ `--series $D/<ชื่อ>.json` ตอน build (ใช้ซ้ำได้) · RAW รายเดือน = `[{y,m,index,yoy?,mom?}]` จุดวางที่วันสิ้นเดือน · หยุดถ้าเดือนซ้ำ/ค่าว่าง · แหล่งต้องมีวันที่เข้าถึง · ดัชนีเหล็ก สนค.: เปิด `https://index.tpso.go.th` ใน browser แล้วเรียก POST `/api/cmi/filter` (API ที่หน้าเว็บของ สนค. ใช้เอง ระบุใน API Document) ด้วย `{YearBase:2564,TimeOption:true,Categories:["4"],Period:{StartYear:<พ.ศ.>,StartMonth,EndYear,EndMonth}}` (หมวด 4 = เหล็กและผลิตภัณฑ์เหล็ก) และตรวจกับรายงาน PDF รายเดือนของ สนค. อย่างน้อย 1 เดือน
- **เทียบตลาดคาด:** ต่อเหตุการณ์งบใส่ `vs_consensus: {verdict: above|inline|below|null, pct, note, src[]}` เก็บเฉพาะคำตัดสินและ % ที่สื่อรายงาน เป็นคำของเราเอง ไม่ใส่ตัวเลขประมาณการ ชื่อโบรก หรือลิงก์รายงานโบรก ถ้าหาไม่ได้ให้ `verdict=null` และ note ขึ้นต้น `[ยังไม่ยืนยัน]` ไม่เดา · `check_page` บังคับให้ verdict มีที่มา

## 5. หน้าสรุปรวม
```bash
python $M/build_index.py --pages-dir output/price_move --out output/dashboard.html
```
อ่านจากหน้า `output/price_move/*.html` ที่สร้างแล้ว หยุดถ้าพบชื่อโบรกหรือคำต้องห้าม

## เพิ่มหุ้นใหม่
ไม่ต้องแก้โค้ด: ทำขั้น 1–4 ด้วย ticker ใหม่ ข้อมูลจะอยู่ที่ `output/price_move/[T]/` และหน้าที่ `output/price_move/[T].html`
