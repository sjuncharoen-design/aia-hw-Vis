"""Build one evidence pack per price event so research sub-agents read the right local files first.
usage: python build_evidence_pack.py TICKER EVENTS_JSON QUARTERLY_JSON OUT_DIR [--raw DIR] [--broker FILE] [--batch 6]
       [--digest PACK_DIR/raw_digest.json] [--deepdive PACK_DIR/deepdive_ctx.json]
       [--depth light|normal|deep] [--max-bytes 6000]
  --depth        : how hard the research agents may search the web per event (written to OUT_DIR/config.json and into every pack):
                   light = local documents only (0 searches) · normal = <=1 search (default) · deep = <=3 searches
  --max-bytes    : hard cap for one pack file (UTF-8 bytes). Lowest-value sections are trimmed first (0 = no cap)
  daily events (kind "day") look only at the event day T and the next day T+1 (a Friday event also covers Monday);
  weekly/trend events keep the old window (-42 days .. +14 days).
  EVENTS_JSON    : output of detect_events.py
  QUARTERLY_JSON : quarterly.json dataset (q, rev, gpm, np, rev_yoy, np_yoy, np_qoq ...)
  --raw          : default $PRICE_MOVE_RAW/<TICKER> (AllCompany ถ้าไม่ตั้ง)
  --broker       : ไฟล์สรุปโบรก (ไม่ระบุ = ไม่อ่าน)
  --digest       : merged digest of every raw file (raw_inventory.py --check) — dated facts inside the window are listed
  --deepdive     : deepdive_context.py output — causes Deepdive already found for moves in the window + its facts for the
                   quarter(s) in play. Context only: tier B, must be re-verified against raw files, never copied as a conclusion
writes OUT_DIR/<date>_<kind>.md per event + OUT_DIR/batches.json (events grouped for parallel agents)
Only .extracted.md caches are listed (raw pdf/xlsx/docx are blocked by hook). Files whose name carries
another ticker (YYYYQQ_Type_OTHER) are skipped — folder is not proof of ticker.
"""
import argparse, glob, json, os, re
from datetime import date, timedelta

TH_MON = ['มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน', 'กรกฎาคม', 'สิงหาคม',
          'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม']
TH_ABBR = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.']
EN_MON = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October',
          'November', 'December']
BIG = 300_000
DEPTH = {'light': 0, 'normal': 1, 'deep': 3}  # web searches allowed per event
DEFAULT_MAX_BYTES = 6000
DOC_TYPES = {'MDA': 'mda', 'Earningcall': 'earningcall', 'FS': 'fs', 'NOTES': 'notes', 'AuditReport': 'audit'}


def q_end(q):
    """'2023Q3' -> date(2023, 9, 30)"""
    y, n = int(q[:4]), int(q[5])
    return date(y, 3 * n, 30 if n in (2, 3) else 31)


def announce_window(q):
    """SET deadline: Q1-Q3 45 days, Q4 60 days after quarter end (+ slack either side)."""
    e = q_end(q)
    return (e + timedelta(days=40), e + timedelta(days=80)) if q[5] == '4' else (e + timedelta(days=25), e + timedelta(days=65))


def quarter_of(d):
    return f'{d.year}Q{(d.month - 1) // 3 + 1}'


def audit_date(path):
    """board/auditor sign date at the end of the audit report = actual results date. None if not found."""
    try:
        tail = open(path, encoding='utf-8', errors='ignore').read()[-3000:]
    except OSError:
        return None
    m = None
    for m in re.finditer(r'(\d{1,2})\s*(' + '|'.join(TH_MON) + r')\s*(?:พ\.ศ\.\s*)?(\d{4})', tail):
        pass
    if not m:
        return None
    y = int(m.group(3))
    y = y - 543 if y > 2400 else y
    try:
        return date(y, TH_MON.index(m.group(2)) + 1, int(m.group(1)))
    except ValueError:
        return None


