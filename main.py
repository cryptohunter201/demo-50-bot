# main.py - NEUROBRO ORIGINAL - 6 COIN FINAL
import os, time, sqlite3, requests, traceback, pathlib
import ccxt

TESTNET = os.getenv("TESTNET", "true").lower() in ("1","true","yes")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
DB_PATH = os.getenv("DB_PATH", "/data/neurobro_s50.db")

# COIN FINAL SESUAI KAMU
SYMBOLS = [
    "LIT/USDT:USDT",
    "ONDO/USDT:USDT",
    "SUI/USDT:USDT",
    "ASTER/USDT:USDT",
    "SOL/USDT:USDT",
    "HYPER/USDT:USDT"
]

def ensure_dir():
    pathlib.Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

def tg(msg):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[TG] SKIP {msg[:80]}")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=15)
    except Exception as e:
        print(f"[TG] fail {e}")

def get_exchange():
    ex = ccxt.bybit({'enableRateLimit': True, 'options': {'defaultType': 'swap'}})
    ex.load_markets()
    print(f"[OK] BYBIT {len(ex.markets)} markets - {SYMBOLS}")
    return ex

def ema(data, period):
    if len(data) < period: return None
    k = 2/(period+1)
    ev = sum(data[:period])/period
    for p in data[period:]:
        ev = p*k + ev*(1-k)
    return ev

def atr(ohlcv, period=14):
    if len(ohlcv) < period+1: return None
    trs = []
    for i in range(1, len(ohlcv)):
        h,l,pc = ohlcv[i][2], ohlcv[i][3], ohlcv[i-1][4]
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    return sum(trs[-period:])/period if len(trs)>=period else None

def init_db():
    ensure_dir()
    con = sqlite3.connect(DB_PATH)
    con.cursor().execute("CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY, symbol TEXT, side TEXT, entry REAL, sl REAL, tp REAL, pnl REAL, created_at TEXT)")
    con.commit()
    con.close()

def main_loop():
    ensure_dir()
    init_db()
    tg(f"🤖 BOT NYALA Neurobro - 6 COIN: LIT ONDO SUI ASTER SOL HYPER")
    exchange = get_exchange()
    while True:
        try:
            for sym in SYMBOLS:
                try:
                    ohlcv = exchange.fetch_ohlcv(sym, '5m', limit=100)
                    closes = [c[4] for c in ohlcv]
                    e20, e50, atr_val = ema(closes,20), ema(closes,50), atr(ohlcv,14)
                    last = closes[-1]
                    if e20 and e50 and atr_val:
                        print(f"[SCAN] {sym} last={last:.4f} e20={e20:.4f} e50={e50:.4f} atr={atr_val:.4f}")
                except Exception as e:
                    print(f"[SCAN] {sym} err: {e}")
                time.sleep(1)
            print("[SLEEP] 60s")
            time.sleep(60)
        except Exception as e:
            print(f"[LOOP] err {e}")
            traceback.print_exc()
            time.sleep(10)

if __name__ == "__main__":
    main_loop()
