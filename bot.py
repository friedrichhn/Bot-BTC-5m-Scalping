# Version Auto-Trade Binance Futures Testnet - Scalping 5m
import os
import time
import threading
from flask import Flask
import pandas as pd
import numpy as np
import requests
from binance.client import Client

app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot Estrategia 3 (Scalping 5m Autotrade) Operativo", 200

API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

client = Client(API_KEY, API_SECRET, testnet=True)
SYMBOL = "BTCUSDT"
TIMEFRAME = Client.KLINE_INTERVAL_5MINUTE
LEVERAGE = 10
INITIAL_CAPITAL = 500  # Capital en USD

def send_telegram_alert(message):
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "Markdown"
            }
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            print(f"⚠️ Error enviando alerta a Telegram: {e}", flush=True)

def init_leverage():
    try:
        client.futures_change_leverage(symbol=SYMBOL, leverage=LEVERAGE)
        print(f"⚙️ [Estrategia 3 - 5m] Apalancamiento configurado a {LEVERAGE}x en {SYMBOL}", flush=True)
    except Exception as e:
        print(f"⚠️ [Estrategia 3 - 5m] Error configurando apalancamiento: {e}", flush=True)

def execute_binance_trade(side, close_price, tp_price, sl_price):
    try:
        notional_value = INITIAL_CAPITAL * LEVERAGE
        quantity = round(notional_value / close_price, 3)
        
        # 1. Orden de Mercado Principal
        order = client.futures_create_order(
            symbol=SYMBOL,
            side=side,
            type='MARKET',
            quantity=quantity
        )
        print(f"✅ Orden de Mercado Ejecutada en Binance: {side} {quantity} BTC", flush=True)
        
        # Dirección opuesta para cerrar la posición
        tp_side = 'SELL' if side == 'BUY' else 'BUY'
        
        # 2. Take Profit con cantidad explícita (sin closePosition)
        client.futures_create_order(
            symbol=SYMBOL,
            side=tp_side,
            type='TAKE_PROFIT_MARKET',
            stopPrice=round(tp_price, 2),
            quantity=quantity
        )
        
        # 3. Stop Loss con cantidad explícita (sin closePosition)
        client.futures_create_order(
            symbol=SYMBOL,
            side=tp_side,
            type='STOP_MARKET',
            stopPrice=round(sl_price, 2),
            quantity=quantity
        )
        
        return f"🚀 *ORDEN EJECUTADA EN BINANCE TESTNET*\nCantidad: `{quantity} BTC` (${notional_value} Notional)"
    
    except Exception as e:
        err_msg = f"❌ Error ejecutando orden en Binance: {e}"
        print(err_msg, flush=True)
        return f"⚠️ *Error al ejecutar en Binance:* {e}"

def get_market_data():
    klines = client.futures_klines(symbol=SYMBOL, interval=TIMEFRAME, limit=200)
    df = pd.DataFrame(klines, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'number_of_trades',
        'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
    ])
    df['close'] = df['close'].astype(float)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    df['volume'] = df['volume'].astype(float)
    
    df['ema8'] = df['close'].ewm(span=8, adjust=False).mean()
    df['ema21'] = df['close'].ewm(span=21, adjust=False).mean()
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    df['tr'] = np.maximum(
        df['high'] - df['low'],
        np.maximum(
            abs(df['high'] - df['close'].shift(1)),
            abs(df['low'] - df['close'].shift(1))
        )
    )
    df['atr'] = df['tr'].rolling(window=14).mean()
    
    up_move = df['high'] - df['high'].shift(1)
    down_move = df['low'].shift(1) - df['low']
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    plus_di = 100 * (pd.Series(plus_dm).rolling(14).mean() / df['atr'])
    minus_di = 100 * (pd.Series(minus_dm).rolling(14).mean() / df['atr'])
    dx = 100 * (abs(plus_di - minus_di) / (plus_di + minus_di))
    df['adx'] = dx.rolling(14).mean()
    
    df['vol_ma'] = df['volume'].rolling(window=20).mean()
    
    return df