def index_raw(raw, ticker):
    """-> list of {path, type, q, pub, size, idx}"""
    docs = []
    for p in glob.glob(os.path.join(raw, '**', '*.extracted.md'), recursive=True):
        name = os.path.basename(p)
        if name.endswith('.idx.md'):
            continue
        rel = p.replace('\\', '/')
        d = {'path': rel, 'size': os.path.getsize(p), 'q': None, 'pub': None}
        idx = p[:-3] + '.idx.md'
        d['idx'] = idx.replace('\\', '/') if os.path.exists(idx) else None
        m = re.match(r'(\d{4}Q[1-4])_([A-Za-z]+)_([A-Z0-9]+)', name)
        if m:
            if ticker not in re.split(r'[_.\s-]', name):
                continue
            d['q'], d['type'] = m.group(1), DOC_TYPES.get(m.group(2), m.group(2).lower())
        elif '/OneReport/' in rel:
            m = re.search(r'ONE(\d{2})(\d{2})(\d{4})', rel)
            if not m or 'STRUCTURE' in name.upper():
                continue
            d['type'], d['pub'] = 'onereport', date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        else:
            m = re.search(r'(\d{4}-\d{2}-\d{2})', name)
            folder = rel.split('/')[-2]
            d['type'] = {'News': 'news', 'Broker': 'broker', 'Analysis Report': 'broker'}.get(folder, folder.lower())
            d['pub'] = date.fromisoformat(m.group(1)) if m else None
        docs.append(d)
    return docs


def news_items(raw, start, end):
    """SET news headlines (set_news_*.jsonl) dated inside [start, end]."""
    out = []
    for f in glob.glob(os.path.join(raw, 'News', 'set_news_*.jsonl')):
        for line in open(f, encoding='utf-8', errors='ignore'):
            try:
                n = json.loads(line)
                d = date.fromisoformat(n['datetime'][:10])
            except (ValueError, KeyError):
                continue
            if start <= d <= end:
                out.append((d.isoformat(), n.get('title', ''), n.get('url', '')))
    return sorted(set(out))


def month_patterns(d):
    i, be = d.month - 1, d.year + 543
    return [f'{TH_MON[i]} {d.year}', f'{TH_MON[i]} {be}', f'{TH_ABBR[i]} {d.year}', f'{TH_ABBR[i]} {be}',
            f'{TH_ABBR[i]} {str(be)[2:]}', f'{EN_MON[i]} {d.year}', f'{EN_MON[i][:3]} {d.year}', d.strftime('%Y-%m')]


# lines worth showing from MD&A / earning call so the agent often needs not open the file at all
KEYWORDS = ('กำไรสุทธิ', 'กำไรขั้นต้น', 'อัตรากำไร', 'ราคาขาย', 'ราคาวัตถุดิบ', 'ต้นทุน', 'ปริมาณ', 'ยอดขาย',
            'รายได้จากการขาย', 'เงินปันผล', 'คาดว่า', 'เป้าหมาย', 'net profit', 'gross margin', 'guidance')


def date_hits(path, pats, limit=8):
    hits = []
    try:
        for n, line in enumerate(open(path, encoding='utf-8', errors='ignore'), 1):
            if any(p in line for p in pats):
                hits.append((n, line.strip()[:160]))
                if len(hits) >= limit:
                    break
    except OSError:
        pass
    return hits


def fmt_q(r, prev_y):
    g = lambda k: r.get(k)
    s = [f"rev {g('rev'):,.0f}M" if g('rev') is not None else None,
         f"rev YoY {g('rev_yoy'):+.1f}%" if g('rev_yoy') is not None else None,
         f"GPM {g('gpm'):.1f}%" if g('gpm') is not None else None,
         f"GPM YoY {g('gpm') - prev_y['gpm']:+.1f}pp" if prev_y and g('gpm') is not None and prev_y.get('gpm') is not None else None,
         f"NP {g('np'):,.0f}M" if g('np') is not None else None,
         f"NP YoY {g('np_yoy'):+.1f}%" if g('np_yoy') is not None else None,
         f"NP QoQ {g('np_qoq'):+.1f}%" if g('np_qoq') is not None else None,
         f"core {g('core_np'):,.0f}M (YoY {g('core_yoy'):+.1f}%)" if g('core_np') is not None and g('core_yoy') is not None else
         f"core {g('core_np'):,.0f}M" if g('core_np') is not None else None,
         f"รายการพิเศษ {g('oneoff_at'):+,.0f}M ({g('oneoff_desc')})" if abs(g('oneoff_at') or 0) >= 0.5 else None]
    return ' · '.join(x for x in s if x)


def event_window(e):
    """(lo, hi) dates whose documents/news can explain the move."""
    s, t = date.fromisoformat(e['date']), date.fromisoformat(e['end'])
    if e.get('kind') == 'day':
        return s, s + timedelta(days=3 if s.weekday() == 4 else 1)
    if e.get('kind') == 'window':
        return s, t + timedelta(days=3 if t.weekday() == 4 else 1)
    return s - timedelta(days=42), t + timedelta(days=14)


def _size(lines):
    return len('\n'.join(lines).encode('utf-8'))


