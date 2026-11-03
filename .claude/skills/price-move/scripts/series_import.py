"""แปลงข้อมูลอนุกรมที่สกัดแล้วเป็นไฟล์ซีรีส์สำหรับ build_page.py --series
usage: python series_import.py RAW_JSON OUT_JSON --id ID --name NAME --unit UNIT --freq monthly|daily --note NOTE --src URL --tier A --accessed YYYY-MM-DD
RAW_JSON : monthly = [{y, m, index, yoy?, mom?}] · daily = [{d, index, ...}]
หยุดและไม่เขียนไฟล์ถ้า: มีเดือน/วันซ้ำ · ค่าว่าง · ไม่มีที่มาหรือวันที่เข้าถึง
monthly ใช้วันสิ้นเดือนเป็นวันที่ของจุด (ดัชนีรายเดือนเผยแพร่ช่วงต้นเดือนถัดไป จึงไม่ย้อนไปใช้ก่อนสิ้นเดือน)"""
import argparse, calendar, json, os, sys


def convert(raw, freq):
    rows, seen = [], set()
    for r in raw:
        if freq == 'monthly':
            d = f"{r['y']:04d}-{r['m']:02d}-{calendar.monthrange(r['y'], r['m'])[1]:02d}"
        else:
            d = r['d']
        if r.get('index') is None:
            sys.exit(f'หยุด: {d} ไม่มีค่า')
        if d in seen:
            sys.exit(f'หยุด: {d} ซ้ำ')
        seen.add(d)
        row = dict(d=d, p=float(r['index']))
        for k in ('yoy', 'mom'):
            if r.get(k) is not None:
                row[k] = float(r[k])
        rows.append(row)
    return sorted(rows, key=lambda x: x['d'])


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser()
    ap.add_argument('raw'); ap.add_argument('out')
    for f in ('--id', '--name', '--unit', '--freq', '--note', '--src', '--tier', '--accessed'):
        ap.add_argument(f, required=True)
    a = ap.parse_args()
    if a.freq not in ('monthly', 'daily'):
        sys.exit('หยุด: --freq ต้องเป็น monthly หรือ daily')
    rows = convert(json.load(open(a.raw, encoding='utf-8')), a.freq)
    if not rows:
        sys.exit('หยุด: ไม่มีข้อมูล')
    out = dict(id=a.id, name=a.name, unit=a.unit, freq=a.freq, note=a.note, src=[dict(src=a.src, tier=a.tier, accessed=a.accessed)], rows=rows)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(out, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'{len(rows)} rows {rows[0]["d"]}..{rows[-1]["d"]} -> {a.out}')
