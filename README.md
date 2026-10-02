# Portfell

Mobiilne veebiäpp aktsiaportfelli päevaliikumiste vaatamiseks.

- Positsioonid: `positions.csv`, mille GitHub Action tõmbab igal õhtul Google Drive'ist (PORTFELL_positions.csv).
- Hinnad: FMP (financialmodelingprep.com), päritakse otse telefonist iga minut.
- FMP API võti salvestatakse ainult seadme brauserisse (localStorage), mitte reposse.
