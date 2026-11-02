"""ทดสอบปัจจัยภายนอกกับอัตรากำไรขั้นต้นรายไตรมาสของ DOHOME (ราคาเหล็ก HRC=F เป็นตัวแทน ไม่ใช่ราคาเหล็กไทย)
usage: python scripts/factor_test.py [--raw DIR]   (อ่าน output/factors_HRC.csv และ FS .extracted.md ในเครื่อง)
output: output/factor_DOHOME.json · Q4 = ทั้งปี − 9 เดือน · ผลเป็นแค่ "สอดคล้อง/ไม่สอดคล้อง" ไม่ใช่การพิสูจน์เหตุและผล
"""
import argparse, csv, glob, json, os, re, statistics as st, sys

sys.stdout.reconfigure(encoding='utf-8')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'output')


def first_num(line):
    m = re.findall(r'\|\s*(-?\d[\d,.]*)\s*(?=\|)', line)
    return float(m[0].replace(',', '')) if m else None


def read_fs(path):
    """ยอดขายและต้นทุนขาย ของตารางแรก (งวดปัจจุบันของงบรวม) หน่วยบาท"""
    text = open(path, encoding='utf-8', errors='ignore').read().splitlines()
    sales = next((first_num(l) for l in text if re.match(r'\|\s*รายได้จากการขาย', l)), None)
    cost = next((first_num(l) for l in text if re.match(r'\|\s*ต้นทุนขาย', l)), None)
    if not sales or not cost:
        return None
    k = 1 if sales > 5e8 else 1000
    return sales * k, cost * k


def nine_month(path):
    """ยอดขายและต้นทุนขาย ของตารางเก้าเดือน (แถวที่สองในงบไตรมาส 3)"""
    text = open(path, encoding='utf-8', errors='ignore').read().splitlines()
    s = [first_num(l) for l in text if re.match(r'\|\s*รายได้จากการขาย', l)]
    c = [first_num(l) for l in text if re.match(r'\|\s*ต้นทุนขาย', l)]
    if len(s) < 2 or len(c) < 2 or not s[1] or not c[1]:
        return None
    k = 1 if s[1] > 5e8 else 1000
    return s[1] * k, c[1] * k


ap = argparse.ArgumentParser()
ap.add_argument('--raw', default='D:/3_Stocks_Analyst/AllCompany')
a = ap.parse_args()
base = os.path.join(a.raw, 'DOHOME', 'Financial statement')
if not os.path.isdir(base):
    sys.exit(f'ไม่พบโฟลเดอร์ข้อมูลดิบ: {base}')
files = {}
for p in glob.glob(os.path.join(base, '20*_FS_DOHOME*.extracted.md')):
    files[os.path.basename(p)[:6]] = p
gpm = {}
for q, p in sorted(files.items()):
    if q < '2021Q4':
        continue
    y, n = q[:4], q[5]
    v = read_fs(p)
    if v is None:
        continue
    if n == '4':
        p9 = files.get(f'{y}Q3')
        nm = nine_month(p9) if p9 else None
        if nm is None:
            continue
        v = (v[0] - nm[0], v[1] - nm[1])
    gpm[q] = round((1 - v[1] / v[0]) * 100, 2)
ends = {'1': ('01', '03'), '2': ('04', '06'), '3': ('07', '09'), '4': ('10', '12')}
hrc = list(csv.DictReader(open(os.path.join(OUT, 'factors_HRC.csv'), encoding='utf-8')))
avg = {}
for q in gpm:
    a0, b0 = ends[q[5]]
    vals = [float(r['close']) for r in hrc if f'{q[:4]}-{a0}' <= r['date'][:7] <= f'{q[:4]}-{b0}']
    if vals:
        avg[q] = st.mean(vals)
qs = sorted(q for q in gpm if q in avg)
rows = []
for x, y in zip(qs, qs[1:]):
    rows.append(dict(q=y, gpm=gpm[y], d_gpm=round(gpm[y] - gpm[x], 2), hrc_chg=round((avg[y] / avg[x] - 1) * 100, 1)))
pairs = [(r['hrc_chg'], r['d_gpm']) for r in rows]
xm, ym = st.mean(p[0] for p in pairs), st.mean(p[1] for p in pairs)
corr = sum((p[0] - xm) * (p[1] - ym) for p in pairs) / (sum((p[0] - xm) ** 2 for p in pairs) ** .5 * sum((p[1] - ym) ** 2 for p in pairs) ** .5)
same = sum(1 for p in pairs if p[0] * p[1] > 0)
res = dict(n=len(rows), corr=round(corr, 2), same_direction=same, rows=rows, note='HRC=F เป็นราคาเหล็กแผ่นรีดร้อนสหรัฐฯ ใช้เป็นตัวแทนเท่านั้น · เทียบการเปลี่ยนแปลงรายไตรมาส (QoQ) ไม่ตัดฤดูกาล')
json.dump(res, open(os.path.join(OUT, 'factor_DOHOME.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(res['n'], 'corr', res['corr'], 'same', same, [(r['q'], r['gpm'], r['hrc_chg']) for r in rows])
