import os, time, signal, threading, math
from datetime import datetime
import requests, websocket, ccxt, pandas as pd

# ============ CONFIG DEMO $50 - FILE BARU FIX 451 + TELE ============
SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "AVAX/USDT:USDT", "SUI/USDT:USDT", "BNB/USDT:USDT"]
API_KEY = os.getenv("BINANCE_API_KEY", "")
API_SECRET = os.getenv("BINANCE_API_SECRET", "")
TESTNET = os.getenv("TESTNET", "true").lower() == "true"
TELE_TOKEN = os.getenv("TELE_TOKEN", "")
TELE_CHAT = os.getenv("TELE_CHAT_ID", "")

DEMO_BALANCE = 250.0
RISK_PER_TRADE = 0.0025
MAX_POSITIONS = 3
R_MULT = 1.20
BREAKOUT_N = 20
VOL_THRESHOLD = 1.30
ATR_MULT_MAP = {s: 1.2 if "BTC" in s or "ETH" in s else 1.6 if "SUI" in s else 1.4 for s in SYMBOLS}

RUNNING_FLAG = True
positions = {}
last_ws_msg = time.time()

def send_tele(msg):
    if not TELE_TOKEN or not TELE_CHAT:
        print(f"[TELE SKIP] TOKEN/CHAT kosong: {msg}"); return
    try:
        url = f"https://api.telegram.org/bot{TELE_TOKEN}/sendMessage"
        r = requests.post(url, json={"chat_id": TELE_CHAT, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        print(f"[TELE] {r.status_code} {r.text[:200]}")
    except Exception as e:
        print(f"[TELE ERR] {e}")

# ============ EXCHANGE FIX 451 RESTRICTED ============
exchange = ccxt.binance({
    "apiKey": API_KEY, "secret": API_SECRET,
    "enableRateLimit": True,
    "urls": {
        "api": {
            "public": "https://data-api.binance.vision",
            "private": "https://data-api.binance.vision",
        },
        "fapiPublic": "https://fapi.binance.com",
        "fapiPrivate": "https://fapi.binance.com",
    },
    "options": {"defaultType": "swap", "defaultSubType": "linear", "adjustForTimeDifference": True}
})
if TESTNET and API_KEY:
    try: exchange.set_sandbox_mode(True)
    except: pass

signal.signal(signal.SIGINT, lambda s,f: globals().update(RUNNING_FLAG=False))
signal.signal(signal.SIGTERM, lambda s,f: globals().update(RUNNING_FLAG=False))

def ema(s, n): return s.ewm(span=n, adjust=False).mean()
def atr(df, n=14):
    tr = pd.concat([(df["high"]-df["low"]), (df["high"]-df["close"].shift()).abs(), (df["low"]-df["close"].shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()

def long_ok(df1h, df15m):
    e20, e50 = ema(df1h["close"], 20).iloc[-1], ema(df1h["close"], 50).iloc[-1]
    hh = df15m["high"].iloc[-BREAKOUT_N-1:-1].max()
    vol_ok = df15m["vol"].iloc[-1] >= VOL_THRESHOLD * df15m["vol"].iloc[-BREAKOUT_N:].median()
    return e20 > e50 and df15m["close"].iloc[-1] > hh and vol_ok

def short_ok(df1h, df15m):
    e20, e50 = ema(df1h["close"], 20).iloc[-1], ema(df1h["close"], 50).iloc[-1]
    ll = df15m["low"].iloc[-BREAKOUT_N-1:-1].min()
    vol_ok = df15m["vol"].iloc[-1] >= VOL_THRESHOLD * df15m["vol"].iloc[-BREAKOUT_N:].median()
    return e20 < e50 and df15m["close"].iloc[-1] < ll and vol_ok

def open_position(symbol, side, df15m):
    a = atr(df15m).iloc[-1]
    price = df15m["close"].iloc[-1]
    mult = ATR_MULT_MAP.get(symbol, 1.4)
    stop = price - mult*a if side=="buy" else price + mult*a
    target = price + R_MULT*abs(price-stop) if side=="buy" else price - R_MULT*abs(price-stop)
    positions[symbol] = {"side": side, "entry": price, "stop": stop, "tp": target}
    send_tele(f"✅ *DEMO $50 ENTRY*\n`{symbol}` {side.upper()}\nEntry: {price}\nSL: {stop:.2f} | TP: {target:.2f}\nBalance: ${DEMO_BALANCE}")
    print(f"[OPEN] {symbol} {side} {price}")

def ws_thread():
    global last_ws_msg
    while RUNNING_FLAG:
        try:
            ws = websocket.WebSocket()
            streams = "/".join([s.split("/")[0].lower()+"usdt@bookTicker" for s in SYMBOLS])
            ws.connect(f"wss://fstream.binance.com/stream?streams={streams}")
            while RUNNING_FLAG:
                if ws.recv(): last_ws_msg = time.time()
        except Exception as e:
            print(f"[WS] {e}"); time.sleep(2)

def main():
    threading.Thread(target=ws_thread, daemon=True).start()
    print("=== BOT DEMO $50 START (FIXED FILE) ===")
    send_tele(f"TEST_BOT_DEMO_50_AKTIF - FILE BARU\n[{datetime.now().strftime('%H:%M:%S')}] DEMO $50 running - Balance simulasi ${DEMO_BALANCE}\nFix 451 OK, TELE OK")

    while RUNNING_FLAG:
        for symbol in SYMBOLS:
            if len(positions) >= MAX_POSITIONS or symbol in positions: continue
            try:
                ohlcv_4h = exchange.fetch_ohlcv(symbol, "4h", limit=100)
                ohlcv_1h = exchange.fetch_ohlcv(symbol, "1h", limit=100)
                ohlcv_15 = exchange.fetch_ohlcv(symbol, "15m", limit=50)
                df4h = pd.DataFrame(ohlcv_4h, columns=["ts","open","high","low","close","vol"])
                df1h = pd.DataFrame(ohlcv_1h, columns=["ts","open","high","low","close","vol"])
                df15 = pd.DataFrame(ohlcv_15, columns=["ts","open","high","low","close","vol"])
                e50, e200 = ema(df4h["close"], 50).iloc[-1], ema(df4h["close"], 200).iloc[-1]
                reg = "BULL" if df4h["close"].iloc[-1] > e50 > e200 else "BEAR" if df4h["close"].iloc[-1] < e50 < e200 else "NO"
                if reg == "BULL" and long_ok(df1h, df15): open_position(symbol, "buy", df15)
                elif reg == "BEAR" and short_ok(df1h, df15): open_position(symbol, "sell", df15)
            except Exception as e:
                print(f"[ERR] {symbol}: {e}")
            time.sleep(0.5)
        time.sleep(15)

if __name__ == "__main__":
    main()
