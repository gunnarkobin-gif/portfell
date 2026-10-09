#!/usr/bin/env python3
"""Support-breach filter for the portfolio-channels pipeline.

  csvpos <PORTFELL_positions.csv> <out.json>
      Fallback positions from the Drive CSV (no cost/P&L columns): equity books only.
  merge <out.json> <book>=<pos.json> [<book>=<pos.json> ...]
      Merge per-sheet pos.json files (from channels.py positions) and tag each with its book.
  live <prices_dir> <quotes.json> <out_dir>
      Copy prices; append today's live quote as a bar when its exchange date is newer
      than the last daily close (Asia trading now).  quotes.json = [{symbol, price, timestamp}]
  breaches <pos.json> <prices_dir> <out_pos.json> <out_report.json>
      Keep only positions whose latest close is the FIRST close more than 2% below a
      tested support level (>=2 swing lows within 3%), i.e. the break happened on the
      last bar. Same support definition as the channel page (10-day swing lows).
"""
import sys, json, os, csv, datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def clusters(c, k=10):
    n = len(c); P = []
    for i in range(k, n - 3):
        b = min(n - 1, i + k)
        if all(c[j] >= c[i] for j in range(i - k, b + 1)):
            P.append(i)
    P.sort(key=lambda i: c[i]); C = []
    for i in P:
        if C and c[i] <= C[-1]['lv'] * 1.03:
            g = C[-1]; g['ix'].append(i); g['lv'] = sum(c[j] for j in g['ix']) / len(g['ix'])
        else:
            C.append({'ix': [i], 'lv': c[i]})
    return [g for g in C if len(g['ix']) >= 2]


def new_breaks(c):
    """Levels whose first >2% close-below since the last touch is the last bar."""
    n = len(c); out = []
    for g in clusters(c):
        lt = max(g['ix'])
        bi = next((j for j in range(lt + 1, n) if c[j] < g['lv'] * 0.98), -1)
        if bi == n - 1:
            out.append(dict(level=round(g['lv'], 4), touches=len(g['ix']), last_touch=lt,
                            below_pct=round((1 - c[-1] / g['lv']) * 100, 2)))
    return sorted(out, key=lambda d: -d['touches'])


def read_prices(f):
    rows = []
    with open(f) as fh:
        for r in csv.DictReader(fh):
            try: rows.append((r['date'][:10], float(r['close'])))
            except (KeyError, ValueError): pass
    d = {}
    for a, b in rows: d[a] = b
    return sorted(d.items())


def cmd_csvpos(src, out):
    from channels import fmp_symbol
    P = {}
    with open(src, encoding='utf-8-sig') as fh:
        for r in csv.DictReader(fh):
            book = (r.get('Book') or '').strip().upper()
            if book not in ('EU', 'US', 'ASIA'): continue
            try: q = float(r.get('Saldo_or_Nominal') or 0)
            except ValueError: continue
            if q <= 0 or not r.get('Symbol'): continue
            sym = fmp_symbol(r['Symbol'])
            p = P.setdefault(sym, dict(fmp=sym, label=r['Symbol'].strip().upper(), name=r.get('Name'),
                                       ccy=r.get('Currency'), qty=0, open_cost=0, open_pl=0, real=0,
                                       buy=None, buy_date=None, book=book))
            p['qty'] += q
    for p in P.values(): p['qty'] = 0   # no cost data: cards show price only
    json.dump(list(P.values()), open(out, 'w'), indent=1)
    print(f'{len(P)} equity positions from CSV (no P&L columns)')


def cmd_merge(out, pairs):
    allp = {}
    for pr in pairs:
        book, f = pr.split('=', 1)
        for p in json.load(open(f)):
            p['book'] = book
            if p['fmp'] in allp:
                a = allp[p['fmp']]
                for k in ('qty', 'open_cost', 'open_pl', 'real'): a[k] += p[k]
            else:
                allp[p['fmp']] = p
    json.dump(list(allp.values()), open(out, 'w'), indent=1, default=str)
    print(f'{len(allp)} positions merged')


def cmd_live(prices, quotes, outdir):
    os.makedirs(outdir, exist_ok=True)
    Q = {}
    try:
        for q in json.load(open(quotes)):
            if q.get('price') and q.get('timestamp'): Q[q['symbol']] = q
    except Exception as e:
        print('no quotes:', e)
    added = []
    for f in os.listdir(prices):
        if not f.endswith('.csv'): continue
        sym = f[:-4]; rows = read_prices(os.path.join(prices, f))
        q = Q.get(sym)
        if q and rows:
            qd = dt.datetime.utcfromtimestamp(int(q['timestamp'])).date().isoformat()
            if qd > rows[-1][0] and sym.endswith(('.HK', '.AX', '.KL', '.T', '.SI', '.NZ')):
                rows.append((qd, float(q['price']))); added.append(sym)
        with open(os.path.join(outdir, f), 'w') as fh:
            fh.write('date,close\n')
            for a, b in rows: fh.write(f'{a},{b}\n')
    print(f'live bar appended for {len(added)}: {added}')


def cmd_breaches(pos_json, prices, out_pos, out_rep):
    pos = json.load(open(pos_json)); keep = []; rep = []; missing = []
    for p in pos:
        f = os.path.join(prices, p['fmp'] + '.csv')
        if not os.path.exists(f): missing.append(p['fmp']); continue
        rows = read_prices(f)
        if len(rows) < 30: continue
        c = [b for _, b in rows]
        br = new_breaks(c)
        if br:
            keep.append(p)
            prev = c[-2]
            rep.append(dict(sym=p['label'], fmp=p['fmp'], name=p.get('name'), book=p.get('book'),
                            date=rows[-1][0], close=c[-1], day_pct=round((c[-1] / prev - 1) * 100, 2),
                            open_pl=round(p.get('open_pl') or 0), breaks=br))
    json.dump(keep, open(out_pos, 'w'), indent=1, default=str)
    json.dump(rep, open(out_rep, 'w'), indent=1, default=str)
    print(f'{len(rep)} new support breaks out of {len(pos)} positions; missing prices: {missing or "none"}')
    for r in rep: print('  ', r)


if __name__ == '__main__':
    a = sys.argv
    if a[1] == 'csvpos': cmd_csvpos(a[2], a[3])
    elif a[1] == 'merge': cmd_merge(a[2], a[3:])
    elif a[1] == 'live': cmd_live(a[2], a[3], a[4])
    elif a[1] == 'breaches': cmd_breaches(a[2], a[3], a[4], a[5])
