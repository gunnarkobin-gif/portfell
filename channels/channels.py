#!/usr/bin/env python3
"""Portfolio regression-channel pipeline.
  positions <PORTFELL.xlsx> <SHEET> <out.json>          -> open positions + FMP symbols
  build <positions.json> <prices_dir> <template.html> <out.html> <title> [--max-loss 20]
Prices: <prices_dir>/<FMP symbol>.csv with header date,close (daily, ~3y)."""
import sys, json, re, os, datetime as dt, warnings
warnings.filterwarnings('ignore')

SUFFIX = {'lon':'L','gb':'L','etr':'DE','de':'DE','xetr':'DE','par':'PA','fr':'PA','se':'ST','sto':'ST',
  'ams':'AS','nl':'AS','mil':'MI','it':'MI','no':'OL','osl':'OL','es':'MC','mce':'MC','dk':'CO','cph':'CO',
  'ch':'SW','swx':'SW','be':'BR','bru':'BR','hel':'HE','fi':'HE','pl':'WA','lis':'LS','pt':'LS','vie':'VI','at':'VI',
  'hk':'HK','hkg':'HK','aus':'AX','au':'AX','asx':'AX','kls':'KL','my':'KL','ca':'TO','tsx':'TO','sg':'SI','sgx':'SI',
  'jp':'T','tyo':'T','nz':'NZ','nzx':'NZ'}

def fmp_symbol(raw):
    s = str(raw).strip()
    m = re.match(r'^(.+?)-([A-Za-z]+)$', s)
    if not m: return s.upper().replace('.', '-')          # US: no suffix
    base, suf = m.group(1), m.group(2).lower()
    ex = SUFFIX.get(suf)
    if ex is None: return s.upper()
    base = base.upper().replace('.', '-')
    if ex in ('HK', 'KL') and base.isdigit(): base = base.zfill(4)
    return f'{base}.{ex}'

def positions(xlsx, sheet, out):
    import openpyxl
    from openpyxl.utils import column_index_from_string as ci
    ws = openpyxl.load_workbook(xlsx, data_only=True, read_only=True)[sheet]
    rows = list(ws.iter_rows(values_only=True))
    hdr = {str(v).strip(): i for i, v in enumerate(rows[1]) if v is not None}
    def col(name, letter):  # prefer header lookup, fall back to known letter
        return hdr.get(name, ci(letter) - 1)
    c = dict(sym=0, name=1, ccy=col('Valuuta','D'), date=col('Ost Date','F'), price=col('Hind','I'),
             cost=col('Ost EUR','O'), qty=col('Saldo','Y'), pl=col('€ Kasum','BE'), real=col('€ Rtud PL','BJ'))
    P = {}
    for r in rows[2:]:
        if not r or not r[0]: continue
        q = r[c['qty']] if c['qty'] < len(r) else None
        if not isinstance(q, (int, float)) or q <= 0: continue
        sym = fmp_symbol(r[0])
        p = P.setdefault(sym, dict(fmp=sym, label=str(r[0]).upper(), name=r[1], ccy=r[c['ccy']],
                                   qty=0, open_cost=0, open_pl=0, real=0, _bv=0, buy_date=None))
        g = lambda k: (r[c[k]] if c[k] < len(r) and isinstance(r[c[k]], (int, float)) else 0)
        p['qty'] += q; p['open_cost'] += g('cost'); p['open_pl'] += g('pl'); p['real'] += g('real')
        p['_bv'] += g('price') * q
        d = r[c['date']]
        if isinstance(d, dt.datetime):
            ds = d.strftime('%Y-%m-%d'); p['buy_date'] = min(p['buy_date'] or ds, ds)
    for p in P.values():
        p['buy'] = p.pop('_bv') / p['qty'] if p['qty'] else None
    json.dump(list(P.values()), open(out, 'w'), indent=1, default=str)
    print(f'{len(P)} open positions on {sheet}')
    for p in P.values(): print(f"  {p['label']:14} -> {p['fmp']:12} {p['name']}")

def fit(close, start):
    import numpy as np
    c = np.asarray(close); i = start + int(np.argmin(c[start:])); y = c[i:]; x = np.arange(len(y))
    if len(y) >= 3:
        b, a = np.polyfit(x, y, 1); sd = (y - (a + b * x)).std(ddof=2)
    else: a, b, sd = y[0], 0.0, 0.0
    fe = a + b * x[-1]
    return dict(i=i, low=float(c[i]), a=float(a), b=float(b), s=float(sd), n=len(y), fit=float(fe),
                z=float((y[-1] - fe) / sd) if sd > 0 else 0.0)

