import os, math, time
from decimal import Decimal, ROUND_DOWN
from binance.client import Client
from dotenv import load_dotenv
from src.utils.logger import setup_logger

load_dotenv()
logger = setup_logger()

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

def _price(symbol: str) -> float:
    return float(bn_client.get_symbol_ticker(symbol=symbol)["price"])

# === EXECUTION ===
def place_binance_order(
    symbol: str,
    operation: str,          # open_long | close_long | open_short | close_short | hold
    quantity: float,
    isolated: bool = False,
):
    symbol = to_binance_symbol(symbol)
    qty = adjust_quantity_margin(symbol, quantity)

    if operation == "hold":
        logger.info(f"[SKIP] {symbol} HOLD – no action.")
        return (f"[SKIP] {symbol} HOLD – no action.")
    if qty <= 0:
        logger.warning(f"[SKIP] {symbol} {operation.upper()} – qty too low.")
        return (f"[SKIP] {symbol} {operation.upper()} – qty too low.")

    op_map = {
        "open_long":  ("BUY",  "MARGIN_BUY"),
        "close_long": ("SELL", "AUTO_REPAY"),
        "open_short": ("SELL", "MARGIN_BUY"),
        "close_short":("BUY",  "AUTO_REPAY"),
    }
    if operation not in op_map:
        logger.error(f"[❓] Unknown operation '{operation}' for {symbol}.")
        return (f"[❓] Unknown operation '{operation}' for {symbol}.")

    side, effect = op_map[operation]
    try:
        res = bn_client.create_margin_order(
            symbol=symbol,
            side=side,
            type="MARKET",
            quantity=str(qty),
            sideEffectType=effect,
            isIsolated="TRUE" if isolated else "FALSE",
        )
        logger.info(f"[✅] {operation.upper()} {symbol} | Qty {qty} | ID {res.get('orderId','N/A')}")
        return res
    except Exception as e:
        logger.error(f"[❌] Margin execution error: {e}")

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
# === PORTFOLIO ===


def get_binance_margin_positions():
    """Return live margin positions (filled and still open)."""
    pos = []
    try:
        acc = bn_client.get_margin_account()

        for a in acc["userAssets"]:
            asset = a["asset"]
            if asset == "USDC":
                continue

            free = float(a["free"])
            borrowed = float(a["borrowed"])
            if free == borrowed == 0:
                continue

            symbol = f"{asset}USDC"

            long_qty  = max(0.0, free - borrowed)
            short_qty = max(0.0, borrowed - free)

            if long_qty:
                cb = _cost_basis(symbol, long_qty, True)
                pos.append(
                    {
                        "symbol": symbol,
                        "side": "long",
                        "quantity": long_qty,
                        "price": cb,
                    }
                )

            if short_qty:
                cb = _cost_basis(symbol, short_qty, False)
                pos.append(
                    {
                        "symbol": symbol,
                        "side": "short",
                        "quantity": short_qty,
                        "price": cb,
                    }
                )

        if not pos:
            logger.debug("[ℹ️] No active margin positions found.")
        return pos

    except Exception as e:
        logger.error(f"[❌] Margin position retrieval error: {e}")
        return pos


def build_portfolio_from_binance_assets(settings):
    """
    Retourne :
      {
        "available_USDC": float,          # cash libre
        "total_margin_used": float,       # valeur des shorts ouverts
        "available_margin_USDC": float, # valeur USDC encore shortable
        "available_sell": {sym: qty},     # units shortables par ticker
        "positions": {...}
      }
    """
    margin_req = getattr(settings, "margin_requirement", 0.5)  # 50 % par défaut
    tickers = set(settings.signals.tickers)

    port = {
        "available_USDC": 0.0,
        "available_margin_USDC": 0.0,
        "total_margin_used": 0.0,
        "available_sell": {},
        "positions": {},
    }

    # --- Cash USDC ------------------------------------------------------
    try:
        acc = bn_client.get_margin_account()
        usdc = next((a for a in acc["userAssets"] if a["asset"] == "USDC"), {"free": "0"})
        port["available_USDC"] = float(usdc["free"])
    except Exception as e:
        logger.error(f"[❌] USDC fetch error: {e}")

    # --- Positions & margin used --------------------------------
    for p in get_binance_margin_positions():
        if p["symbol"] not in tickers:
            continue
        logger.debug(f"[ℹ️] Processing position: {p}")

        sym, qty, side, entry = p["symbol"], p["quantity"], p["side"], p["price"]
        price_now = _price(sym)
        pnl = (price_now - entry) * qty if side == "long" else (entry - price_now) * qty

        port["positions"][sym] = {
            "side": side,
            "quantity": qty,
            "entry": entry,
            "current": price_now,
            "unrealized_pnl": pnl,
        }

    # --- Available margin -------------------------------
    margin_summary = margin_summary_usdc(bn_client)
    logger.debug(f"[ℹ️] Margin summary: {margin_summary}")
    logger.debug(f"[ℹ️] Available USDC: {port['available_USDC']:.2f} USDC")
    
    avail_margin = max(
        0.0, (margin_summary["equity"] / margin_req)
    )
    port["available_margin_USDC"] = avail_margin - margin_summary["equity"]

    # --- Available sell quantity / ticker ---------------------------
    for sym in tickers:
        price_now = _price(sym)
        port["available_sell"][sym] = 0.0 if price_now == 0 else avail_margin / price_now

    return port

def margin_summary_usdc(client: Client) -> dict[str, float]:
    acc = client.get_margin_account()
    btc_price = Decimal(client.get_symbol_ticker(symbol="BTCUSDC")["price"])
    assets  = Decimal(acc["totalAssetOfBtc"])     * btc_price
    debt    = Decimal(acc["totalLiabilityOfBtc"]) * btc_price
    equity  = Decimal(acc["totalNetAssetOfBtc"])  * btc_price
    return {"assets": float(assets), "debt": float(debt), "equity": float(equity)}
