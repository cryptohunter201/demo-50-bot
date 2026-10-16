# main.py - FINAL NO CCXT
import os, time, sqlite3, requests, traceback, pathlib

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", os.getenv("TELE_TOKEN", ""))
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", os.getenv("TELE_CHAT_ID", ""))
DB_PATH = os.getenv("DB_PATH", "/data/neurobro_s50.db")

SYMBOLS = {
    "LIT/USDT:USDT": "LITUSDT",
    "ONDO/USDT:USDT": "ONDOUSDT",
    "SUI/USDT:USDT": "SUIUSDT",
    "ASTER/USDT:USDT": "ASTERUSDT",
    "SOL/USDT:USDT": "SOLUSDT",
    "HYPE/USDT:USDT": "HYPEUSDT",
}

def ensure_dir():
    pathlib.Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

def tg(msg):
    try:
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            print(f"[TG] SKIP")
            return
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=15)
        print(f"[TG] {r.status_code}")
    except Exception as e:
        print(f"[TG] err {e}")

def fetch_klines(bybit_symbol):
    url = f"https://api.bybit.com/v5/market/kline"
    params = {"category": "linear", "symbol": bybit_symbol, "interval": "5", "limit": 100}
    r = requests.get(url, params=params, timeout=15)
    data = r.json()
    if data.get("retCode")!=0:
        raise Exception(f"{data}")
    klines = list(reversed(data["result"]["list"]))
    return [[int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])] for k in klines]

def ema(data,p):
    if len(data)<p: return None
    k=2/(p+1)
    ev=sum(data[:p])/p
    for x in data[p:]:
        ev=x*k+ev*(1-k)
    return ev

def main_loop():
    ensure_dir()
    con=sqlite3.connect(DB_PATH)
    con.execute("CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY)")
    con.commit()
    con.close()
    tg("🤖 BOT NYALA - FINAL ANTI CRASH")
    print("[OK] Start - no ccxt")

    while True:
        for ccxt_sym, bybit_sym in SYMBOLS.items():
            try:
                ohlcv = fetch_klines(bybit_sym)
                closes = [c[4] for c in ohlcv]
                e20 = ema(closes,20)
                e50 = ema(closes,50)
                print(f"[SCAN] {bybit_sym} {closes[-1]:.4f} e20={e20:.4f} e50={e50:.4f}")
            except Exception as e:
                print(f"[SCAN] {bybit_sym} err {e}")
            time.sleep(0.5)
        print("[SLEEP] 60s")
        time.sleep(60)

if __name__=="__main__":
    main_loop()