def run_trading_bot():
    print("🚀 Bucle de Monitoreo Iniciado - Estrategia 3 (Scalping 5m)", flush=True)
    init_leverage()
    send_telegram_alert("🤖 Bot Estrategia 3 (Scalping 5m Auto-Trade) activo en Render.")
    
    last_processed_time = None
    
    while True:
        try:
            df = get_market_data()
            last_closed = df.iloc[-2]
            candle_time = last_closed['timestamp']
            
            if candle_time != last_processed_time:
                close_price = last_closed['close']
                ema8 = last_closed['ema8']
                ema21 = last_closed['ema21']
                ema200 = last_closed['ema200']
                rsi = last_closed['rsi']
                adx = last_closed['adx']
                atr = last_closed['atr']
                volume = last_closed['volume']
                vol_ma = last_closed['vol_ma']
                
                print("VELA 5M CERRADA -> Precio:", close_price, "EMA8:", ema8, "EMA21:", ema21, "ADX:", adx, "RSI:", rsi, flush=True)
                
                if (close_price > ema200) and (ema8 > ema21) and (adx > 20) and (volume > vol_ma * 1.2) and (rsi > 55):
                    tp_price = close_price + (atr * 1.5)
                    sl_price = close_price - (atr * 1.0)
                    exec_status = execute_binance_trade('BUY', close_price, tp_price, sl_price)
                    
                    msg = (
                        f"🟢 *SEÑAL LONG SCALPING DETECTADA (10x)*\n\n"
                        f"*Estrategia:* 3 (Scalping 5m)\n"
                        f"*Par:* {SYMBOL}\n"
                        f"*Capital Posición:* ${INITIAL_CAPITAL} USD (${INITIAL_CAPITAL * LEVERAGE} Notional)\n"
                        f"*Precio Entrada:* ${close_price:.2f}\n"
                        f"*Take Profit:* ${tp_price:.2f}\n"
                        f"*Stop Loss:* ${sl_price:.2f}\n"
                        f"*Filtro Trend:* Precio > EMA200 (${ema200:.2f})\n"
                        f"*ADX:* {adx:.1f} | *RSI:* {rsi:.1f}\n\n"
                        f"{exec_status}"
                    )
                    print(msg, flush=True)
                    send_telegram_alert(msg)
                    
                elif (close_price < ema200) and (ema8 < ema21) and (adx > 20) and (volume > vol_ma * 1.2) and (rsi < 45):
                    tp_price = close_price - (atr * 1.5)
                    sl_price = close_price + (atr * 1.0)
                    exec_status = execute_binance_trade('SELL', close_price, tp_price, sl_price)
                    
                    msg = (
                        f"🔴 *SEÑAL SHORT SCALPING DETECTADA (10x)*\n\n"
                        f"*Estrategia:* 3 (Scalping 5m)\n"
                        f"*Par:* {SYMBOL}\n"
                        f"*Capital Posición:* ${INITIAL_CAPITAL} USD (${INITIAL_CAPITAL * LEVERAGE} Notional)\n"
                        f"*Precio Entrada:* ${close_price:.2f}\n"
                        f"*Take Profit:* ${tp_price:.2f}\n"
                        f"*Stop Loss:* ${sl_price:.2f}\n"
                        f"*Filtro Trend:* Precio < EMA200 (${ema200:.2f})\n"
                        f"*ADX:* {adx:.1f} | *RSI:* {rsi:.1f}\n\n"
                        f"{exec_status}"
                    )
                    print(msg, flush=True)
                    send_telegram_alert(msg)
                    
                else:
                    reasons = []
                    if close_price <= ema200 and close_price >= ema200: reasons.append("Precio cruzando o sobre EMA200")
                    if ema8 <= ema21 and ema8 >= ema21: reasons.append("EMAs sin cruce claro")
                    if adx <= 20: reasons.append(f"ADX bajo ({adx:.1f} <= 20)")
                    if volume <= vol_ma * 1.2: reasons.append("Volumen insuficiente")
                    if close_price > ema200 and rsi <= 55: reasons.append(f"RSI bajo para Long ({rsi:.1f})")
                    if close_price < ema200 and rsi >= 45: reasons.append(f"RSI alto para Short ({rsi:.1f})")
                    print("Sin entrada 5M. Motivo:", ", ".join(reasons), flush=True)
                    
                last_processed_time = candle_time
                
        except Exception as e:
            print("Error en ciclo 5M:", e, flush=True)
            time.sleep(60)
            continue
            
        time.sleep(15)

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_trading_bot)
    bot_thread.daemon = True
    bot_thread.start()
    run_flask()
