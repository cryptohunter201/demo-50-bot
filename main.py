# neurobro_perp_bot.py
import os, math, time, sqlite3, requests, threading
from datetime import datetime, timezone
import ccxt

# ---------- ENV / CONFIG ----------
TESTNET = os.getenv("TESTNET", "true").lower() == "true"
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
DB_PATH = os.getenv("DB_PATH", "neurobro_state.db")

USDT = 100.0
RISK_PER_TRADE = 0.012          # 1,2% modal per trade
DAILY_LOSS_LIMIT = 0.015        # stop 1,5% / hari
MAX_CORR_RISK = 0.045           # 4,5% all-in max
CONSEC_LOSS_CAP = 3
ATR_PERIOD, ATR_MULT = 14, 1.28
TRAIL_ACTIVATE, TRAIL_MULT = 2.1, 1.15
RR, TP1_TAKE = 2.2, 0.5

SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT",
           "AVAX/USDT:USDT", "SUI/USDT:USDT", "BNB/USDT:USDT",
           "LIT/USDT:USDT", "ASTER/USDT:USDT", "ONDO/USDT:USDT"]

ATR_MULT = {**{s: ATR_MULT for s in SYMBOLS},
            "LIT/USDT:USDT": 1.60, "ASTER/USDT:USDT": 1.60, "ONDO/USDT:USDT": 1.60}
TRAIL_MULT = {**{s: TRAIL_MULT for s in SYMBOLS},
              "LIT/USDT:USDT": 1.3, "ASTER/USDT:USDT": 1.3, "ONDO/USDT:USDT": 1.3}
LEVERAGE = {"BTC/USDT:USDT": 5, "ETH/USDT:USDT": 4, "SOL/USDT:USDT": 3,
            "BNB/USDT:USDT": 3, "AVAX/USDT:USDT": 2, "SUI/USDT:USDT": 2,
            "LIT/USDT:USDT": 2, "ASTER/USDT:USDT": 2, "ONDO/USDT:USDT": 2}

# ---------- TELEGRAM ----------
def tg_send(text):
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        return
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                      json={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=5)
    except Exception as e:
        print(f"[TG] {e}")

