import itertools
from datetime import datetime
from typing import List, Dict, Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from colorama import Fore, Style

from agent import Agent
from utils import Interval, QUANTITY_DECIMALS, format_backtest_row, print_backtest_results
from utils.binance_data_provider import BinanceDataProvider
import time


class Backtester:
    """LLM‑driven long/short back‑tester using the new portfolio format.

    Portfolio schema
    -----------------
    {
        "available_USDC": float,
        "margin_requirement": float,
        "margin_used": float,
        "positions": {
            "ETHUSDC": {
                "side": "long" | "short",
                "quantity": float,
                "entry": float,          # VWAP of the open position
                "current": float,        # updated each bar
                "unrealized_pnl": float  # (current-entry)*qty (sign flipped for shorts)
            },
            ...
        }
    }
    """

    def __init__(
        self,
        primary_interval: Interval,
        intervals: List[Interval],
        tickers: List[str],
        start_date: datetime,
        end_date: datetime,
        initial_capital: float,
        strategies: List[str],
        model_name: str = "gpt-4.1",
        model_provider: str = "OpenAI",
        initial_margin_requirement: float = 0.0,
        borrowed_USDC: float = 0.0,
        show_agent_graph: bool = False,
        show_reasoning: bool = False,
    ):
        self.primary_interval = primary_interval
        self.intervals = intervals
        self.borrowed_USDC = borrowed_USDC
        self.tickers = tickers
        self.start_date = start_date
        self.end_date = end_date
        self.margin_requirement = initial_margin_requirement
        self.initial_capital = initial_capital
        self.strategies = strategies
        self.model_name = model_name
        self.model_provider = model_provider
        self.show_agent_graph = show_agent_graph
        self.show_reasoning = show_reasoning

        self.binance_data_provider = BinanceDataProvider()
        self.klines: Dict[str, pd.DataFrame] = {}

        self.portfolio = {
            "available_USDC": initial_capital,
            "borrowed_USDC": borrowed_USDC,
            "equity": initial_capital,
            "available_margin_USDC": initial_capital / initial_margin_requirement,
            "available_margin_ETH": 0.0,
            "positions": {},
        }
        self.portfolio_values: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # trading helpers
    # ------------------------------------------------------------------

    def _ensure_position_node(self, symbol: str, side: str, quantity: float, entry: float):
        """Create an empty node if not present."""
        self.portfolio["positions"][symbol] = {
            "side": side,
            "quantity": quantity,
            "entry": entry,
            "current": entry,
            "unrealized_pnl": 0.0,
        }

    def _update_pnl(self, symbol: str, current_price: float):
        p = self.portfolio["positions"][symbol]
        if p["side"] == "long":
            pnl = (current_price - p["entry"]) * p["quantity"]
        else:
            pnl = (p["entry"] - current_price) * p["quantity"]
        p["current"] = current_price
        p["unrealized_pnl"] = pnl

    # main trade executor ------------------------------------------------
    def execute_trade(self, symbol: str, operation: str, quantity: float, current_price: float, prices: Dict[str, float] = None):
        """Executes a trade operation for the given symbol."""
        """If the quantity*price is higher than margin_requirement * available_USDC, it will not execute the trade and return an error."""
        
        
        FEE = 0.001
        if quantity <= 0.0 or operation == "hold":
            return 0.0
        quantity = round(float(quantity), QUANTITY_DECIMALS)

        positions = self.portfolio["positions"]
        pos = positions.get(symbol)
        
        margin_available = self.portfolio["available_USDC"] / self.margin_requirement
        
        print(f"Executing {operation} for {symbol}: quantity={quantity}, price={current_price}")

        # open long ------------------------------------------------------
        if operation == "open_long":
            
            cost = quantity * current_price * (1 + FEE)
            
            if cost > margin_available:
                raise ValueError(
                    f"Trade size exceeds margin requirement: {quantity*current_price} > {self.portfolio['available_USDC'] / self.margin_requirement}"
                )

            if not pos:
                self._ensure_position_node(symbol, "long", 0.0, current_price)
                pos = positions[symbol]
            # vwap update
            new_qty = pos["quantity"] + quantity
            pos["entry"] = (pos["entry"] * pos["quantity"] + current_price * quantity) / new_qty
            pos["quantity"] = new_qty
            
            if self.portfolio["available_USDC"] < cost: # if not enough cash, borrow
                
                borrowed = cost - self.portfolio["available_USDC"]
                self.portfolio["available_USDC"] = 0
                
                pos["borrowed_USDC"] = borrowed
                self.portfolio["borrowed_USDC"] += borrowed
                
                self.portfolio["equity"] = self.calculate_equity(current_price)
                
                self.portfolio["available_margin_USDC"] = (self.portfolio["equity"])/ self.margin_requirement
            
            else:   # if enough cash, use it            
                self.portfolio["available_USDC"] -= cost
                self.portfolio["equity"] = self.calculate_equity(current_price)
                self.portfolio["available_margin_USDC"] = (self.portfolio["equity"])/ self.margin_requirement
                
            self._update_pnl(symbol, current_price)
            
            return quantity

        # close long -----------------------------------------------------
        if operation == "close_long" and pos and pos["side"] == "long":
            
            sell_qty = quantity
            proceeds = sell_qty * current_price
            
            # Sell quantity
            pos["quantity"] -= sell_qty
            
            # If margin position exists, release margin
            if "borrowed_USDC" in pos:
                borrowed = pos["borrowed_USDC"]
                self.portfolio["borrowed_USDC"] -= borrowed
                
                self.portfolio["available_USDC"] += proceeds - borrowed
                
                if pos["quantity"] == 0:
                    positions.pop(symbol)
                
                self.portfolio["equity"] = self.calculate_equity(current_price)
                
                self.portfolio["available_margin_USDC"] = (self.portfolio["equity"])/ self.margin_requirement
                
            else:
                # Add remaining cash to available USDC
                self.portfolio["available_USDC"] += proceeds
                self.portfolio["available_margin_USDC"] = self.portfolio["available_USDC"]/ self.margin_requirement
                if pos["quantity"] == 0:
                    positions.pop(symbol)
                else:
                    self._update_pnl(symbol, current_price)
            return sell_qty

        # open short -----------------------------------------------------
        if operation == "open_short":
            proceeds = quantity * current_price
            
            if proceeds > margin_available:
                raise ValueError(
                    f"Trade size exceeds margin requirement: {quantity*current_price} > {margin_available}"
                )
                
            if not pos:
                self._ensure_position_node(symbol, "short", 0.0, current_price)
                pos = positions[symbol]
            # vwap update
            new_qty = pos["quantity"] + quantity
            pos["entry"] = (pos["entry"] * pos["quantity"] + current_price * quantity) / new_qty
            pos["quantity"] = new_qty
            pos["borrowed_USDC"] = proceeds  # borrowed USDC for margin
            
            # self.portfolio["available_USDC"] += proceeds  # proceeds credited
            
            self.portfolio["borrowed_USDC"] += proceeds  # borrowed USDC for margin
            
            self.portfolio["equity"] = self.calculate_equity(current_price)
            self.portfolio["available_margin_USDC"] = self.portfolio["equity"]/ self.margin_requirement
            self._update_pnl(symbol, current_price)
            time.sleep(1000)
            return quantity

        # close short ----------------------------------------------------
        if operation == "close_short" and pos and pos["side"] == "short":
            cover_cost = quantity * current_price

            pos["quantity"] -= quantity
            
            self.portfolio["available_USDC"] += cover_cost - pos["entry"] * quantity
            
            # borrowed
            self.portfolio["borrowed_USDC"] -= pos["borrowed_USDC"]
            
            if pos["quantity"] == 0:
                positions.pop(symbol)
            else:
                self._update_pnl(symbol, current_price)
            
            self.portfolio["equity"] = self.calculate_equity(current_price)
                
            self.portfolio["available_margin_USDC"] = (self.portfolio["equity"])/ self.margin_requirement

            return quantity

        return 0.0

    # ------------------------------------------------------------------
    # valuation helpers
    # ------------------------------------------------------------------
    
    def calculate_equity(self, price):
        """Calculate the equity value of the portfolio based on current prices."""
        equity = self.portfolio["available_USDC"]
        borrowed_USDC = self.portfolio.get("borrowed_USDC", 0.0)
        print(f"Calculating equity at price {price:.2f} with available_USDC: {self.portfolio['available_USDC']:.2f} and borrowed_USDC: {borrowed_USDC:.2f}")
        if borrowed_USDC > 0:
            equity -= borrowed_USDC
        for sym, pos in self.portfolio["positions"].items():
            if pos["side"] == "long":
                equity += pos["quantity"] * price
            else:
                equity += pos["quantity"]*pos["entry"] - pos["quantity"] * price + self.portfolio.get("borrowed_USDC", 0.0)
                print(f"Short position {sym} PnL: {(pos['entry'] - price) * pos['quantity']:.2f}")
        print (f"Equity calculated: {equity:.2f} (available_USDC: {self.portfolio['available_USDC']:.2f}, borrowed_USDC: {borrowed_USDC:.2f})")
        print (f"Positions: {self.portfolio['positions']}")

        return equity

    def calculate_portfolio_value(self, prices: Dict[str, float]):
        value = self.portfolio["available_USDC"]
        for sym, pos in self.portfolio["positions"].items():
            price = prices.get(sym)
            if price is None:
                continue
            self._update_pnl(sym, price)
            if pos["side"] == "long":
                value += pos["quantity"] * price
            else:
                value -= pos["quantity"] * price
        return value

    def _update_available_margin_eth(self, eth_price: float):
        if eth_price:
            self.portfolio["available_margin_ETH"] = (
                self.portfolio["available_USDC"] / (self.margin_requirement * eth_price)
            )
    # ------------------------------------------------------------------
    # data loaders
    # ------------------------------------------------------------------

    def prefetch_data(self):
        print("Fetching candles…")
        for sym in self.tickers:
            self.klines[sym] = self.binance_data_provider.get_historical_klines(
                symbol=sym,
                timeframe=self.primary_interval.value,
                start_date=self.start_date,
                end_date=self.end_date,
            )
        print("Done.")

    # ------------------------------------------------------------------
    # main backtest loop
    # ------------------------------------------------------------------

    def run_backtest(self):
        self.prefetch_data()
        base_df = self.klines[self.tickers[0]]
        if base_df.empty:
            raise ValueError("No data loaded")
        self.portfolio_values.append({"Date": base_df.loc[0, "open_time"], "Portfolio Value": self.initial_capital})

        metrics = {"sharpe_ratio": None, "sortino_ratio": None, "max_drawdown": None}
        table_rows = []

        for idx in range(len(base_df)):
            current_time = base_df.iloc[idx]["close_time"]
            prices = {sym: self.klines[sym].iloc[idx]["close"] for sym in self.tickers}
            
            self._update_available_margin_eth(prices.get("ETHUSDC"))

            # -----------------------------------------------------------
            # agent decision
            # -----------------------------------------------------------
            output = Agent.run(
                primary_interval=self.primary_interval,
                intervals=self.intervals,
                tickers=self.tickers,
                end_date=current_time,
                portfolio=self.portfolio,
                strategies=self.strategies,
                model_name=self.model_name,
                model_provider=self.model_provider,
                show_agent_graph=self.show_agent_graph,
                show_reasoning=self.show_reasoning,
            )
            decisions = output.get("decisions", {})
            analyst_signals = output.get("analyst_signals", {})

            executed = {}
            for sym in self.tickers:
                dec = decisions.get(sym, {"operation": "hold", "quantity": 0.0})
                executed[sym] = self.execute_trade(sym, dec.get("operation", "hold"), dec.get("quantity", 0.0), prices[sym])
                self.calculate_equity(prices[sym])  # update equity after each trade

            # -----------------------------------------------------------
            # valuation & exposures
            # -----------------------------------------------------------
            total_val = self.calculate_portfolio_value(prices)
            long_exp = sum(pos["quantity"] * prices[sym] for sym, pos in self.portfolio["positions"].items() if pos["side"] == "long")
            short_exp = sum(pos["quantity"] * prices[sym] for sym, pos in self.portfolio["positions"].items() if pos["side"] == "short")
            gross_exp = long_exp + short_exp
            net_exp = long_exp - short_exp
            ls_ratio = long_exp / short_exp if short_exp > 1e-9 else float("inf")

            self.portfolio_values.append({
                "Date": current_time,
                "Portfolio Value": total_val,
                "Long Exposure": long_exp,
                "Short Exposure": short_exp,
                "Gross Exposure": gross_exp,
                "Net Exposure": net_exp,
                "Long/Short Ratio": ls_ratio,
            })

            # -----------------------------------------------------------
            # table rows for printing
            # -----------------------------------------------------------
            daily_rows = []
            for sym in self.tickers:
                sigs = {a: s[sym] for a, s in analyst_signals.items() if sym in s}
                bull = len([s for s in sigs.values() if s.get("signal", "").lower() == "bullish"])
                bear = len([s for s in sigs.values() if s.get("signal", "").lower() == "bearish"])
                neut = len([s for s in sigs.values() if s.get("signal", "").lower() == "neutral"])

                pos = self.portfolio["positions"].get(sym)
                net_qty = pos["quantity"] * (1 if pos and pos["side"] == "long" else -1) if pos else 0.0
                net_val = net_qty * prices[sym]

                op = decisions.get(sym, {}).get("operation", "hold")
                qty_exec = executed.get(sym, 0.0)

                daily_rows.append(
                    format_backtest_row(
                        date=current_time,
                        ticker=sym,
                        action=op,
                        quantity=qty_exec,
                        price=prices[sym],
                        shares_owned=net_qty,
                        position_value=net_val,
                        bullish_count=bull,
                        bearish_count=bear,
                        neutral_count=neut,
                    )
                )

            # summary row
            port_return = (total_val / self.initial_capital - 1) * 100
            daily_rows.append(
                format_backtest_row(
                    date=current_time,
                    ticker="",
                    action="",
                    quantity=0.0,
                    price=0.0,
                    shares_owned=0.0,
                    position_value=0.0,
                    bullish_count=0,
                    bearish_count=0,
                    neutral_count=0,
                    is_summary=True,
                    total_value=total_val,
                    return_pct=port_return,
                    cash_balance=self.portfolio["available_USDC"],
                    total_position_value=total_val - self.portfolio["available_USDC"],
                    sharpe_ratio=metrics["sharpe_ratio"],
                    sortino_ratio=metrics["sortino_ratio"],
                    max_drawdown=metrics["max_drawdown"],
                )
            )

            table_rows.extend(daily_rows)
            print_backtest_results(table_rows)

            if len(self.portfolio_values) > 3:
                self._update_performance_metrics(metrics)

        self.performance_metrics = metrics
        return metrics

    # ------------------------------------------------------------------
    # metrics helpers
    # ------------------------------------------------------------------

    def _update_performance_metrics(self, metrics):
        df = pd.DataFrame(self.portfolio_values).set_index("Date")
        df["Daily Return"] = df["Portfolio Value"].pct_change()
        rets = df["Daily Return"].dropna()
        if len(rets) < 2:
            return
        rf_daily = 0.0434 / 365
        excess = rets - rf_daily
        mu, sigma = excess.mean(), excess.std()
        metrics["sharpe_ratio"] = np.sqrt(365) * mu / sigma if sigma > 1e-12 else 0.0
        neg = excess[excess < 0]
        if len(neg):
            down = neg.std()
            metrics["sortino_ratio"] = np.sqrt(365) * mu / down if down > 1e-12 else float("inf") if mu > 0 else 0
        else:
            metrics["sortino_ratio"] = float("inf") if mu > 0 else 0
        roll_max = df["Portfolio Value"].cummax()
        dd = (df["Portfolio Value"] - roll_max) / roll_max
        if len(dd):
            metrics["max_drawdown"] = dd.min() * 100
            metrics["max_drawdown_date"] = dd.idxmin().strftime("%Y-%m-%d") if dd.min() < 0 else None

    # ------------------------------------------------------------------
    # analysis
    # ------------------------------------------------------------------

    def analyze_performance(self):
        if not self.portfolio_values:
            print("Run backtest first")
            return pd.DataFrame()
        df = pd.DataFrame(self.portfolio_values).set_index("Date")
        if df.empty:
            return df
        final_val = df["Portfolio Value"].iloc[-1]
        tot_ret = (final_val - self.initial_capital) / self.initial_capital * 100
        print(f"PORTFOLIO PERFORMANCE SUMMARY:")
        print(f"Total Return: {Fore.GREEN if tot_ret >= 0 else Fore.RED}{tot_ret:.2f}%{Style.RESET_ALL}")
        plt.figure(figsize=(12, 6))
        plt.plot(df.index, df["Portfolio Value"], label="Equity")
        plt.title("Equity Curve")
        plt.ylabel("Portfolio Value ($)")
        plt.xlabel("Date")
        plt.grid(True)
        plt.legend()
        plt.show()
        df["Daily Return"] = df["Portfolio Value"].pct_change().fillna(0)
        rf = 0.0434 / 365
        mu, sigma = df["Daily Return"].mean(), df["Daily Return"].std()
        sharpe = np.sqrt(365) * (mu - rf) / sigma if sigma else 0
        print(f"Sharpe Ratio: {Fore.YELLOW}{sharpe:.2f}{Style.RESET_ALL}")
        mdd = self.performance_metrics.get("max_drawdown")
        mdd_date = self.performance_metrics.get("max_drawdown_date")
        if mdd_date:
            print(f"Maximum Drawdown: {Fore.RED}{abs(mdd):.2f}%{Style.RESET_ALL} (on {mdd_date})")
        else:
            print(f"Maximum Drawdown: {Fore.RED}{abs(mdd):.2f}%{Style.RESET_ALL}")
        wins = len(df[df["Daily Return"] > 0])
        days = max(len(df) - 1, 1)
        win_rate = wins / days * 100
        print(f"Win Rate: {Fore.GREEN}{win_rate:.2f}%{Style.RESET_ALL}")
        pos = df[df["Daily Return"] > 0]["Daily Return"].mean() or 0
        neg = abs(df[df["Daily Return"] < 0]["Daily Return"].mean()) or 0
        wl_ratio = pos / neg if neg else float("inf") if pos > 0 else 0
        print(f"Win/Loss Ratio: {Fore.GREEN}{wl_ratio:.2f}{Style.RESET_ALL}")
        bin_ret = (df["Daily Return"] > 0).astype(int)
        max_win_seq = max((len(list(g)) for k, g in itertools.groupby(bin_ret) if k == 1), default=0)
        max_loss_seq = max((len(list(g)) for k, g in itertools.groupby(bin_ret) if k == 0), default=0)
        print(f"Max Consecutive Wins: {Fore.GREEN}{max_win_seq}{Style.RESET_ALL}")
        print(f"Max Consecutive Losses: {Fore.RED}{max_loss_seq}{Style.RESET_ALL}")
        return df
