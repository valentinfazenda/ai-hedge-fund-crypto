import os
import math
import json
import time
import hmac
import base64
import hashlib
import requests
from kucoin.client import Client as SpotClient
from dotenv import load_dotenv

load_dotenv()

# Spot client (via SDK)
spot_client = SpotClient(
    api_key=os.getenv("KUCOIN_API_KEY"),
    api_secret=os.getenv("KUCOIN_API_SECRET"),
    passphrase=os.getenv("KUCOIN_API_PASSPHRASE")
)

# Futures credentials (raw requests)
FUTURES_BASE_URL = "https://api-futures.kucoin.com"
FUTURES_API_KEY = os.getenv("KUCOIN_API_KEY")
FUTURES_API_SECRET = os.getenv("KUCOIN_API_SECRET")
FUTURES_API_PASSPHRASE = os.getenv("KUCOIN_API_PASSPHRASE")

# === UTILS ===

def adjust_quantity_spot(symbol: str, quantity: float) -> float:
    market_data = spot_client.get_symbols()
    info = next((m for m in market_data if m['symbol'] == symbol), None)
    if not info:
        raise ValueError(f"[❌] Symbol {symbol} not found on KuCoin Spot.")
    
    step = float(info['baseIncrement'])
    min_qty = float(info['baseMinSize'])
    if quantity < min_qty:
        return 0.0
    
    precision = abs(int(math.log10(step)))
    return round(math.floor(quantity / step) * step, precision)

def generate_futures_headers(endpoint: str, method: str, body: str = "") -> dict:
    now = str(int(time.time() * 1000))
    str_to_sign = f"{now}{method}{endpoint}{body}"
    signature = base64.b64encode(hmac.new(
        FUTURES_API_SECRET.encode(), str_to_sign.encode(), hashlib.sha256
    ).digest()).decode()

    passphrase = base64.b64encode(hmac.new(
        FUTURES_API_SECRET.encode(), FUTURES_API_PASSPHRASE.encode(), hashlib.sha256
    ).digest()).decode()

    return {
        "KC-API-KEY": FUTURES_API_KEY,
        "KC-API-SIGN": signature,
        "KC-API-TIMESTAMP": now,
        "KC-API-PASSPHRASE": passphrase,
        "KC-API-KEY-VERSION": "2",
        "Content-Type": "application/json"
    }

def adjust_quantity_futures(symbol: str, quantity: float) -> float:
    try:
        r = requests.get(f"{FUTURES_BASE_URL}/api/v1/contracts/active")
        info = next((s for s in r.json().get("data", []) if s['symbol'] == symbol), None)
        if not info:
            return 0.0
        step = float(info['lotSize'])
        return math.floor(quantity / step) * step
    except:
        return quantity  # fallback

# === EXECUTION ===

def place_kucoin_order(symbol: str, action: str, quantity: float):
    symbol = to_kucoin_symbol(symbol)
    if action == "hold":
        print(f"[HOLD] {symbol} – no trade executed.")
        return

    if action in ("buy", "sell"):
        try:
            quantity = adjust_quantity_spot(symbol, quantity)
            if quantity <= 0.0:
                print(f"[SKIP] {symbol} {action.upper()} – qty too low.")
                return

            print(f"[SPOT] Placing {action.upper()} order {symbol} | Qty: {quantity}")
            result = spot_client.create_market_order(symbol=symbol, side=action, size=str(quantity))
            print(f"[✅] Spot order success: ID {result['orderId']}")
        except Exception as e:
            print(f"[❌] Spot order failed for {symbol}: {e}")

    elif action in ("short", "cover"):
        try:
            side = "sell" if action == "short" else "buy"
            futures_symbol = symbol + "M" if not symbol.endswith("M") else symbol
            quantity = adjust_quantity_futures(futures_symbol, quantity)
            if quantity <= 0.0:
                print(f"[SKIP] {futures_symbol} {action.upper()} – qty too low.")
                return

            endpoint = "/api/v1/orders"
            url = FUTURES_BASE_URL + endpoint

            order = {
                "symbol": futures_symbol,
                "side": side,
                "type": "market",
                "size": str(quantity),
                "leverage": 1
            }

            headers = generate_futures_headers(endpoint, "POST", json.dumps(order))
            response = requests.post(url, headers=headers, json=order)

            if response.status_code == 200:
                order_id = response.json().get("data", {}).get("orderId", "N/A")
                print(f"[✅] Futures {action.upper()} order: {futures_symbol} | Qty: {quantity} | ID: {order_id}")
            else:
                print(f"[❌] Futures order failed: {response.text}")

        except Exception as e:
            print(f"[❌] Futures execution error: {e}")
    else:
        print(f"[❓] Unknown action '{action}' for {symbol}. Skipping.")


