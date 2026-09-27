import os
import time
import threading
from flask import Flask
import pandas as pd
import numpy as np
import requests
from binance.client import Client

# Servidor Flask para Web Service en Render
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot Estrategia 3 (Scalping 5m Optimizado) Operativo", 200

# Configuración de Binance Demo / Testnet
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")

# Configuración de Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

client = Client(API_KEY, API_SECRET, testnet=True)
SYMBOL = "BTCUSDT"
TIMEFRAME = Client.KLINE_INTERVAL_5MINUTE
LEVERAGE = 10  # Apalancamiento 10x
INITIAL_CAPITAL = 500  # Capital asignado: $500 USD ($5,000 USD con 10x)

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
        print(f"⚙️ [Estrategia 3 - 5m] Apalancamiento configurado a {LEVERAGE}x en {SYMBOL} | Capital: ${INITIAL_CAPITAL} USD", flush=True)
    except Exception as e:
        print(f"⚠️ [Estrategia 3 - 5m] Error configurando apalancamiento: {e}", flush=True)

def get_market_data():
    klines = client.futures_klines(symbol=SYMBOL, interval=TIMEFRAME, limit=250)
    df = pd.DataFrame(klines, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'number_of_trades',
        'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
    ])
    df['close'] = df['close'].astype(float)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    df['volume'] = df['volume'].astype(float)
    
    # 1. EMAs de Scalping (8 y 21) + Filtro Macro de Tendencia (200)
    df['ema_fast'] = df['close'].ewm(span=8, adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span=21, adjust=False).mean()
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # 2. RSI (7 periodos - Scalping)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=7).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=7).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # 3. Filtro de Volumen (SMA 20)
    df['vol_sma'] = df['volume'].rolling(window=20).mean()
    
    # 4. ATR (14 periodos para SL/TP dinámicos)
    df['tr'] = np.maximum(
        df['high'] - df['low'],
        np.maximum(
            abs(df['high'] - df['close'].shift(1)),
            abs(df['low'] - df['close'].shift(1))
        )
    )
    df['atr'] = df['tr'].rolling(window=14).mean()
    
    # 5. ADX (14 periodos - Fuerza de Tendencia)
    up_move = df['high'] - df['high'].shift(1)
    down_move = df['low'].shift(1) - df['low']
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    plus_di = 100 * (pd.Series(plus_dm).rolling(14).mean() / df['atr'])
    minus_di = 100 * (pd.Series(minus_dm).rolling(14).mean() / df['atr'])
    dx = 100 * (abs(plus_di - minus_di) / (plus_di + minus_di))
    df['adx'] = dx.rolling(14).mean()
    
    return df

def run_trading_bot():
    print(f"🚀 Iniciando Bucle de Monitoreo - Estrategia 3 (Scalping 5m) | {SYMBOL} | Margen: ${INITIAL_CAPITAL} USD (10x)", flush=True)
    init_leverage()
    
    send_telegram_alert(f"🤖 *Bot Estrategia 3 (Scalping 5m)* iniciado correctamente en Render.\n\n💰 *Capital Asignado:* ${INITIAL_CAPITAL} USD (10x)")
    
    last_processed_time = None
    
    while True:
        try:
            df = get_market_data()
            last_closed = df.iloc[-2]  # Vela de 5 minutos recién cerrada
            candle_time = last_closed['timestamp']
            
            if candle_time != last_processed_time:
                close_price = last_closed['close']
                ema_fast = last_closed['ema_fast']
                ema_slow = last_closed['ema_slow']
                ema_200 = last_closed['ema_200']
                rsi = last_closed['rsi']
                volume = last_closed['volume']
                vol_sma = last_closed['vol_sma']
                atr = last_closed['atr']
                adx = last_closed['adx']
                
                timestamp_str = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(candle_time/1000))
                print(f"[{timestamp_str} UTC] VELA 5M CERRADA | Precio: ${close_price:.2f} | EMA8: ${ema_fast:.2f} | EMA21: ${ema_slow:.2f} | EMA200: ${ema_200:.2f} | RSI: {rsi:.2f} | ADX: {adx:.1f}", flush=True)
                
                # CONDICIÓN LONG OPTIMIZADA
                if (close_price > ema_200) and (ema_fast > ema_slow) and (rsi > 55) and (volume > (vol_sma * 1.2)) and (adx > 20):
                    tp_price = close_price + (atr * 1.5)
                    sl_price = close_price - (atr * 1.0)
                    position_size_usd = INITIAL_CAPITAL * LEVERAGE
                    msg = (
                        f"🟢 *SEÑAL LONG SCALPING (10x)*\n\n"
                        f"*Estrategia:* 3 (Scalping 5m)\n"
                        f"*Par:* {SYMBOL}\n"
                        f"*Capital Posición:* ${INITIAL_CAPITAL} USD (${position_size_usd} Notional)\n"
                        f"*Precio Entrada:* ${close_price:.2f}\n"
                        f"*Take Profit (1.5 ATR):* ${tp_price:.2f}\n"
                        f"*Stop Loss (1.0 ATR):* ${sl_price:.2f}\n"
                        f"*Filtro Trend:* Precio > EMA200 (${ema_200:.2f})\n"
                        f"*ADX:* {adx:.1f} | *RSI:* {rsi:.1f}"
                    )
                    print(msg, flush=True)
                    send_telegram_alert(msg)
                    
                # CONDICIÓN SHORT OPTIMIZADA
                elif (close_price < ema_200) and (ema_fast < ema_slow) and (rsi < 45) and (volume > (vol_sma * 1.2)) and (adx > 20):
                    tp_price = close_price - (atr * 1.5)
                    sl_price = close_price + (atr * 1.0)
                    position_size_usd = INITIAL_CAPITAL * LEVERAGE
                    msg = (
                        f"🔴 *SEÑAL SHORT SCALPING (10x)*\n\n"
                        f"*Estrategia:* 3 (Scalping 5m)\n"
                        f"*Par:* {SYMBOL}\n"
                        f"*Capital Posición:* ${INITIAL_CAPITAL} USD (${position_size_usd} Notional)\n"
                        f"*Precio Entrada:* ${close_price:.2f}\n"
                        f"*Take Profit (1.5 ATR):* ${tp_price:.2f}\n"
                        f"*Stop Loss (1.0 ATR):* ${sl_price:.2f}\n"
                        f"*Filtro Trend:* Precio < EMA200 (${ema_200:.2f})\n"
                        f"*ADX:* {adx:.1f} | *RSI:* {rsi:.1f}"
                    )
                    print(msg, flush=True)
                    send_telegram_alert(msg)
                    
                else:
                    reasons = []
                    if adx <= 20: reasons.append(f"ADX bajo ({adx:.1f})")
                    if volume <= (vol_sma * 1.2): reasons.append("Volumen insuficiente")
                    if close_price <= ema_200 and ema_fast > ema_slow: reasons.append("Precio bajo EMA200 (Bloquea Long)")
                    if close_price >= ema_200 and ema_fast < ema_slow: reasons.append("Precio sobre EMA200 (Bloquea Short)")
                    print(f"ℹ️ Sin entrada 5M. Motivo: {', '.join(reasons)}", flush=True)
                    
                last_processed_time = candle_time
                
        except Exception as e:
            print(f"❌ Error en el ciclo principal 5M: {e}", flush=True)
            time.sleep(120)  # Pausa de 2 min para limpiar límites de API/IP si ocurre error
            continue
            
        time.sleep(30)  # Revisa cada 30 segundos si cerró la vela de 5m

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_trading_bot)
    bot_thread.daemon = True
    bot_thread.start()
    run_flask()
