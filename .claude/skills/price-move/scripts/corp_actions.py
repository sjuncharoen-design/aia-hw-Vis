"""อ่านไฟล์ปันผล/XD ที่ดาวน์โหลดจาก SETSMART (<T>-Dividends.xlsx) เป็นรายการวัน XD
usage: python corp_actions.py DIVIDENDS_XLSX OUT_JSON
output: [{date, kind: cash|stock, amount?, ratio?, price_before?, price_on?}] เรียงตามวัน · ไฟล์ไม่มี = ลิสต์ว่าง (ไม่ crash)
cash = Unit Baht (เงินปันผล) · stock = Unit Share แถวอัตรา เช่น "25 : 1" (หุ้นปันผล) ราคาจาก Yahoo ถูกปรับหุ้นปันผลแล้ว จึงไม่มีรอยกระโดด
ใช้เป็นบริบทของเหตุการณ์เท่านั้น ไม่ใช่สาเหตุในตัวเอง · ใช้ openpyxl อ่านเฉพาะไฟล์ที่ผู้ใช้โหลดเอง
"""
import json, os, sys
from datetime import datetime


def num(x):
    try:
        return float(str(x).strip().replace(',', ''))
    except (TypeError, ValueError):
        return None


def read_dividends(path):
    if not os.path.exists(path):
        return []
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    out = []
    for ws in wb:
        head = None
        for row in ws.iter_rows(values_only=True):
            if row and row[0] == 'Symbol':
                head = {str(c).strip(): i for i, c in enumerate(row) if c}
                continue
            if not head or not row or not row[0] or not isinstance(row[head['X-Date']], datetime):
                continue
            unit = str(row[head['Unit']] or '').strip()
            a = dict(date=row[head['X-Date']].date().isoformat(), kind='cash' if unit == 'Baht' else 'stock',
                     price_before=num(row[head['Price Before X-Date']]) if 'Price Before X-Date' in head else None,
                     price_on=num(row[head['Price On X-Date']]) if 'Price On X-Date' in head else None)
            if a['kind'] == 'cash':
                a['amount'] = num(row[head['Dividend (per Share)']])
            else:
                a['ratio'] = str(row[head['Dividend (per Share)']] or '').replace(' ', '')
            out.append(a)
    return sorted(out, key=lambda a: (a['date'], a['kind']))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    acts = read_dividends(sys.argv[1])
    json.dump(acts, open(sys.argv[2], 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'{len(acts)} corporate actions -> {sys.argv[2]}')
