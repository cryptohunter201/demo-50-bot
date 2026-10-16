import os, time, math, signal, threading
from datetime import datetime
import requests
import websocket
import ccxt
import pandas as pd

# ============ KONFIGURASI DEMO $50 ============
SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "AVAX/USDT:USDT", "SUI/USDT:USDT", "BNB/USDT:USDT"]
API_KEY = os.getenv("BINANCE_API_KEY", "")
API_SECRET = os.getenv("BINANCE_API_SECRET", "")
TESTNET = os.getenv("TESTNET", "true").lower() == "true"
TELE_TOKEN = os.getenv("TELE_TOKEN", "")
TELE_CHAT = os.getenv("TELE_CHAT_ID", "")

DEMO_BALANCE = 250.0 # simulasi $250 sesuai log kamu
RISK_PER_TRADE = 0.0025
MAX_OPEN_RISK = 0.0075
DAILY_LOSS_LIMIT = 0.015
MAX_POSITIONS = 3
R_MULT = 1.20
EMA_FAST, EMA_SLOW = 20, 50
BREAKOUT_N = 20
VOL_THRESHOLD = 1.30

# FIX mapping: harus pakai format lengkap :USDT
ATR_MULT = {s: 1.2 if "BTC" in s or "ETH" in s else 1.4 if "BNB" in s or "AVAX" in s else 1.6 for s in SYMBOLS}
TRAIL_MULT = {s: 1.0 if "BTC" in s or "ETH" in s else 1.2 for s in SYMBOLS}

RUNNING_FLAG = True
positions = {}
last_ws_msg = time.time()

# ============ TELEGRAM ============
def send_tele(msg):
    if not TELE_TOKEN or not TELE_CHAT:
        print(f"[TELE SKIP] {msg}"); return
    try:
        r = requests.post(f"https://api.telegram.org/bot{TELE_TOKEN}/sendMessage",
                          json={"chat_id": TELE_CHAT, "text": msg, "parse_mode": "Markdown"}, timeout=10)
        print(f"[TELE] {r.status_code} {r.text[:200]}")
    except Exception as e:
        print(f"[TELE ERR] {e}")

def equity():
    # Kalau API key kosong, pakai simulasi $250
    if not API_KEY or not API_SECRET:
        return DEMO_BALANCE
    try:
        bal = exchange.fetch_balance()
        return bal.get("USDT", {}).get("total", DEMO_BALANCE) or DEMO_BALANCE
    except:
        return DEMO_BALANCE

# ============ EXCHANGE ============
exchange = ccxt.binance({
    "apiKey": API_KEY, "secret": API_SECRET,
    "enableRateLimit": True,
    "options": {"defaultType": "swap", "defaultSubType": "linear", "adjustForTimeDifference": True}
})
if TESTNET and API_KEY:
    exchange.set_sandbox_mode(True)

def shutdown(sig, frame):
    global RUNNING_FLAG
    RUNNING_FLAG = False
signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)

# ============ INDIKATOR (FIX) ============
def ema(s, n): return s.ewm(span=n, adjust=False).mean()

def atr(df, n=14):
    high, low, close = df["high"], df["low"], df["close"]
    tr = pd.concat([(high-low), (high-close.shift()).abs(), (low-close.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()

def regime(df_4h):
    close = df_4h["close"]
    e50, e200 = ema(close, 50).iloc[-1], ema(close, 200).iloc[-1]
    return "BULL" if close.iloc[-1] > e50 > e200 else "BEAR" if close.iloc[-1] < e50 < e200 else "NO_TRADE"

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

# ============ EKSEKUSI DEMO ============
def open_position(symbol, side, df15m):
    a = atr(df15m).iloc[-1]
    price = df15m["close"].iloc[-1]
    eq = equity()
    risk_amt = eq * RISK_PER_TRADE
    mult = ATR_MULT.get(symbol, 1.4)
    stop = price - mult*a if side=="buy" else price + mult*a
    dist = abs(price-stop)
    if dist == 0: return
    qty = risk_amt / dist
    target = price + R_MULT*dist if side=="buy" else price - R_MULT*dist

    # SIMULASI (tidak market order beneran kalau TESTNET tanpa key)
    positions[symbol] = {"side": side, "entry": price, "stop": stop, "tp": target, "qty": qty}
    send_tele(f"✅ *DEMO $50 ENTRY*\n{symbol} {side.upper()}\nEntry: {price}\nSL: {stop:.2f}\nTP: {target:.2f}\nBalance sim: ${eq}")
    print(f"[OPEN] {symbol} {side} {price}")

# ============ WS WATCHDOG ============
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

# ============ LOOP ============
def main():
    threading.Thread(target=ws_thread, daemon=True).start()
    print("=== BOT DEMO $50 START ===")
    send_tele(f"TEST_BOT_DEMO_50_AKTIF\n[{(datetime.now().strftime('%H:%M:%S'))}] DEMO $50 running - Balance simulasi ${DEMO_BALANCE}")

    while RUNNING_FLAG:
        if time.time() - last_ws_msg > 30:
            print("[!] WS stale"); time.sleep(5); continue
        for symbol in SYMBOLS:
            if len(positions) >= MAX_POSITIONS or symbol in positions: continue
            try:
                # FIX kolom: pakai 'vol' semua
                ohlcv_4h = exchange.fetch_ohlcv(symbol, "4h", limit=100)
                ohlcv_1h = exchange.fetch_ohlcv(symbol, "1h", limit=100)
                ohlcv_15 = exchange.fetch_ohlcv(symbol, "15m", limit=50)
                df4h = pd.DataFrame(ohlcv_4h, columns=["ts","open","high","low","close","vol"])
                df1h = pd.DataFrame(ohlcv_1h, columns=["ts","open","high","low","close","vol"])
                df15 = pd.DataFrame(ohlcv_15, columns=["ts","open","high","low","close","vol"])

                reg = regime(df4h)
                if reg == "BULL" and long_ok(df1h, df15):
                    open_position(symbol, "buy", df15)
                elif reg == "BEAR" and short_ok(df1h, df15):
                    open_position(symbol, "sell", df15)
            except Exception as e:
                print(f"[ERR] {symbol}: {e}")
            time.sleep(0.5)
        time.sleep(15)

if __name__ == "__main__":
    main()
