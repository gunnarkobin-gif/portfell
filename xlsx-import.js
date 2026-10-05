/* PORTFELL Exceli lugemine telefonis — sama loogika mis portfell_extract.py.
   Aktsiad: lehed "EU AKTSIA", "US AKTSIA", "AASIA AKTSIA", alates 3. reast; rida võetakse, kui A on täidetud ja Y (Saldo) > 0.
   Võlakirjad: leht "BONDS", alates 5. reast; rida võetakse, kui A või B on täidetud ja veerg 57 (avatud nominaal) > 0. */
(function (root) {
  const HEADER = ["Book","Symbol","Name","Country_or_Parent","Currency","Saldo_or_Nominal","Last","Daily_pct","Coupon_pct","Yield_pct","Maturity"];
  const EQUITY = [["EU","EU AKTSIA"],["US","US AKTSIA"],["ASIA","AASIA AKTSIA"]];

  const num = v => { if (v === null || v === undefined || v === "" || typeof v === "boolean") return null;
    const x = typeof v === "number" ? v : parseFloat(String(v).trim()); return isFinite(x) ? x : null; };
  const truthy = v => !(v === null || v === undefined || v === "" || v === 0 || v === false);
  const rd = (x, n) => x === null ? "" : (n === 0 ? Math.trunc(x) : Math.round(x * 10 ** n) / 10 ** n);
  const pct = x => x === null ? null : x * 100;
  const str = v => v === null || v === undefined ? "" : (v instanceof Date ? v.toISOString().slice(0, 10) : String(v));
  const esc = v => { const s = str(v); return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };

  function xlDate(XLSX, v) {
    if (typeof v !== "number") return v;
    const d = XLSX.SSF.parse_date_code(v); if (!d) return v;
    const p = n => String(n).padStart(2, "0");
    return d.y + "-" + p(d.m) + "-" + p(d.d);
  }

  function sheetRows(XLSX, ws, firstRow) {
    if (!ws || !ws["!ref"]) return [];
    const rg = XLSX.utils.decode_range(ws["!ref"]);
    rg.s.r = 0; rg.s.c = 0; // nii et indeks 0 = veerg A ja rida 1
    const all = XLSX.utils.sheet_to_json(ws, { header: 1, raw: true, defval: null, blankrows: true, range: rg });
    return all.slice(firstRow - 1);
  }

  function extract(XLSX, data) {
    const wb = XLSX.read(data, { type: "array", cellDates: false, cellFormula: false, cellHTML: false, cellText: false,
      sheets: [...EQUITY.map(e => e[1]), "BONDS"] });
    const missing = [...EQUITY.map(e => e[1]), "BONDS"].filter(n => !wb.Sheets[n]);
    if (missing.length === 4) throw new Error("Selles failis pole PORTFELL lehti (EU AKTSIA, US AKTSIA, AASIA AKTSIA, BONDS).");
    const rows = [];
    for (const [book, sheet] of EQUITY) {
      for (const r0 of sheetRows(XLSX, wb.Sheets[sheet], 3)) {
        const r = r0 || [];
        const saldo = num(r[24]);
        if (truthy(r[0]) && (saldo || 0) > 0)
          rows.push([book, r[0], r[1], r[2], r[3], rd(saldo, 0), rd(num(r[27]), 4), rd(pct(num(r[29])), 2), "", "", ""]);
      }
    }
    for (const r0 of sheetRows(XLSX, wb.Sheets["BONDS"], 5)) {
      const r = r0 || [];
      const nom = num(r[56]);
      if ((truthy(r[0]) || truthy(r[1])) && nom && nom > 0)
        rows.push(["BONDS", r[0], r[1], r[2], r[13], nom, rd(num(r[20]), 3), rd(pct(num(r[22])), 2),
          rd(pct(num(r[14])), 3), rd(pct(num(r[35])), 2), xlDate(XLSX, r[41])]);
    }
    const counts = {};
    rows.forEach(x => counts[x[0]] = (counts[x[0]] || 0) + 1);
    const csv = [HEADER, ...rows].map(r => r.map(esc).join(",")).join("\r\n") + "\r\n";
    return { csv, counts, missing };
  }

  root.PortfellXlsx = { extract };
  if (typeof module !== "undefined") module.exports = root.PortfellXlsx;
})(typeof window !== "undefined" ? window : globalThis);