def cap_pack(text, max_bytes):
    """keep a pack (note included) under max_bytes: drop the last list line of the bulkiest sections first, then hard-cut."""
    if not max_bytes or len(text.encode('utf-8')) <= max_bytes:
        return text
    note = '\n- (pack ถูกตัดตาม --max-bytes: เปิด .extracted.md ต้นฉบับเมื่อต้องการรายละเอียด)\n'
    budget = max_bytes - len(note.encode('utf-8'))
    lines = text.rstrip('\n').split('\n')
    for head in ('## ข้อเท็จจริงที่ digest', '## หัวข้อข่าว SET', '## บทวิเคราะห์โบรก', '## ไฟล์ในเครื่อง'):
        while _size(lines) > budget:
            idx = next((i for i, l in enumerate(lines) if l.startswith(head)), None)
            if idx is None:
                break
            j = idx + 1
            while j < len(lines) and not lines[j].startswith('## '):
                j += 1
            if j - idx <= 2:
                break
            del lines[j - 1]
        if _size(lines) <= budget:
            break
    out = '\n'.join(lines)
    while len(out.encode('utf-8')) > budget:
        out = out[:int(len(out) * 0.9)]
    return out.rstrip() + note


def build(ticker, events, quarterly, raw, broker_md, digest=(), deepdive=None, depth='normal', max_bytes=DEFAULT_MAX_BYTES):
    docs = index_raw(raw, ticker)
    qmap = {r['q']: r for r in quarterly}
    ann = {}  # quarter -> (date, source)
    for d in docs:
        if d['type'] == 'audit' and d['q']:
            ad = audit_date(d['path'])
            if ad:
                ann[d['q']] = (ad, 'audit report sign date')
    packs = {}
    for e in events:
        s, t = date.fromisoformat(e['date']), date.fromisoformat(e['end'])
        lo, hi = event_window(e)
        daily = e.get('kind') in ('day', 'window')
        # quarters whose results came out inside/just before the move
        qs_ann = []
        for q in sorted({quarter_of(s - timedelta(days=k)) for k in range(0, 200, 30)} | set(qmap) | {d['q'] for d in docs if d['q']}):
            a = ann.get(q)
            w = (a[0], a[0]) if a else announce_window(q)
            if w[0] <= t + timedelta(days=7) and w[1] >= s - timedelta(days=21):
                qs_ann.append(q)
        q_in = quarter_of(s)  # quarter in which the move happened (its MD&A/EC explain the operating backdrop)
        want_q = set(qs_ann) | {q_in}
        span = f'ปิดรายวัน · หลักฐานช่วง {lo} – {hi}' if daily else f'{e["span_w"]} สัปดาห์'
        L = [f'# Evidence pack {ticker} · {e["date"]} → {e["end"]} ({e["kind"]}, {span})', '',
             f'- ราคา {e["price_from"]} → {e["price_to"]} = **{e["ret"]:+.1f}%** · SET {e["set_ret"]}% · vs SET {e["rel"]} pp'
             + (f' · sector {e["sec_ret"]}% · vs sector {e["rel_sec"]} pp' if e.get('sec_ret') is not None else '')
             + (' · ⚠️ market_hint (ขยับตาม SET)' if e.get('market_hint') else '')
             + (' · ⚠️ sector_hint (ขยับตามกลุ่ม)' if e.get('sector_hint') else '')
             + (' · ⚠️ price_mismatch (ราคา 2 แหล่งไม่ตรงวันนี้: conf ห้ามเป็น high)' if e.get('price_mismatch') else '')
             + (' · ราคาตรวจ 2 แหล่งแล้ว' if e.get('price_verified') else ' · ราคาแหล่งเดียว (ยังไม่ได้ cross-check)' if 'price_verified' in e else ''),
             f'- ความลึกการค้น: **{depth}** — ค้นเว็บได้ไม่เกิน {DEPTH[depth]} ครั้งสำหรับ event นี้'
             + (' (อ่านเอกสารในเครื่องเท่านั้น)' if not DEPTH[depth] else ''),
             f'- ไตรมาสที่ประกาศงบในช่วงนี้: {", ".join(qs_ann) or "ไม่มี"} · ไตรมาสที่ event เกิด: {q_in}', '']
        if e.get('why'):
            L += ['## ผลรอบก่อน (ตรวจซ้ำ ห้ามลอกโดยไม่ยืนยัน)', f'- conf {e.get("conf")}: {e["why"]}',
                  f'- หลักฐานเดิม: {json.dumps(e.get("evidence"), ensure_ascii=False)}', '']
        if qs_ann:
            L.append('## วันประกาศงบ (ประมาณ)')
            for q in qs_ann:
                a = ann.get(q)
                L.append(f'- {q}: {a[0].isoformat()} ({a[1]})' if a else
                         f'- {q}: ช่วง {announce_window(q)[0]} – {announce_window(q)[1]} (deadline ก.ล.ต. ยังไม่รู้วันจริง)')
            L.append('')
        L.append('## ตัวเลขงบ (quarterly.json)')
        rows = [q for q in sorted(want_q) if q in qmap]
        for q in rows:
            py = qmap.get(f'{int(q[:4]) - 1}{q[4:]}')
            L.append(f'- **{q}**: {fmt_q(qmap[q], py)}')
        if not rows:
            L.append(f'- ไม่มีงบไตรมาส {", ".join(sorted(want_q))} ใน quarterly.json (เก่ากว่าข้อมูลที่ parse) — ใช้ OneReport/Earning Call/ข่าว')
        L += ['', '## ไฟล์ในเครื่องที่ต้องอ่านก่อน (`.extracted.md` เท่านั้น)']
        pats = month_patterns(s) + (month_patterns(t) if t.month != s.month else [])
        pick = []
        for d in docs:
            if d['q'] and d['q'] in want_q and d['type'] in ('mda', 'earningcall', 'notes'):
                pick.append(d)
            elif d['type'] == 'onereport' and d['pub'] and s.year <= d['pub'].year - 1 <= t.year:
                pick.append(d)  # One Report published in year Y+1 covers year Y
            elif d['type'] in ('news', 'broker') and d['pub'] and lo <= d['pub'] <= hi:
                pick.append(d)
        for d in sorted(pick, key=lambda d: (d['type'], d['path'])):
            how = (f'ใหญ่ {d["size"] // 1000} KB → อ่านผ่าน `{d["idx"]}` + offset/limit' if d['size'] > BIG and d['idx']
                   else f'ใหญ่ {d["size"] // 1000} KB ไม่มี idx → อ่านเป็นช่วง offset/limit' if d['size'] > BIG
                   else f'{d["size"] // 1000} KB')
            L.append(f'- [{d["type"]}] `{d["path"]}` — {how}')
            for n, txt in date_hits(d['path'], pats, 4 if daily else 8):
                L.append(f'    - L{n}: {txt}')
            if d['type'] in ('mda', 'earningcall'):
                for n, txt in date_hits(d['path'], KEYWORDS, 6 if daily else 12):
                    L.append(f'    - key L{n}: {txt}')
        if not pick:
            L.append('- ไม่มีไฟล์ในเครื่องที่ช่วงเวลาตรง → ใช้ WebSearch (ระบุใน sources_checked ว่าในเครื่องไม่มี)')
        if deepdive and deepdive.get('found'):
            L += deepdive_block(deepdive, s, t)
        facts = sorted((f['date'], f.get('what', ''), d['path'], f.get('loc', '')) for d in digest for f in d.get('events') or []
                       if str(f.get('date', ''))[:10] >= lo.isoformat() and str(f.get('date', ''))[:10] <= hi.isoformat())
        if facts:
            L += ['', '## ข้อเท็จจริงที่ digest agent สกัดจากไฟล์ในเครื่อง (ตรวจกับต้นฉบับก่อนอ้าง)']
            L += [f'- {dt} · {w} · `{p}` {loc}' for dt, w, p, loc in facts[:10 if daily else 25]]
        nw = news_items(raw, lo, hi)
        if nw:
            L += ['', '## หัวข้อข่าว SET ในช่วง (News/set_news_*.jsonl)']
            L += [f'- {d} · {ti} · {u}' for d, ti, u in nw[:12 if daily else 30]]
        if broker_md and os.path.exists(broker_md):
            L += ['', '## บทวิเคราะห์โบรก', f'- `{broker_md.replace(os.sep, "/")}` — grep วันที่ใกล้ {e["date"]}']
            L += [f'    - L{n}: {txt}' for n, txt in date_hits(broker_md, pats, 5)]
        packs[f'{e["date"]}_{e["kind"]}'] = cap_pack('\n'.join(L) + '\n', max_bytes)
    return packs, ann


