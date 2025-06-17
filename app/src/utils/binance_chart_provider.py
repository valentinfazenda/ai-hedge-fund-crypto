import os
import sys
import io
import base64
import matplotlib.pyplot as plt
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
import matplotlib.pyplot as plt
from dotenv import load_dotenv

import os, datetime as dt, pandas as pd, numpy as np, mplfinance as mpf
from binance.client import Client

load_dotenv()

client = Client(
    api_key=os.getenv("BINANCE_API_KEY"),
    api_secret=os.getenv("BINANCE_API_SECRET"),
    tld="com",
)

def fetch_klines(client, symbol, interval, end_date=None):
    data = client.get_klines(symbol=symbol, interval=interval, limit=60, endTime=end_date)
    df = pd.DataFrame(data, columns=['time','open','high','low','close','volume','close_time','qav','trades','tbbav','tbqav','ignore'])
    df['time'] = pd.to_datetime(df['time'], unit='ms')
    df.set_index('time', inplace=True)
    df = df[['open','high','low','close','volume']].astype(float)
    return df

def rsi(series, period):
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def macd(close, fast=12, slow=26, signal=9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist

def add_indicators(df):
    df['MA5']  = df['close'].rolling(5).mean()
    df['MA10'] = df['close'].rolling(10).mean()

    bb_mid = df['close'].rolling(20).mean()
    bb_std = df['close'].rolling(20).std()
    df['BBU'] = bb_mid + 2 * bb_std
    df['BBL'] = bb_mid - 2 * bb_std
    df['BBM'] = bb_mid

    df['RSI6'] = rsi(df['close'], 6)
    df['RSI12'] = rsi(df['close'], 12)
    df['RSI24'] = rsi(df['close'], 24)

    df['MACD'], df['MACD_signal'], df['MACD_hist'] = macd(df['close'])
    return df

def plot_chart(df, symbol, interval):
    last_price = df['close'].iloc[-1]
    title = f'{symbol} - {interval} | Last: {last_price:.2f}'
    mc = mpf.make_marketcolors(up='#26A69A', down="#E9615F", inherit=True)
    style = mpf.make_mpf_style(
    base_mpf_style='classic',
    marketcolors=mc,
    rc={'font.size': 10}
    )


    ap = [
        mpf.make_addplot(df['MA5'], color='magenta', width=1, label='MA5'),
        mpf.make_addplot(df['MA10'], color='orange', width=1, label='MA10'),
        mpf.make_addplot(df['BBU'], color='gold', width=0.75, label='BB Upper'),
        mpf.make_addplot(df['BBM'], color='blue', width=0.75, label='BB Mid'),
        mpf.make_addplot(df['BBL'], color='purple', width=0.75, label='BB Lower'),

        mpf.make_addplot(df['MACD'], panel=2, color='gold', label='MACD'),
        mpf.make_addplot(df['MACD_signal'], panel=2, color='purple', label='Signal'),
        mpf.make_addplot(df['MACD_hist'], panel=2, type='bar',
                         color=np.where(df['MACD_hist'] >= 0, 'g', 'r'), alpha=0.6),

        mpf.make_addplot(df['RSI6'], panel=3, color='gold', label='RSI6'),
        mpf.make_addplot(df['RSI12'], panel=3, color='magenta', label='RSI12'),
        mpf.make_addplot(df['RSI24'], panel=3, color='purple', label='RSI24'),

        # Ligne de prix actuelle
        mpf.make_addplot([last_price]*len(df), color='black', secondary_y=False, linestyle='--')
    ]

    fig, axlist = mpf.plot(
        df,
        type='candle',
        style=style,
        title=title,
        addplot=ap,
        volume=True,
        panel_ratios=(6,2,2,2),
        figsize=(20, 10),
        tight_layout=True,
        update_width_config=dict(candle_linewidth=0.7, candle_width=0.6),
        xrotation=15,
        ylabel='Price',
        ylabel_lower='Volume',
        returnfig=True,
    )
    
    for ax in axlist:
        ax.grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.7)
        ax.minorticks_on()
        
    axlist[0].yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x:,.0f}'))
    last_close = df['close'].iloc[-1]
    axlist[0].axhline(y=last_close, color='black', linestyle='--', linewidth=1)
    
    axlist[0].annotate(
        f'{last_close:.2f}',
        xy=(df.index[-1], last_close),
        xytext=(20, 0),
        textcoords='offset points',
        ha='left', va='bottom',
        fontsize=8,
        bbox=dict(facecolor='white', edgecolor='none', alpha=0.7)
    )
        
    buf = io.BytesIO()
    fig.savefig(buf, format='png')
    plt.close(fig)
    buf.seek(0)

    img_base64 = base64.b64encode(buf.read()).decode('utf-8')

    # plt.imshow(plt.imread(io.BytesIO(base64.b64decode(img_base64))))
    # plt.axis('off')
    # plt.show()
    
    return img_base64

def get_chart(symbol, interval, end_date=None):
    df = fetch_klines(client, symbol, interval, end_date)
    df = add_indicators(df)
    
    return  plot_chart(df, symbol, interval)


if __name__ == '__main__':
    # end_date = int(pd.to_datetime("2025-06-11").timestamp() * 1000)
    df = fetch_klines(client, "ETHUSDC", "1m")
    df = add_indicators(df)
    chart_base64 = plot_chart(df, "ETHUSDC", "1m")