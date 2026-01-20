"""
Trade History Manager
Persists trade records and provides P/L analytics.
Supports separate storage for live and mock trades.
"""

import os
import json
from datetime import datetime, date
from typing import List, Optional, Dict
from dataclasses import dataclass, asdict, field

from logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class Trade:
    id: str
    timestamp: str
    symbol: str
    strike: int
    option_type: str
    side: str  # BUY or SELL
    quantity: int
    price: float
    order_id: str
    expiry: str
    security_id: str = ""
    order_type: str = "MARKET"  # MARKET or LIMIT
    limit_price: Optional[float] = None
    is_mock: bool = False
    # Filled on exit
    exit_price: Optional[float] = None
    exit_time: Optional[str] = None
    pnl: Optional[float] = None
    status: str = "OPEN"  # OPEN, CLOSED, CANCELLED


class TradeHistory:
    """
    Trade history manager with persistence.
    Supports separate files for live and mock trades.

    Features:
    - Auto-save to JSON
    - P/L calculations
    - Daily/overall analytics
    - Open positions tracking
    """

    def __init__(self, mode: str = "live"):
        """
        Initialize trade history.

        Args:
            mode: "live" or "mock" - determines storage file
        """
        self.mode = mode
        self.trades_file = f"data/{mode}_trades.json"
        self.trades: List[Trade] = []
        self._load()

    def _ensure_dir(self):
        os.makedirs(os.path.dirname(self.trades_file), exist_ok=True)

    def _load(self):
        """Load trades from JSON file"""
        self._ensure_dir()

        if os.path.exists(self.trades_file):
            try:
                with open(self.trades_file, 'r') as f:
                    data = json.load(f)

                self.trades = []
                for t in data.get('trades', []):
                    # Handle backward compatibility - add new fields if missing
                    if 'order_type' not in t:
                        t['order_type'] = 'MARKET'
                    if 'limit_price' not in t:
                        t['limit_price'] = None
                    if 'is_mock' not in t:
                        t['is_mock'] = self.mode == "mock"
                    self.trades.append(Trade(**t))

                logger.info(f"Loaded {len(self.trades)} {self.mode} trades from history")

            except Exception as e:
                logger.error(f"Failed to load {self.mode} trades: {e}")
                self.trades = []
        else:
            self.trades = []
            logger.info(f"No existing {self.mode} trades file found, starting fresh")

    def _save(self):
        """Save trades to JSON file"""
        self._ensure_dir()

        try:
            data = {
                'last_updated': datetime.now().isoformat(),
                'mode': self.mode,
                'trades': [asdict(t) for t in self.trades]
            }

            with open(self.trades_file, 'w') as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            logger.error(f"Failed to save {self.mode} trades: {e}")

    def add_trade(
        self,
        symbol: str,
        strike: int,
        option_type: str,
        side: str,
        quantity: int,
        price: float,
        order_id: str,
        expiry: str,
        security_id: str = "",
        order_type: str = "MARKET",
        limit_price: Optional[float] = None,
        is_mock: bool = False
    ) -> Trade:
        """Record a new trade"""
        trade = Trade(
            id=f"T{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
            timestamp=datetime.now().isoformat(),
            symbol=symbol,
            strike=strike,
            option_type=option_type,
            side=side,
            quantity=quantity,
            price=price,
            order_id=order_id,
            expiry=expiry,
            security_id=security_id,
            order_type=order_type,
            limit_price=limit_price,
            is_mock=is_mock,
            status="OPEN" if side == "BUY" else "CLOSED"
        )

        self.trades.append(trade)
        self._save()

        logger.info(f"[{self.mode.upper()}] Trade recorded: {trade.id} - {side} {quantity} {symbol} @ {price}")
        return trade

    def close_trade(
        self,
        trade_id: str,
        exit_price: float,
        exit_order_id: str
    ) -> Optional[Trade]:
        """Close an open trade with exit details"""
        for trade in self.trades:
            if trade.id == trade_id and trade.status == "OPEN":
                trade.exit_price = exit_price
                trade.exit_time = datetime.now().isoformat()
                trade.pnl = (exit_price - trade.price) * trade.quantity
                trade.status = "CLOSED"

                self._save()
                logger.info(f"[{self.mode.upper()}] Trade closed: {trade_id} - P/L: {trade.pnl:.2f}")
                return trade

        return None

    def close_trade_by_security(
        self,
        security_id: str,
        exit_price: float,
        exit_order_id: str
    ) -> Optional[Trade]:
        """Close an open trade by security_id"""
        for trade in self.trades:
            if trade.security_id == security_id and trade.status == "OPEN" and trade.side == "BUY":
                trade.exit_price = exit_price
                trade.exit_time = datetime.now().isoformat()
                trade.pnl = (exit_price - trade.price) * trade.quantity
                trade.status = "CLOSED"

                self._save()
                logger.info(f"[{self.mode.upper()}] Trade closed by security: {trade.id} - P/L: {trade.pnl:.2f}")
                return trade

        return None

    def get_open_trades(self) -> List[Trade]:
        """Get all open trades"""
        return [t for t in self.trades if t.status == "OPEN"]

    def get_closed_trades(self) -> List[Trade]:
        """Get all closed trades"""
        return [t for t in self.trades if t.status == "CLOSED"]

    def get_today_trades(self) -> List[Trade]:
        """Get today's trades"""
        today = date.today().isoformat()
        return [t for t in self.trades if t.timestamp.startswith(today)]

    def get_all_trades(self, limit: int = 100) -> List[dict]:
        """Get all trades as dicts, most recent first"""
        sorted_trades = sorted(self.trades, key=lambda t: t.timestamp, reverse=True)
        return [asdict(t) for t in sorted_trades[:limit]]

    def get_open_positions(self) -> List[dict]:
        """
        Get open positions aggregated by security_id.
        Returns positions in format compatible with Dhan positions API.
        """
        positions = {}

        for trade in self.trades:
            if trade.status == "OPEN" and trade.side == "BUY" and trade.security_id:
                sid = trade.security_id
                if sid not in positions:
                    positions[sid] = {
                        'security_id': sid,
                        'symbol': trade.symbol,
                        'qty': 0,
                        'entry_price': 0,
                        'total_cost': 0,
                        'product_type': 'MARGIN'
                    }
                positions[sid]['qty'] += trade.quantity
                positions[sid]['total_cost'] += trade.price * trade.quantity

        # Calculate average entry price
        for pos in positions.values():
            if pos['qty'] > 0:
                pos['entry_price'] = pos['total_cost'] / pos['qty']
            del pos['total_cost']  # Remove temporary field

        return list(positions.values())

    def get_analytics(self) -> dict:
        """Get P/L analytics"""
        closed = self.get_closed_trades()
        today_trades = self.get_today_trades()
        today_closed = [t for t in today_trades if t.status == "CLOSED"]

        total_pnl = sum(t.pnl or 0 for t in closed)
        today_pnl = sum(t.pnl or 0 for t in today_closed)

        winners = [t for t in closed if (t.pnl or 0) > 0]
        losers = [t for t in closed if (t.pnl or 0) < 0]

        win_rate = len(winners) / len(closed) * 100 if closed else 0

        avg_win = sum(t.pnl or 0 for t in winners) / len(winners) if winners else 0
        avg_loss = sum(t.pnl or 0 for t in losers) / len(losers) if losers else 0

        return {
            'mode': self.mode,
            'total_trades': len(self.trades),
            'open_trades': len(self.get_open_trades()),
            'closed_trades': len(closed),
            'today_trades': len(today_trades),
            'total_pnl': total_pnl,
            'today_pnl': today_pnl,
            'win_rate': win_rate,
            'winners': len(winners),
            'losers': len(losers),
            'avg_win': avg_win,
            'avg_loss': avg_loss
        }

    def get_entry_price(self, symbol: str) -> Optional[float]:
        """Get last entry price for a symbol from local trades"""
        matching = [t for t in self.trades
                    if t.symbol == symbol and t.side == "BUY" and t.status == "OPEN"]
        if matching:
            matching.sort(key=lambda t: t.timestamp, reverse=True)
            return matching[0].price
        return None

    def get_entry_prices_map(self) -> Dict[str, float]:
        """Get map of security_id -> last entry price for all open trades"""
        result = {}
        open_trades = [t for t in self.trades if t.side == "BUY" and t.status == "OPEN"]
        for t in open_trades:
            if t.security_id:
                result[t.security_id] = t.price
            result[t.symbol] = t.price
            key = f"{t.strike}_{t.option_type}"
            result[key] = t.price
        return result


# Singleton instances for live and mock trades
live_trade_history = TradeHistory("live")
mock_trade_history = TradeHistory("mock")

# Backward compatibility alias
trade_history = live_trade_history