def build(pos_json, prices, tpl, out, title, max_loss=20.0):
    import pandas as pd
    pos = json.load(open(pos_json)); D = []; missing = []
    asof = None
    for p in pos:
        f = os.path.join(prices, p['fmp'] + '.csv')
        if not os.path.exists(f): missing.append(p['fmp']); continue
        d = pd.read_csv(f, parse_dates=['date']).sort_values('date').drop_duplicates('date')
        if len(d) < 2: missing.append(p['fmp']); continue
        dates = [t.strftime('%Y-%m-%d') for t in d.date]; close = [round(float(v), 4) for v in d.close]
        asof = max(asof or dates[-1], dates[-1])
        D.append(dict(p=p, dates=dates, close=close))
    A = dt.date.fromisoformat(asof)
    d1 = A.replace(year=A.year - 1).isoformat(); d2 = A.replace(year=A.year - 2).isoformat()
    data = []; report = []
    for e in D:
        p, dates, close = e['p'], e['dates'], e['close']
        f3 = fit(close, 0)
        i1 = next((i for i, t in enumerate(dates) if t >= d1), 0); f1 = fit(close, i1)
        i2 = next((i for i, t in enumerate(dates) if t >= d2), 0); f2 = fit(close, i2)
        last = close[-1]
        pct = p['open_pl'] / p['open_cost'] * 100 if p['open_cost'] else 0
        lower = f3['fit'] - 2 * f3['s']
        flag = None
        if -max_loss < pct < 0 and f3['n'] >= 40:
            if f3['z'] <= -2: flag = 'broken'
            elif f3['b'] < 0: flag = 'down'
            elif lower > 0 and last <= lower * 1.02: flag = 'watch'
        slope = lambda f: f['b'] * 250 / f['fit'] * 100 if f['fit'] else 0
        s = dict(sym=p['label'], name=p['name'], ccy=p['ccy'], dates=dates, close=close,
                 low_i=f3['i'], low=f3['low'], low_date=dates[f3['i']], a=f3['a'], b=f3['b'], s=f3['s'], n=f3['n'],
                 z=f3['z'], fit_end=f3['fit'], lower=lower, upper=f3['fit'] + 2 * f3['s'], last=last,
                 l1_i=f1['i'], l1=f1['low'], a1=f1['a'], b1=f1['b'], s1=f1['s'], n1=f1['n'], z1=f1['z'],
                 l2_i=f2['i'], l2=f2['low'], a2=f2['a'], b2=f2['b'], s2=f2['s'], n2=f2['n'], z2=f2['z'],
                 flag=flag, pl=dict(open_pl=p['open_pl'], open_cost=p['open_cost'], qty=p['qty'], real=p['real'],
                                    buy=p['buy'], buy_date=p['buy_date']) if p.get('qty') else None)
        for k, v in list(s.items()):
            if isinstance(v, float): s[k] = round(v, 6)
        data.append(s)
        show1 = f1['n'] >= 40 and f1['i'] != f3['i']; show2 = f2['n'] >= 40 and f2['i'] not in (f3['i'], f1['i'])
        report.append(dict(sym=p['label'], name=(p['name'] or '')[:30], pl=round(p['open_pl']), pct=round(pct, 1),
            flag=flag, z3=round(f3['z'], 2) if f3['n'] >= 40 else None, slope3=round(slope(f3)) if f3['n'] >= 40 else None,
            vs_lower=round((last / lower - 1) * 100, 1) if f3['n'] >= 40 and lower > 0 else None,
            z2=round(f2['z'], 2) if show2 else None, slope2=round(slope(f2)) if show2 else None,
            z1=round(f1['z'], 2) if show1 else None, slope1=round(slope(f1)) if show1 else None,
            days_since_3y_low=f3['n'] - 1, chg20=round((close[-1] / close[max(0, len(close) - 21)] - 1) * 100, 1)))
    fresh = [r['sym'] for r in report if r['days_since_3y_low'] < 39]
    asof_txt = A.strftime('%-d %b %Y')
    foot = (f"Data: FMP daily closes to {asof_txt}. Flags: among positions down less than {max_loss:g}%, red marks an exit signal "
            "(close below the lower 2σ band of the 3-year channel, or a downward-sloping 3-year regression) and orange marks a stock "
            "within 2% above its lower band. Euro P&amp;L is the unrealised gain or loss on each open position from the PORTFELL sheet "
            "(€ Kasum), including fees and currency moves; the purple line is the average buy price from the first buy date. "
            f"The blue channel starts at the lowest close since {d2}, the teal one at the lowest close since {d1}; each is drawn only "
            "when its low differs from the longer channel's low and is at least 40 trading days old. "
            + (f"{len(fresh)} stock{'s' if len(fresh) != 1 else ''} set a 3-year low within the last 40 trading days and show price only. " if fresh else "")
            + "Regression is linear in price; σ is the residual standard deviation over the fit window.")
    h = open(tpl).read()
    h = (h.replace('__TITLE__', title).replace('__ASOF_TXT__', asof_txt).replace('__D1__', d1).replace('__D2__', d2)
          .replace('__FOOT__', foot).replace('__DATA__', json.dumps(data, separators=(',', ':'))))
    open(out, 'w').write(h)
    json.dump(report, open(os.path.splitext(out)[0] + '-report.json', 'w'), indent=1)
    print(f'as of {asof}; {len(data)} charts; missing prices: {missing or "none"}')
    tot = sum(r['pl'] for r in report); cost = sum(e['p']['open_cost'] for e in D)
    print(f'open P&L €{tot:,} on €{cost:,.0f} ({tot / cost * 100:.1f}%)' if cost else '')
    print('FLAGGED:')
    for r in sorted(report, key=lambda r: ({'broken': 0, 'down': 1, 'watch': 2}.get(r['flag'], 9), r['z3'] or 0)):
        if r['flag']: print('  ', r)
    print('OTHER positions down <%g%%:' % max_loss)
    for r in report:
        if not r['flag'] and -max_loss < r['pct'] < 0: print('  ', r)

if __name__ == '__main__':
    a = sys.argv
    if a[1] == 'positions': positions(a[2], a[3], a[4])
    elif a[1] == 'build':
        ml = float(a[a.index('--max-loss') + 1]) if '--max-loss' in a else 20.0
        build(a[2], a[3], a[4], a[5], a[6], ml)
