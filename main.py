import time, requests

SYMBOLS = ["LIT-USDT","ONDO-USDT","SUI-USDT","ASTER-USDT","SOL-USDT"]
pos = {} # simpan entry price

def get_candles(s):
    for _ in range(3):
        try:
            r = requests.get("https://www.okx.com/api/v5/market/candles",
                params={"instId":s,"bar":"5m","limit":100},
                timeout=15, headers={"User-Agent":"Mozilla/5.0"})
            if not r.text.strip().startswith("{"): continue
            j=r.json()
            if j.get("code")!="0": continue
            return [float(x[4]) for x in reversed(j["data"])]
        except: time.sleep(2)
    return None

def ema(d,p):
    k=2/(p+1); e=d[0]
    for x in d[1:]: e=x*k+e*(1-k)
    return e

print("[OK] BOT PAPER PROFIT - TANPA TELE", flush=True)

while True:
    for s in SYMBOLS:
        closes=get_candles(s)
        if not closes: continue
        price=closes[-1]
        e20=ema(closes,20); e50=ema(closes,50)

        name=s.replace('-','')
        prev_e20=ema(closes[:-1],20)
        prev_e50=ema(closes[:-1],50)

        # BUY baru (cross up)
        if e20>e50 and prev_e20<=prev_e50:
            pos[name]=price
            print(f"[BUY] {name} @ {price:.4f} e20>e50", flush=True)
        # SELL (cross down) + hitung profit
        elif e20<e50 and prev_e20>=prev_e50 and name in pos:
            entry=pos.pop(name)
            pnl=(price-entry)/entry*100
            print(f"[SELL] {name} @ {price:.4f} Entry {entry:.4f} PNL {pnl:+.2f}%", flush=True)
        else:
            if name in pos:
                pnl=(price-pos[name])/pos[name]*100
                print(f"[HOLD] {name} {price:.4f} PNL {pnl:+.2f}%", flush=True)
            else:
                print(f"[SCAN] {name} {price:.4f} nunggu sinyal", flush=True)
    time.sleep(60)
