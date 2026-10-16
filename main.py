import os, time, requests, traceback

print("[BOOT] LOGIKA LAMA + ANTI ERROR", flush=True)

SYMBOLS = ["LIT-USDT", "ONDO-USDT", "SUI-USDT", "ASTER-USDT", "SOL-USDT"]

def get_candles(instId):
    url = "https://www.okx.com/api/v5/market/candles"
    for _ in range(3):
        try:
            r = requests.get(url, params={"instId": instId, "bar":"5m", "limit":100},
                             timeout=15, headers={"User-Agent":"Mozilla/5.0"})
            txt = r.text.strip()
            if not txt.startswith("{"): # kalau dapet HTML
                print(f"[WARN] {instId} HTML retry", flush=True)
                time.sleep(3)
                continue
            j = r.json()
            if j["code"]!= "0":
                time.sleep(2)
                continue
            closes = [float(x[4]) for x in reversed(j["data"])]
            return closes
        except Exception as e:
            print(f"[RETRY] {instId} {e}", flush=True)
            time.sleep(3)
    raise Exception("OKX HTML terus")

def ema(data, period):
    k = 2/(period+1)
    e = data[0]
    for p in data[1:]: e = p*k + e*(1-k)
    return e

print("[OK] Start - no ccxt - LOGIKA TETAP", flush=True)

while True:
    for sym in SYMBOLS:
        try:
            closes = get_candles(sym)
            e20 = ema(closes, 20)
            e50 = ema(closes, 50)
            print(f"[SCAN] {sym.replace('-','')} {closes[-1]:.4f} e20={e20:.4f} e50={e50:.4f}", flush=True)
        except Exception as e:
            print(f"[SCAN] {sym} err {e}", flush=True)
    time.sleep(60)
