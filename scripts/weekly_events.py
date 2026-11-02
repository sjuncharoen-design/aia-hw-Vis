"""สัปดาห์ที่ราคาปิดขยับเกิน 10% (ปิดวันทำการสุดท้ายของสัปดาห์ เทียบปิดวันทำการสุดท้ายของสัปดาห์ก่อน) แล้วโยงกับวันรายวันที่ขยับเกิน 5% ในสัปดาห์นั้น
usage: python scripts/weekly_events.py        (หลัง make_events_all.py)
input : output/prices_<T>.csv · factors_TDEX.csv · events_all.json
output: output/weekly_<T>.json
สัปดาห์ = จันทร์–ศุกร์ตามปฏิทิน ISO · kind: spike = มีวันรายวันเกิน 5% ทิศเดียวกับสัปดาห์ · drift = ไม่มีวันเกิน 5% ทิศเดียวกันเลย (ราคาสะสมทีละน้อย)
status: found ถ้ามีวันรายวันที่พบสาเหตุทิศเดียวกับสัปดาห์ · lead ถ้ามีเบาะแสรายวัน · unknown นอกนั้น
"""
import csv, json, os, statistics as st
from datetime import date

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'output')
THRESH = 10.0


def week_key(d):
    y, w, _ = date.fromisoformat(d).isocalendar()
    return f'{y}-W{w:02d}'


def main():
    ev_all = json.load(open(os.path.join(OUT, 'events_all.json'), encoding='utf-8'))
    tdex = {r['date']: float(r['close']) for r in csv.DictReader(open(os.path.join(OUT, 'factors_TDEX.csv'), encoding='utf-8'))}
    summary = {}
    for t, v in ev_all.items():
        rows = list(csv.DictReader(open(os.path.join(OUT, f'prices_{t}.csv'), encoding='utf-8')))
        weeks = {}
        for r in rows:
            weeks.setdefault(week_key(r['date']), []).append(r)
        keys = sorted(weeks)
        wk_vol = [sum(float(x['volume'] or 0) for x in weeks[k]) for k in keys]
        daily = {e['date']: e for e in v['events']}
        out, prev_close, prev_mkt = [], None, None
        for i, k in enumerate(keys):
            rs = weeks[k]
            close, d0, d1 = float(rs[-1]['close']), rs[0]['date'], rs[-1]['date']
            mk = tdex.get(d1)
            if prev_close is not None:
                ret = (close / prev_close - 1) * 100
                if abs(ret) > THRESH:
                    mret = (mk / prev_mkt - 1) * 100 if mk and prev_mkt else None
                    in_week = [daily[r['date']] for r in rs if r['date'] in daily]
                    same = [e for e in in_week if e['ret'] * ret > 0]
                    base = [x for x in wk_vol[max(0, i - 8):i] if x]
                    found = [e for e in same if e['status'] == 'found']
                    lead = [e for e in same if e['status'] == 'lead']
                    out.append(dict(week=k, start=d0, end=d1, prev_close=round(prev_close, 2), close=round(close, 2), ret=round(ret, 2), dir='up' if ret > 0 else 'down',
                                    mkt=round(mret, 2) if mret is not None else None, residual=round(ret - (mret or 0), 2), vol_ratio=round(wk_vol[i] / (sum(base) / len(base)), 2) if base else None,
                                    kind='spike' if same else 'drift', days=[dict(date=e['date'], ret=e['ret'], status=e['status'], type=e['type']) for e in in_week],
                                    market=bool(not found and mret is not None and mret * ret > 0 and abs(mret) >= 0.5 * abs(ret)), status='found' if found else 'lead' if (lead or (mret is not None and mret * ret > 0 and abs(mret) >= 0.5 * abs(ret))) else 'unknown', types=sorted({e['type'] for e in found}),
                                    why=' · '.join(f"{e['date']}: {e['why']}" for e in found) if found else None))
            prev_close, prev_mkt = close, mk
        json.dump(dict(ticker=t, threshold=THRESH, weeks_total=len(keys) - 1, weeks=out), open(os.path.join(OUT, f'weekly_{t}.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        c = {k: sum(w['status'] == k for w in out) for k in ('found', 'lead', 'unknown')}
        summary[t] = (len(out), len(keys) - 1, c, sum(w['kind'] == 'drift' for w in out), sum(1 for w in out if any(d['status'] == 'found' for d in w['days'])))
        print(t, f'weeks>10%={len(out)}/{len(keys) - 1}', c, 'drift', summary[t][3])


if __name__ == '__main__':
    main()
