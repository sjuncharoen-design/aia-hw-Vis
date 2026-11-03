# output/

ใส่ผลงานของคุณที่นี่

- ภาพหน้าจอ dashboard หรือผลวิเคราะห์ (`.png`, `.jpg`)
- ลิงก์ผลงานที่เปิดดูได้ (เขียนไว้ในไฟล์นี้)
- ไฟล์ผลลัพธ์เล็ก ๆ ที่สร้างเอง เช่น หน้า Price Move (`price_move/*.html`)

ห้ามใส่: ไฟล์ข้อมูลดิบที่ซื้อมา (เช่น SETSMART), บทวิเคราะห์โบรกเกอร์, ข้อมูลพอร์ตจริง

## ลิงก์ผลงาน

- หน้า Price Move ต่อหุ้น (เปิดไฟล์ในเบราว์เซอร์): [TURBO](price_move/TURBO.html) · [DOHOME](price_move/DOHOME.html) · [MOSHI](price_move/MOSHI.html) · [PR9](price_move/PR9.html)
- หน้าสรุปรวมทุกหุ้น: [dashboard.html](dashboard.html)
- ภาพรวมระบบ: [architecture.html](architecture.html)

## สร้างหน้าใหม่

ขั้นสร้างหน้าและตรวจหน้ารันซ้ำได้จากไฟล์ใน `output/price_move/<T>/` (ไม่ต้องมีเอกสารบริษัท):

```bash
D=output/price_move/TURBO
python .claude/skills/price-move/scripts/build_page.py TURBO --events $D/events.json --takeaways $D/takeaways.json --pnl $D/pnl.json --price-dir $D --out-dir $D --extras $D/extras.json --public --out output/price_move/TURBO.html
```

ขั้นอ่านเอกสารบริษัทต้องตั้ง `PRICE_MOVE_RAW` เป็นโฟลเดอร์ AllCompany ในเครื่อง ดูขั้นตอนเต็มใน `.claude/skills/price-move/SKILL.md`