def deepdive_block(dd, s, t):
    """pack section from a Deepdive: moves it already explained (KEYMETRICS ตาราง C), anomalous quarters (ตาราง B), dated facts."""
    import deepdive_context as ddc
    L = ['', f'## Deepdive {dd.get("date")} (อายุ {dd.get("age_days")} วัน{" · ⚠️ เก่า" if dd.get("stale") else ""}) — บริบท ไม่ใช่หลักฐาน ต้องตรวจซ้ำกับไฟล์ดิบ']
    mv = ddc.moves_in_window(dd, s, t)
    if mv:
        L.append('### สาเหตุที่ Deepdive เคยหาไว้สำหรับวันที่ราคาขยับในช่วงนี้ (KEYMETRICS ตาราง C)')
        for e in mv:
            cause = e['cause'] or 'ยังไม่มีการเติมสาเหตุ'
            L.append(f'- {e["date"]} {e["pct"]:+.1f}% · conf {e["conf"] or "-"} · {cause[:300]} · แหล่งที่อ้าง: {e["src"] or "-"}')
            if e.get('detail'):
                L.append(f'    - {e["detail"][:200]}')
    qs = ddc.quarters_in_window(dd, s, t)
    if qs:
        L.append('### ไตรมาสผิดปกติที่ Deepdive จับไว้ (KEYMETRICS ตาราง B)')
        L += [f'- {b["q"]}: NP {b["np"]} ({b["np_yoy"]}) · {b["anomaly"][:160]} · สาเหตุ: {(b["cause"] or "-")[:200]} · conf {b["conf"] or "-"}' for b in qs]
    fx = ddc.facts_in_window(dd, s, t)
    if fx:
        L.append('### ข้อเท็จจริงของงวดที่เกี่ยวข้อง (FACTS — ตำแหน่งต้นฉบับอยู่ในคอลัมน์สุดท้าย)')
        L += [f'- {f["item"]}: {f["value"]} {f["unit"]} ({f["period"]}) · {f["src"]} · ชั้น {f["tier"]}' for f in fx]
    if not (mv or qs or fx):
        L.append('- ไม่มีรายการของ Deepdive ที่ตรงช่วงเวลานี้ (ใช้ deepdive_brief.md เป็นบริบทธุรกิจเท่านั้น)')
    return L