def alert(title, msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    tg_send(f"\u26a0\ufe0f [{title}] {msg} · {ts}")

# ---------- PERSISTENCE ----------
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

def db_set(conn, k, v):
    conn.execute("INSERT OR REPLACE INTO stats VALUES (?,?)", (k, str(v))); conn.commit()

def db_get(conn, k):
    r = conn.execute("SELECT value FROM stats WHERE key=?", (k,)).fetchone()
    return r[0] if r else None

# ---------- EXCHANGE ----------
exchange = ccxt.binance({
    "apiKey": BINANCE_API_KEY, "secret": BINANCE_API_SECRET,
    "options": {"defaultType": "swap"},
    "enableRateLimit": True, "adjustForTimeDifference": True,
})
if TESTNET:
    exchange.set_sandbox_mode(True)

def fetch_symbols():
    markets = exchange.load_markets()
    return {s for s in SYMBOLS if s in markets}

# ---------- HELPERS ----------
def ohlcv(symbol, limit=120):
    return exchange.fetch_ohlcv(symbol, "1h", limit=limit)

def atr(df, period=ATR_PERIOD):
    closes = [c[4] for c in df]; highs = [c[2] for c in df]; lows = [c[3] for c in df]
    trs = [max(h - l, abs(h - c), abs(l - c))
           for h, l, c in zip(highs[:-1], lows[:-1], closes[:-1])]
    base = sum(trs[:period]) / period
    atrs = [base]
    for t in trs[period:]:
        atrs.append((atrs[-1] * (period - 1) + t) / period)
    return atrs

def rsi(closes, period=14):
    gains = [] ; losses = []
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

def floor_qty(symbol, qty):
    tick = exchange.market(symbol)["precision"]["amount"]
    return math.floor(qty / tick) * tick

# ---------- TRADING ----------
def open_position(conn, symbol, side, df):
    last = df[-1]; close = last[4]; a = atr(df)[-1]
    if a <= 0 or close <= 0: return
    cfg = {"shr": 0.5, "corr": 1.0}  # nonce lembaga; placeholder
    alloc = USDT * (0.25 * cfg["shr"]) * cfg["corr"]
    alloc = min(alloc, USDT * MAX_CORR_RISK)
    qty = floor_qty(symbol, alloc / close)
    if qty <= 0: return
    stop_dist = a * ATR_MULT.get(symbol, ATR_MULT)
    if side == "long":
        sl = close - stop_dist; tt = close + a * RR; stop2 = close - a * 0.7
        trail_stop = sl
    else:
        sl = close + stop_dist; tt = close - a * RR; stop2 = close + a * 0.7
        trail_stop = sl
    tp = tt if abs(tt - close) < abs(stop2 - close) else stop2
    p = {"side": side, "entry": close, "qty": qty, "stop": sl,
         "tp": tp, "trail": trail_stop}
    try:
        exchange.set_leverage(LEVERAGE.get(symbol, 2), symbol)
        exchange.create_order(symbol, "limit", side.lower(), qty, close)
        db_save(conn, symbol, p)
        alert("OPEN", f"{symbol} {side.upper()} {qty} @ {close:.6g} | SL {sl:.6g}")
    except Exception as e:
        alert("ERROR", f"{symbol} open gagal: {e}")

def manage_positions(conn, positions):
    now = datetime.now(timezone.utc).date().isoformat() + " 00:00"
    for symbol, p in list(positions.items()):
        try:
            tick = exchange.fetch_ticker(symbol)
            price = tick["last"]
        except Exception:
            continue
        if p["side"] == "long":
            if price <= p["stop"] or price >= p["tp"]:
                exchange.create_order(symbol, "market", "sell", p["qty"])
                db_forget(conn, symbol); del positions[symbol]
                alert("CLOSED", f"{symbol} exit @ {price:.6g} | entry {p['entry']:.6g}")
            elif price >= p["entry"] * (1 + TRAIL_ACTIVATE * (p["tp"] - p["entry"]) / (p["tp"] - p["stop"])):
                new_stop = max(p["trail"], price * (1 - TRAIL_MULT * (p["tp"] - p["entry"]) / (p["tp"] - p["stop"])))
                if new_stop > p["trail"]: p["trail"] = new_stop
        else:
            if price >= p["stop"] or price <= p["tp"]:
                exchange.create_order(symbol, "market", "buy", p["qty"])
                db_forget(conn, symbol); del positions[symbol]
                alert("CLOSED", f"{symbol} exit @ {price:.6g} | entry {p['entry']:.6g}")

# ---------- TELEGRAM STATUS THREAD ----------
def telegram_poll():
    off = None
    while True:
        try:
            r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
                              json={"timeout": 20, "offset": off}, timeout=25).json()
            for u in r.get("result", []):
                off = u["update_id"] + 1
                if u.get("message", {}).get("text") == "/status":
                    tg_send(f"Simbol: {len(fetch_symbols())} | Posisi: {len(positions)}")
        except Exception:
            pass
        time.sleep(1)

# ---------- MAIN ----------
def main():
    conn = db_init()
    positions = db_load(conn)
    active = fetch_symbols()
    print(f"[OK] {len(active)}/{len(SYMBOLS)} simbol aktif | testnet={TESTNET}")
    threading.Thread(target=telegram_poll, daemon=True).start()
    consec_loss = 0
    while True:
        try:
            eq = USDT - consec_loss * RISK_PER_TRADE * USDT
            if consec_loss >= CONSEC_LOSS_CAP or eq <= USDT * (1 - DAILY_LOSS_LIMIT):
                alert("STOP", "Daily loss limit tercapai - bot berhenti"); break
            ema = None
            for sym in active:
                if sym in positions: continue
                df = ohlcv(sym)
                if not df or len(df) < 30: continue
                closes = [c[4] for c in df]
                r = rsi(closes); a = atr(df)[-1]
                ema20 = sum(closes[-20:]) / 20
                ema50 = sum(closes[-50:]) / 50
                if ema20 > ema50 and 45 <= r <= 70:
                    open_position(conn, sym, "long", df)
                elif ema20 < ema50 and 30 <= r <= 55:
                    open_position(conn, sym, "short", df)
            manage_positions(conn, positions)
            time.sleep(15)
        except Exception as e:
            alert("ERROR", f"Loop: {e}")
            time.sleep(20)

if __name__ == "__main__":
    main()
