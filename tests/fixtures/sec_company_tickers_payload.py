"""SEC company_tickers_exchange.json mock payload — universe registration test 用."""
from __future__ import annotations


def sec_universe_payload() -> dict:
    """16 ticker (DEFUNCT 除く 15) + 異常 4 entry を含む payload.

    SEC actual response shape:
        {"fields": ["cik", "name", "ticker", "exchange"], "data": [[...], ...]}
    """
    rows = [
        # ── universe seeds (DEFUNCT 除く 15) ──
        [320193,    "Apple Inc",                              "AAPL",  "Nasdaq"],
        [789019,    "Microsoft Corp",                         "MSFT",  "Nasdaq"],
        [1067983,   "BERKSHIRE HATHAWAY INC",                 "BRK-A", "NYSE"],
        [1067983,   "BERKSHIRE HATHAWAY INC",                 "BRK-B", "NYSE"],   # 同 CIK
        [1652044,   "Alphabet Inc",                           "GOOGL", "Nasdaq"],
        [1652044,   "Alphabet Inc",                           "GOOG",  "Nasdaq"], # 同 CIK
        [1318605,   "Tesla Inc",                              "TSLA",  "Nasdaq"],
        [1046179,   "Taiwan Semiconductor Manufacturing Co",  "TSM",   "NYSE"],
        [1000184,   "SAP SE",                                 "SAP",   "NYSE"],
        [313838,    "Sony Group Corp",                        "SONY",  "NYSE"],
        [19617,     "JPMorgan Chase & Co",                    "JPM",   "NYSE"],
        [726728,    "Realty Income Corp",                     "O",     "NYSE"],
        [1495231,   "IZEA Worldwide Inc",                     "IZEA",  "Nasdaq"],
        [1321655,   "Palantir Technologies Inc",              "PLTR",  "NYSE"],
        [1435064,   "Cemtrex Inc",                            "CETX",  "Nasdaq"],
        # ── 異常 4 entry ──
        [9999000,   "Empty Ticker Co",                        "",      "Nasdaq"], # ticker 空 → skip + warn
        [9999001,   "",                                       "EMTNAM","NYSE"],   # name 空 → skip + warn
        [9999002,   "Unknown Exchange Co",                    "UNKEX", ""],       # exchange 空 → market=UNKNOWN
        [9999003,   "Empty Both",                             "",      ""],       # 両方空 → skip + warn
    ]
    return {
        "fields": ["cik", "name", "ticker", "exchange"],
        "data": rows,
    }


def sec_universe_payload_minimal() -> dict:
    """最小 payload (test の 1 ticker upsert 確認用)."""
    return {
        "fields": ["cik", "name", "ticker", "exchange"],
        "data": [[320193, "Apple Inc", "AAPL", "Nasdaq"]],
    }