def batches(events, size):
    """order events by quarter then chunk -> list of lists of pack ids (one agent each). Neighbouring events share the
    same MD&A / earning call / One Report, so an agent opens each document once instead of once per batch."""
    ordered = sorted(events, key=lambda e: (quarter_of(date.fromisoformat(e['date'])), e['date']))
    flat = [f'{e["date"]}_{e["kind"]}' for e in ordered]
    return [flat[i:i + size] for i in range(0, len(flat), size)]


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('ticker'); ap.add_argument('events'); ap.add_argument('quarterly'); ap.add_argument('out')
    ap.add_argument('--raw'); ap.add_argument('--broker'); ap.add_argument('--batch', type=int, default=6)
    ap.add_argument('--digest'); ap.add_argument('--deepdive')
    ap.add_argument('--depth', choices=sorted(DEPTH), default='normal')
    ap.add_argument('--max-bytes', type=int, default=DEFAULT_MAX_BYTES)
    a = ap.parse_args()
    raw = a.raw or os.path.join(os.environ.get('PRICE_MOVE_RAW', 'AllCompany'), a.ticker)
    broker = a.broker  # ไม่อ่านโฟลเดอร์โบรกโดยปริยาย
    ev = json.load(open(a.events, encoding='utf-8'))
    todo = [e for e in ev if e.get('conf') not in ('mid', 'high') or not e.get('driver')]
    dig = json.load(open(a.digest, encoding='utf-8')) if a.digest else []
    dd = json.load(open(a.deepdive, encoding='utf-8')) if a.deepdive else None
    packs, ann = build(a.ticker, todo, json.load(open(a.quarterly, encoding='utf-8')), raw, broker, dig, dd,
                       a.depth, a.max_bytes)
    os.makedirs(a.out, exist_ok=True)
    json.dump({'ticker': a.ticker, 'depth': a.depth, 'web_searches_per_event': DEPTH[a.depth], 'max_bytes': a.max_bytes},
              open(os.path.join(a.out, 'config.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for k, txt in packs.items():
        open(os.path.join(a.out, k + '.md'), 'w', encoding='utf-8').write(txt)
    b = batches(todo, a.batch)
    json.dump({'ticker': a.ticker, 'announce_dates': {q: v[0].isoformat() for q, v in sorted(ann.items())},
               'batches': b}, open(os.path.join(a.out, 'batches.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'packs={len(packs)} (skipped {len(ev) - len(todo)} already researched with driver) '
          f'batches={len(b)} announce_dates={len(ann)} -> {a.out}')
