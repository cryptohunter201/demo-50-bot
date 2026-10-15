import os, time, requests
from datetime import datetime

# === SETTING DEMO $50 ===
USDT_PER_TRADE = 50
SYMBOLS = ["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT"]

TELE_TOKEN = os.getenv("TELE_TOKEN")
TELE_CHAT_ID = os.getenv("TELE_CHAT_ID")

def send_tele(msg):
    try:
        url = f"https://api.telegram.org/bot{TELE_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELE_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        print("Tele error", e)

print("=== BOT DEMO $50 START ===")
send_tele("✅ *BOT DEMO $50 AKTIF*\n\nModal: $50 per koin\nKoin: BTC, ETH, SOL, BNB, XRP\nMode: Sinyal DEMO (bukan real trade)\nStatus: Jalan 24 jam di Railway")

balance = USDT_PER_TRADE * len(SYMBOLS)

while True:
    now = datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] DEMO $50 running - Balance simulasi ${balance}")
    # Simulasi sinyal tiap 5 menit
    time.sleep(300)
    send_tele(f"📈 *Sinyal DEMO $50* [{now}]\nSemua koin HOLD\nSaldo simulasi: ${balance}\nBot masih aktif ✅")
