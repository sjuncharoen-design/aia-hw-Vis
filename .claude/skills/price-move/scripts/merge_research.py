"""Merge research sub-agent results into the events list.
usage: python merge_research.py EVENTS_RAW_JSON PACK_DIR OUT_EVENTS_JSON
  PACK_DIR/result_*.json : each a list of {id, driver, cat, metric_move, why, evidence[], sources_checked[], conf}
                           id = "<date>_<kind>" (the evidence-pack file name)
Events already researched (carried over with conf mid/high + driver) are left untouched.
Every evidence/context item without `tier` gets one from tier_of(src) (A company/SET/SEC · B major media/broker · C other);
an agent-set tier is kept. check_page: conf high needs >=1 tier A or >=2 independent tier B.
Prints events still missing a result — the main model must research those itself before building.
"""
import glob, json, os, re, sys

FIELDS = ('driver', 'cat', 'metric_move', 'why', 'evidence', 'sources_checked', 'conf', 'context', 'from_deepdive',
          'what', 'direction_match', 'pnl_quarter', 'pnl_note', 'pnl_links', 'market_view', 'market_view_public', 'vs_consensus', 'market_view_src', 'outlook', 'hypothesis', 'next_check', 'conflicts')
CAT_OF = {'earnings_beat': 'earnings', 'earnings_miss': 'earnings', 'margin': 'earnings', 'revenue_volume': 'earnings',
          'guidance': 'earnings', 'dividend_xd': 'news', 'capital_action': 'news', 'insider_biglot': 'news',
          'broker': 'broker', 'commodity': 'commodity', 'policy': 'policy', 'sector': 'market', 'market': 'market', 'unknown': 'unknown'}


TIER_A_LOCAL = re.compile(r'_(MDA|FS|NOTES|AuditReport|Earningcall)_|/OneReport/|ONEREPORT|/Financial statement/|set_news_', re.I)
TIER_A_WEB = ('set.or.th', 'sec.or.th', 'settrade.com/th/equities', 'bot.or.th')
TIER_B_WEB = ('infoquest.co.th', 'ryt9.com', 'kaohoon.com', 'hoonsmart.com', 'thunhoon.com', 'prachachat.net',
              'bangkokpost.com', 'thestandard.co', 'bangkokbiznews.com', 'efinancethai.com', 'moneyandbanking.co.th',
              'reuters.com', 'bloomberg.com', 'nikkei.com', 'settrade.com', 'longtunman.com')


def is_deepdive(src):
    return '/Deepdive/' in str(src or '').replace('\\', '/')


def tier_of(src):
    s = str(src or '')
    if is_deepdive(s):
        return 'B'  # our own earlier synthesis, not a company document — cite its raw source for tier A
    if s.startswith('http'):
        h = re.sub(r'^https?://(www\.)?', '', s)
        return 'A' if any(d in h for d in TIER_A_WEB) else 'B' if any(h.startswith(d) or ('.' + d) in h for d in TIER_B_WEB) else 'C'
    if 'AllCompany' in s:
        return 'A' if TIER_A_LOCAL.search(s) else 'B'  # broker/news text saved locally
    return 'C'


def add_tiers(events):
    for e in events:
        for k in ('evidence', 'context'):
            for x in e.get(k) or []:
                if isinstance(x, dict) and not x.get('tier'):
                    x['tier'] = tier_of(x.get('src'))
        if any(isinstance(x, dict) and is_deepdive(x.get('src')) for k in ('evidence', 'context') for x in e.get(k) or []):
            e['from_deepdive'] = True
    return events


def merge(events, results):
    got = {r['id']: r for r in results}
    missing = []
    for e in events:
        k = f"{e['date']}_{e['kind']}"
        if k in got:
            r = got[k]
            e.update({f: r[f] for f in FIELDS if r.get(f) not in (None, '')})
            e['cat'] = r.get('cat') or CAT_OF.get(e.get('driver'), 'unknown')
        elif not (e.get('conf') in ('mid', 'high') and e.get('driver')):
            missing.append(k)
    return add_tiers(events), missing


if __name__ == '__main__':
    src, pack, out = sys.argv[1:4]
    results = [r for f in sorted(glob.glob(os.path.join(pack, 'result_*.json')))
               for r in json.load(open(f, encoding='utf-8'))]
    events, missing = merge(json.load(open(src, encoding='utf-8')), results)
    json.dump(events, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'merged={len(results)} events={len(events)} missing={missing} -> {out}')
    sys.exit(1 if missing else 0)
