import os, math, time
from decimal import Decimal, ROUND_DOWN
from binance.client import Client
from dotenv import load_dotenv

load_dotenv()

# === CLIENT ===
bn_client = Client(
    api_key=os.getenv("BINANCE_API_KEY"),
    api_secret=os.getenv("BINANCE_API_SECRET"),
    tld="com",
)

# cache exchange-info to avoid extra calls
_EX_INFO = {s["symbol"]: s for s in bn_client.get_exchange_info()["symbols"]}


# === UTILS ===
def _lot_step(symbol: str) -> tuple[Decimal, Decimal]:
    info = _EX_INFO.get(symbol)
    if not info:
        raise ValueError(f"{symbol} not listed on Binance.")
    f = next(f for f in info["filters"] if f["filterType"] == "LOT_SIZE")
    return Decimal(f["minQty"]), Decimal(f["stepSize"])


def adjust_quantity_margin(symbol: str, quantity: float) -> float:
    min_qty, step = _lot_step(symbol)
    qty = Decimal(str(quantity))
    if qty < min_qty:
        return 0.0
    # floor to step
    return float((qty // step) * step)


def to_binance_symbol(symbol: str) -> str:
    return symbol.replace("-", "").upper()


# === EXECUTION ===
def place_binance_order(
    symbol: str,
    action: str,
    quantity: float,
    isolated: bool = False,
):
    symbol = to_binance_symbol(symbol)
    qty = adjust_quantity_margin(symbol, quantity)
    if (action=='hold'):
        print(f"[SKIP] {symbol} {action.upper()} – no action taken.")
        return
    if qty <= 0:
        print(f"[SKIP] {symbol} {action.upper()} – qty too low.")
        return

    side_map = {
        "buy": ("BUY", "MARGIN_BUY"),
        "sell": ("SELL", "AUTO_REPAY"),
        "short": ("SELL", "MARGIN_BUY"),
        "cover": ("BUY", "AUTO_REPAY"),
    }
    if action not in side_map:
        print(f"[❓] Unknown action '{action}' for {symbol}.")
        return

    side, effect = side_map[action]
    try:
        res = bn_client.create_margin_order(
            symbol=symbol,
            side=side,
            type="MARKET",
            quantity=str(qty),
            sideEffectType=effect,
            isIsolated="TRUE" if isolated else "FALSE",
        )
        print(
            f"[✅] Margin {action.upper()} {symbol} | Qty {qty} | ID {res.get('orderId','N/A')}"
        )
    except Exception as e:
        print(f"[❌] Margin execution error: {e}")


# === PORTFOLIO ===
def get_binance_margin_portfolio():
    try:
        acc = bn_client.get_margin_account()
        assets = [
            {
                "asset": a["asset"],
                "free": float(a["free"]),
                "borrowed": float(a["borrowed"]),
                "interest": float(a["interest"]),
                "net": float(a["netAsset"]),
            }
            for a in acc["userAssets"]
            if float(a["free"]) or float(a["borrowed"])
        ]
        if not assets:
            print("[ℹ️] Margin Wallet empty.")
        else:
            print("📊 Binance MARGIN Portfolio:")
            for a in assets:
                print(
                    f" - {a['asset']}: Free={a['free']}, Borrowed={a['borrowed']}, Net={a['net']}"
                )
        return assets
    except Exception as e:
        print(f"[❌] Portfolio fetch error: {e}")
        return []


def get_binance_margin_positions():
    pos = []
    try:
        # open margin orders (cross + isolated)
        orders = bn_client.get_open_margin_orders()
        for o in orders:
            if float(o["origQty"]) == 0:
                continue
            pos.append(
                {
                    "symbol": o["symbol"],
                    "side": "long" if o["side"] == "BUY" else "short",
                    "quantity": float(o["origQty"]),
                    "price": float(o["price"]) if o["price"] else 0.0,
                }
            )
        if not pos:
            print("[ℹ️] No active margin orders found.")
        return pos
    except Exception as e:
        print(f"[❌] Margin order retrieval error: {e}")
        return pos

def _price(symbol: str) -> float:
    return float(bn_client.get_symbol_ticker(symbol=symbol)["price"])


def _cost_basis(symbol: str, qty: float, is_long: bool) -> float:
    if qty == 0:
        return 0.0
    trades = bn_client.get_margin_trades(symbol=symbol, limit=1000)
    trades = [t for t in trades if t["isBuyer"] is is_long]
    trades.sort(key=lambda x: x["time"], reverse=True)
    q = c = 0.0
    for t in trades:
        size = float(t["qty"])
        take = min(size, qty - q)
        q += take
        c += take * float(t["price"])
        if q >= qty:
            break
    return c / q if q else 0.0


def build_portfolio_from_binance_assets(settings):
    port = {"cash": 0.0, "positions": {}, "realized_gains": {}, "margin_requirement": settings.margin_requirement}
    tickers = set(settings.signals.tickers)

    acc = bn_client.get_margin_account()
    usdc = next((a for a in acc["userAssets"] if a["asset"] == "USDC"), {"free": "0"})
    port["cash"] = float(usdc["free"])

    for a in acc["userAssets"]:
        base = a["asset"]
        if base == "USDC":
            continue
        sym = f"{base}USDC"
        if sym not in tickers:
            continue

        free = float(a["free"])
        borrowed = float(a["borrowed"])
        if free == borrowed == 0:
            continue

        long_qty = max(0.0, free - borrowed)
        short_qty = max(0.0, borrowed - free)
        long_cb = _cost_basis(sym, long_qty, True)
        short_cb = _cost_basis(sym, short_qty, False)
        margin_used = short_qty * (short_cb if short_cb else _price(sym))

        port["positions"][sym] = {
            "long": long_qty,
            "short": short_qty,
            "long_cost_basis": long_cb,
            "short_cost_basis": short_cb,
            "short_margin_used": margin_used,
        }
    return port