def get_kucoin_spot_portfolio(client):
    try:
        accounts = client.get_accounts()
        spot_assets = [
            {
                'currency': acc['currency'],
                'available': float(acc['available']),
                'balance': float(acc['balance']),
                'type': acc['type']
            }
            for acc in accounts
            if acc['type'] == 'trade' and float(acc['balance']) > 0
        ]

        if not spot_assets:
            print("[ℹ️] No assets with non-zero balance in Spot Wallet.")
        else:
            print("📊 KuCoin SPOT Portfolio:")
            for asset in spot_assets:
                print(f" - {asset['currency']}: Available = {asset['available']}, Total = {asset['balance']}")

        return spot_assets

    except Exception as e:
        print(f"[❌] Failed to fetch KuCoin portfolio: {e}")
        return []

def get_kucoin_futures_positions():
    positions = []

    try:
        endpoint = "/api/v1/positions"
        url = FUTURES_BASE_URL + endpoint
        headers = generate_futures_headers(endpoint, "GET")
        resp = requests.get(url, headers=headers)

        if resp.status_code != 200:
            print(f"[❌] Failed to fetch futures positions: {resp.text}")
            return positions

        data = resp.json().get("data", [])
        for pos in data:
            qty = float(pos["currentQty"])
            if qty == 0:
                continue

            symbol = pos["symbol"].replace("M", "")
            entry_price = float(pos["entryPrice"])
            margin = float(pos["posMargin"])

            positions.append({
                "symbol": symbol,
                "side": "short" if qty < 0 else "long",
                "quantity": abs(qty),
                "entry_price": entry_price,
                "margin_used": margin
            })

        return positions

    except Exception as e:
        print(f"[❌] Futures position retrieval error: {e}")
        return positions
    
    
def build_portfolio_from_kucoin_assets(settings):
    portfolio = {
        "cash": 0.0,
        "positions": {},
        "realized_gains": {}
    }

    tickers = set(settings.signals.tickers)

    # === Spot Wallet ===
    spot_assets = get_kucoin_spot_portfolio(spot_client)
    for asset in spot_assets:
        currency = asset["currency"]
        balance = float(asset["balance"])

        if currency == "USDC":
            portfolio["cash"] = balance
            continue

        symbol = f"{currency}USDC"
        if symbol not in tickers:
            continue

        try:
            page = 1
            active_fills = []
            accumulated_qty = 0.0

            while accumulated_qty < balance:
                raw_fills = spot_client.get_fills(
                    symbol=to_kucoin_symbol(symbol),
                    side='buy',
                    trade_type='TRADE',
                    page=page,
                    limit=500,
                )

                fills = raw_fills["items"]
                if not fills:
                    break

                for fill in fills:
                    qty = float(fill['size'])
                    if accumulated_qty + qty > balance:
                        qty = balance - accumulated_qty

                    active_fills.append({
                        "price": float(fill['price']),
                        "qty": qty
                    })

                    accumulated_qty += qty
                    if accumulated_qty >= balance:
                        break

                page += 1

            total_qty = sum(f["qty"] for f in active_fills)
            total_cost = sum(f["qty"] * f["price"] for f in active_fills)
            avg_cost = total_cost / total_qty if total_qty > 0 else 0.0


        except Exception as e:
            print(f"[⚠️] Failed to get fills for {symbol}: {e}")
            avg_cost = 0.0

        portfolio["positions"][symbol] = {
            "long": balance,
            "short": 0.0,
            "long_cost_basis": avg_cost,
            "short_cost_basis": 0.0,
            "short_margin_used": 0.0
        }


    # === Futures Wallet ===
    futures_positions = get_kucoin_futures_positions()
    for pos in futures_positions:
        symbol = pos["symbol"]
        if symbol not in tickers:
            continue

        if symbol not in portfolio["positions"]:
            portfolio["positions"][symbol] = {
                "long": 0.0,
                "short": 0.0,
                "long_cost_basis": 0.0,
                "short_cost_basis": 0.0,
                "short_margin_used": 0.0
            }

        if pos["side"] == "short":
            portfolio["positions"][symbol]["short"] = pos["quantity"]
            portfolio["positions"][symbol]["short_cost_basis"] = pos["entry_price"]
            portfolio["positions"][symbol]["short_margin_used"] = pos["margin_used"]
        else:
            # Rare but possible (long futures position)
            portfolio["positions"][symbol]["long"] += pos["quantity"]
            portfolio["positions"][symbol]["long_cost_basis"] = pos["entry_price"]

    return portfolio



def to_kucoin_symbol(symbol: str) -> str:
    """Convert standard format (ETHUSDC) to KuCoin format (ETH-USDC)"""
    if symbol.endswith("USDT"):
        return symbol.replace("USDT", "-USDT")
    elif symbol.endswith("USDC"):
        return symbol.replace("USDC", "-USDC")
    elif symbol.endswith("BTC"):
        return symbol.replace("BTC", "-BTC")
    elif symbol.endswith("ETH"):
        return symbol.replace("ETH", "-ETH")
    return symbol