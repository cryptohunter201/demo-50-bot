# main.py - ULTRA FIX - Anti Crash for Railway
import os, math, time, sqlite3, requests, traceback, pathlib
from datetime import datetime, timezone
import ccxt

# ENV
TESTNET = os.getenv("TESTNET", os.getenv("USE_TESTNET", "true")).lower() in ("1","true","yes")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
DB_PATH = os.getenv("DB_PATH", "/data/neurobro_s50.db")

USDT = 100.0
RISK_PER_TRADE = 0.012
DAILY_LOSS_LIMIT = 0.015
MAX_CORR_RISK = 0.045
CONSEC_LOSS_CAP = 3
ATR_PERIOD = 14
ATR_MULT_DEFAULT = 1.28
TRAIL_ACTIVATE = 2.1
TRAIL_MULT_DEFAULT = 1.15
RR = 2.2

SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "AVAX/USDT:USDT", "SUI/USDT:USDT", "BNB/USDT:USDT", "XRP/USDT:USDT", "ADA/USDT:USDT", "DOGE/USDT:USDT"]

def ensure_dir():
    try:
        p = pathlib.Path(DB_PATH).parent
        p.mkdir(parents=True, exist_ok=True)
        print(f"[DIR] ensured {p}")
    except Exception as e:
        print(f"[DIR] fail {e}")

def tg(msg):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[TG] SKIP no token/chat_id: {msg[:80]}")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=15)
        print(f"[TG] sent {r.status_code}: {msg[:60]}")
        r.raise_for_status()
    except Exception as e:
        print(f"[TG] failed: {e}")

def get_exchange():
    try:
        opts = {'enableRateLimit': True, 'options': {'defaultType': 'future'}}
        if BINANCE_API_KEY:
            opts['apiKey'] = BINANCE_API_KEY
            opts['secret'] = BINANCE_API_SECRET
        ex = ccxt.binance(opts)
        try:
            ex.load_markets()
            print(f"[OK] {len(ex.markets)} markets loaded | testnet={TESTNET}")
        except Exception as e:
            print(f"[WARN] load_markets failed (will continue): {e}")
        return ex
    except Exception as e:
        print(f"[EXCHANGE] fatal create failed: {e}")
        traceback.print_exc()
        return None

def ema(data, period):
    if len(data) < period: return None
    k = 2/(period+1)
    ema_val = sum(data[:period])/period
    for price in data[period:]:
        ema_val = price*k + ema_val*(1-k)
    return ema_val

def main_loop():
    ensure_dir()
    tg("🤖 BOT NYALA! Versi ULTRA FIX jalan (anti-crash)")
    exchange = get_exchange()
    if not exchange:
        tg("⚠️ Exchange gagal dibuat, tapi bot tetap hidup. Cek log Railway.")
    print("[LOOP] starting scan loop")
    while True:
        try:
            for sym in SYMBOLS:
                try:
                    ohlcv = None
                    if exchange:
                        try:
                            ohlcv = exchange.fetch_ohlcv(sym, '5m', limit=100)
                        except Exception as e:
                            print(f"[SCAN] {sym} fetch failed: {e} - retry public")
                            pub = ccxt.binance({'enableRateLimit': True})
                            ohlcv = pub.fetch_ohlcv(sym, '5m', limit=100)
                    else:
                        pub = ccxt.binance({'enableRateLimit': True})
                        ohlcv = pub.fetch_ohlcv(sym, '5m', limit=100)
                    closes = [c[4] for c in ohlcv]
                    e20 = ema(closes, 20)
                    e50 = ema(closes, 50)
                    print(f"[SCAN] {sym}: ema20={e20:.2f} ema50={e50:.2f} last={closes[-1]}" if e20 and e50 else f"[SCAN] {sym} not enough data")
                except Exception as e:
                    print(f"[SCAN] {sym} error: {e}")
                time.sleep(1)
            print("[SLEEP] 60s")
            time.sleep(60)
        except Exception as e:
            print(f"[LOOP] crash prevented: {e}")
            traceback.print_exc()
            tg(f"⚠️ Loop error: {e} - bot restart in 10s")
            time.sleep(10)

if __name__ == "__main__":
    main_loop()
