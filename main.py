# neurobro_perp_bot.py - FIXED
import os, math, time, sqlite3, requests, threading
from datetime import datetime, timezone
import ccxt

# ---------- ENV / CONFIG - Support 2 nama ----------
TESTNET = os.getenv("TESTNET", os.getenv("USE_TESTNET", "true")).lower() == "true"
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", os.getenv("TELE_TOKEN", ""))
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", os.getenv("TELE_CHAT_ID", ""))
DB_PATH = os.getenv("DB_PATH", "/data/neurobro_state.db")

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

SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT",
           "AVAX/USDT:USDT", "SUI/USDT:USDT", "BNB/USDT:USDT",
           "LIT/USDT:USDT", "ASTER/USDT:USDT", "ONDO/USDT:USDT"]

ATR_MAP = {s: ATR_MULT_DEFAULT for s in SYMBOLS}
ATR_MAP.update({"LIT/USDT:USDT": 1.60, "ASTER/USDT:USDT": 1.60, "ONDO/USDT:USDT": 1.60})
TRAIL_MAP = {s: TRAIL_MULT_DEFAULT for s in SYMBOLS}
TRAIL_MAP.update({"LIT/USDT:USDT": 1.3, "ASTER/USDT:USDT": 1.3, "ONDO/USDT:USDT": 1.3})
LEVERAGE = {"BTC/USDT:USDT": 5, "ETH/USDT:USDT": 4, "SOL/USDT:USDT": 3,
            "BNB/USDT:USDT": 3, "AVAX/USDT:USDT": 2, "SUI/USDT:USDT": 2,
            "LIT/USDT:USDT": 2, "ASTER/USDT:USDT": 2, "ONDO/USDT:USDT": 2}

positions = {} # global biar kebaca thread

# ---------- TELEGRAM ----------
def tg_send(text):
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        print("[TG] SKIP - token/chat kosong"); return
    try:
        r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                      json={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=10)
        print(f"[TG] sent {r.status_code}: {text[:50]}")
    except Exception as e:
        print(f"[TG ERROR] {e}")

def alert(title, msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    tg_send(f"⚠️ [{title}] {msg} · {ts}")

#... [db_init, db_save, db_forget, db_load sama kayak punya kamu]...
def db_init():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS positions (
        symbol TEXT PRIMARY KEY, side TEXT, entry REAL, qty REAL,
        stop REAL, tp REAL, trail REAL, opened_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS stats (key TEXT PRIMARY KEY, value TEXT)""")
    conn.commit(); return conn
def db_save(conn, symbol, p):
    conn.execute("INSERT OR REPLACE INTO positions VALUES (?,?,?,?,?,?,?,?)",
                 (symbol, p["side"], p["entry"], p["qty"], p["stop"], p["tp"],
                  p["trail"], datetime.now(timezone.utc).isoformat())); conn.commit()
def db_forget(conn, symbol):
    conn.execute("DELETE FROM positions WHERE symbol=?", (symbol,)); conn.commit()
def db_load(conn):
    return {r[0]: {"side": r[1], "entry": r[2], "qty": r[3], "stop": r[4],
                   "tp": r[5], "trail": r[6]} for r in
            conn.execute("SELECT * FROM positions")}

# ---------- EXCHANGE ----------
exchange = ccxt.binance({
    "apiKey": BINANCE_API_KEY, "secret": BINANCE_API_SECRET,
    "options": {"defaultType": "swap"},
    "enableRateLimit": True,
})
if TESTNET:
    exchange.set_sandbox_mode(True)

def fetch_symbols():
    markets = exchange.load_markets()
    return {s for s in SYMBOLS if s in markets}

def ohlcv(symbol, limit=120):
    return exchange.fetch_ohlcv(symbol, "1h", limit=limit)
def atr(df, period=ATR_PERIOD):
    closes = [c[4] for c in df]; highs = [c[2] for c in df]; lows = [c[3] for c in df]
    trs = [max(h - l, abs(h - c), abs(l - c)) for h, l, c in zip(highs[1:], lows[1:], closes[:-1])]
    if not trs: return [0]
    base = sum(trs[:period]) / period if len(trs)>=period else sum(trs)/len(trs)
    atrs = [base]
    for t in trs[period:]:
        atrs.append((atrs[-1] * (period - 1) + t) / period)
    return atrs
def rsi(closes, period=14):
    gains = []; losses = []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0)); losses.append(max(-d, 0))
    if not gains: return 50.0
    ag = sum(gains[:period]) / period; al = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
    if al == 0: return 100.0
    return 100 - 100 / (1 + ag / al)

def open_position(conn, symbol, side, df):
    global positions
    close = df[-1][4]; a = atr(df)[-1]
    if a <= 0: return
    alloc = USDT * 0.25 * 0.5
    qty = math.floor((alloc / close) / 0.001) * 0.001
    if qty <= 0: return
    stop_dist = a * ATR_MAP.get(symbol, ATR_MULT_DEFAULT)
    sl = close - stop_dist if side=="long" else close + stop_dist
    tp = close + a * RR if side=="long" else close - a * RR
    p = {"side": side, "entry": close, "qty": qty, "stop": sl, "tp": tp, "trail": sl}
    try:
        exchange.set_leverage(LEVERAGE.get(symbol, 2), symbol)
        db_save(conn, symbol, p); positions[symbol]=p
        print(f"[OPEN] {symbol} {side} qty {qty} entry {close}")
        alert("OPEN", f"{symbol} {side.upper()} qty {qty} @ {close:.4f} | SL {sl:.4f} TP {tp:.4f} | Modal ${USDT}")
    except Exception as e:
        print(f"[ERROR OPEN] {e}"); alert("ERROR", f"{symbol} open gagal: {e}")

def telegram_poll():
    off = None
    while True:
        try:
            r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
                              json={"timeout": 20, "offset": off}, timeout=25).json()
            for u in r.get("result", []):
                off = u["update_id"] + 1
                txt = u.get("message", {}).get("text","")
                if txt == "/status":
                    tg_send(f"✅ Active | Simbol: {len(SYMBOLS)} | Posisi: {len(positions)} | Testnet: {TESTNET} | PnL cek log")
        except Exception:
            pass
        time.sleep(2)

def main():
    global positions
    conn = db_init(); positions = db_load(conn)
    active = fetch_symbols()
    print(f"[OK] {len(active)}/{len(SYMBOLS)} simbol aktif | testnet={TESTNET}")
    tg_send(f"🤖 BOT NYALA! {len(active)}/{len(SYMBOLS)} aktif | testnet={TESTNET} | /status buat cek")
    threading.Thread(target=telegram_poll, daemon=True).start()
    while True:
        try:
            for sym in active:
                if sym in positions: continue
                df = ohlcv(sym)
                if not df or len(df) < 50: continue
                closes = [c[4] for c in df]
                r = rsi(closes)
                ema20 = sum(closes[-20:]) / 20; ema50 = sum(closes[-50:]) / 50
                print(f"[SCAN] {sym} ema20 {ema20:.2f} ema50 {ema50:.2f} rsi {r:.1f} posisi {len(positions)}")
                if ema20 > ema50 and 45 <= r <= 70:
                    open_position(conn, sym, "long", df)
                elif ema20 < ema50 and 30 <= r <= 55:
                    open_position(conn, sym, "short", df)
            time.sleep(60)
        except Exception as e:
            print(f"[LOOP ERROR] {e}"); time.sleep(20)

if __name__ == "__main__":
    main()
