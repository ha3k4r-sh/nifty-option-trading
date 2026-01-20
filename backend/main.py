"""
Nifty Option Trading - FastAPI Backend
Modern NIFTY options trading application with smart caching, authentication, and real-time updates.
"""

import time
import secrets
import traceback
from datetime import datetime, timedelta
from itertools import accumulate
from fastapi import FastAPI, HTTPException, BackgroundTasks, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from typing import Optional, List, Dict
import os

from logger import setup_logger
from config import (
    LOT_SIZE, STRIKE_INTERVAL, load_credentials, save_credentials,
    get_ist_time, runtime_config
)
from dhan_service import dhan_service, DhanService
from security_cache import security_cache
from trade_history import live_trade_history, mock_trade_history

logger = setup_logger(__name__)

app = FastAPI(
    title="Nifty Option Trading",
    description="Smart NIFTY Options Trading Dashboard",
    version="2.0.0"
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== Authentication ====================

# Admin credentials (stored in memory, can be changed at runtime)
ADMIN_CREDENTIALS = {"username": "admin", "password": "admin"}

# In-memory session storage
active_sessions: Dict[str, datetime] = {}
SESSION_DURATION = timedelta(hours=24)


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    status: str
    token: Optional[str] = None
    message: str


async def require_auth(authorization: str = Header(None, alias="Authorization")):
    """Dependency to require valid authentication"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    # Extract token from "Bearer <token>" format
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    token = parts[1]

    # Check if token exists and is not expired
    if token not in active_sessions:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    if datetime.now() > active_sessions[token]:
        del active_sessions[token]
        raise HTTPException(status_code=401, detail="Session expired")

    return token


@app.post("/api/auth/login")
async def login(request: LoginRequest):
    """Authenticate user and return session token"""
    if (request.username == ADMIN_CREDENTIALS["username"] and
            request.password == ADMIN_CREDENTIALS["password"]):
        # Generate session token
        token = secrets.token_urlsafe(32)
        active_sessions[token] = datetime.now() + SESSION_DURATION

        logger.info(f"User logged in: {request.username}")
        return {
            "status": "success",
            "token": token,
            "message": "Login successful"
        }

    logger.warning(f"Failed login attempt for user: {request.username}")
    raise HTTPException(status_code=401, detail="Invalid credentials")


@app.post("/api/auth/logout")
async def logout(token: str = Depends(require_auth)):
    """Invalidate session"""
    if token in active_sessions:
        del active_sessions[token]
    logger.info("User logged out")
    return {"status": "success", "message": "Logged out"}


@app.get("/api/auth/check")
async def check_auth(token: str = Depends(require_auth)):
    """Verify session is valid"""
    return {"status": "valid", "message": "Session is valid", "username": ADMIN_CREDENTIALS["username"]}


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


@app.post("/api/auth/change-password")
async def change_password(request: PasswordChangeRequest, token: str = Depends(require_auth)):
    """Change admin password"""
    if request.current_password != ADMIN_CREDENTIALS["password"]:
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    if len(request.new_password) < 4:
        raise HTTPException(status_code=400, detail="New password must be at least 4 characters")

    ADMIN_CREDENTIALS["password"] = request.new_password
    logger.info("Password changed successfully")
    return {"status": "success", "message": "Password changed successfully"}


# ==================== Mock Mode ====================

class MockModeRequest(BaseModel):
    enabled: bool


@app.get("/api/config/mock-mode")
async def get_mock_mode():
    """Get current mock mode status"""
    return {"mock_mode": runtime_config.mock_mode}


@app.post("/api/config/mock-mode")
async def set_mock_mode(request: MockModeRequest):
    """Toggle mock mode"""
    runtime_config.mock_mode = request.enabled
    logger.info(f"Mock mode {'enabled' if request.enabled else 'disabled'}")
    return {"status": "success", "mock_mode": runtime_config.mock_mode}


# ==================== Request/Response Models ====================

class OrderRequest(BaseModel):
    strike: int
    option_type: str  # CE or PE
    quantity: int
    side: str  # BUY or SELL
    expiry: str = "current"  # current, next, monthly
    order_type: str = "MARKET"  # MARKET or LIMIT
    limit_price: Optional[float] = None  # Required for LIMIT orders


class PositionUpdate(BaseModel):
    security_id: str
    current_ltp: float


class ExitRequest(BaseModel):
    security_id: str
    symbol: str
    qty: int
    product_type: str = "MARGIN"


# ==================== Helper Functions ====================

def get_trade_history():
    """Get appropriate trade history based on mock mode"""
    return mock_trade_history if runtime_config.mock_mode else live_trade_history


# ==================== API Endpoints ====================

@app.get("/")
async def root():
    """Health check and redirect to login if not configured"""
    creds = load_credentials()
    has_creds = bool(creds.get("client_id") and creds.get("access_token"))
    return {
        "status": "ok",
        "app": "Nifty Option Trading",
        "configured": has_creds,
        "server_time_ist": get_ist_time()
    }


@app.get("/login")
async def login_page():
    """Serve login page"""
    return FileResponse("static/login.html")


# ==================== Settings ====================

class SettingsRequest(BaseModel):
    client_id: str
    access_token: str


@app.get("/settings")
async def settings_page():
    """Serve settings page"""
    return FileResponse("static/settings.html")


@app.get("/api/settings")
async def get_settings():
    """Get current settings (masked)"""
    creds = load_credentials()
    client_id = creds.get("client_id", "")
    token = creds.get("access_token", "")

    # Mask the token for display
    masked_token = ""
    if token:
        masked_token = token[:20] + "..." + token[-10:] if len(token) > 30 else "****"

    return {
        "client_id": client_id,
        "access_token_masked": masked_token,
        "configured": bool(client_id and token)
    }


@app.post("/api/settings")
async def save_settings(settings: SettingsRequest):
    """Save new credentials and reinitialize"""
    global dhan_service

    try:
        # Save to file
        save_credentials(settings.client_id, settings.access_token)

        # Reinitialize dhan_service with new credentials
        from dhan_service import DhanService
        dhan_service = DhanService()

        # Test connection
        try:
            funds = dhan_service.get_funds()
            return {
                "status": "success",
                "message": f"Connected! Balance: {funds:,.2f}"
            }
        except Exception as e:
            return {
                "status": "warning",
                "message": f"Saved but connection test failed: {str(e)}"
            }

    except Exception as e:
        logger.error(f"Settings save error: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/api/market")
async def get_market_data():
    """
    Get current market data: spot price, funds, expiry info.
    Called on initial load and periodically for updates.
    """
    try:
        spot = dhan_service.get_spot_price()
        funds = dhan_service.get_funds()
        expiry_info = security_cache.get_expiry_info()
        atm_strike = security_cache.get_atm_strike(spot)

        return {
            "spot_price": spot,
            "funds": funds,
            "atm_strike": atm_strike,
            "expiry": expiry_info,
            "lot_size": LOT_SIZE,
            "strike_interval": STRIKE_INTERVAL,
            "server_time_ist": get_ist_time(),
            "mock_mode": runtime_config.mock_mode
        }
    except Exception as e:
        logger.error(f"Market data error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/balance")
async def get_balance():
    """Get just the balance - fresh fetch, no cache"""
    try:
        if not dhan_service.dhan:
            return {"funds": 0, "error": "Not configured"}

        # Direct API call to get fresh balance
        resp = dhan_service.dhan.get_fund_limits()
        logger.info(f"Balance API response: {resp}")

        if resp.get('status') == 'success':
            data = resp.get('data', {})
            # Use availabelBalance (note: Dhan API has typo - "availabel" not "available")
            for key in ['availabelBalance', 'availableBalance', 'availFinanceLimit', 'availObjLimit']:
                if key in data:
                    val = float(data[key])
                    if val > 0:
                        logger.info(f"Balance found: {key} = {val}")
                        return {"funds": val, "key": key}

        logger.warning(f"No balance found in response")
        return {"funds": 0, "error": "No balance found"}
    except Exception as e:
        logger.error(f"Balance error: {e}")
        return {"funds": 0, "error": str(e)}


@app.get("/api/options/{strike}")
async def get_option_pair(strike: int, expiry: str = "current"):
    """Get CE and PE data for a specific strike."""
    try:
        ce_data = dhan_service.get_option_data(strike, "CE", expiry)
        pe_data = dhan_service.get_option_data(strike, "PE", expiry)

        return {
            "strike": strike,
            "expiry": expiry,
            "call": ce_data,
            "put": pe_data
        }
    except Exception as e:
        logger.error(f"Option data error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/option/ltp")
async def get_option_ltp(strike: int, option_type: str, expiry: str = "current"):
    """Get LTP for a single option - called when user selects an option"""
    try:
        data = dhan_service.get_option_data(strike, option_type, expiry)
        if data:
            return {"status": "success", "ltp": data.get('ltp', 0), "data": data}
        return {"status": "failure", "message": "Option not found"}
    except Exception as e:
        logger.error(f"LTP fetch error: {e}")
        return {"status": "failure", "message": str(e)}


@app.get("/api/options/batch/strikes")
async def get_batch_strikes(strikes: str, expiry: str = "current"):
    """
    Get CE and PE data for multiple strikes in one call.
    strikes: comma-separated list of strike prices (e.g., "25400,25450,25500")
    """
    try:
        strike_list = [int(s.strip()) for s in strikes.split(",") if s.strip()]
        data = dhan_service.get_multiple_strikes_data(strike_list, expiry)
        return {"data": data, "expiry": expiry}
    except Exception as e:
        logger.error(f"Batch strikes error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/options/ltp/batch")
async def get_batch_ltp(security_ids: str):
    """
    Get LTP for multiple securities in one call.
    security_ids: comma-separated list of security IDs
    """
    try:
        ids = [s.strip() for s in security_ids.split(",") if s.strip()]
        quotes = dhan_service.get_option_ltp_batch(ids)
        return {"quotes": quotes}
    except Exception as e:
        logger.error(f"Batch LTP error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/strikes")
async def get_available_strikes(expiry: str = "current", around: Optional[int] = None, count: int = 7):
    """
    Get available strikes around ATM or a specific strike.
    Returns list of strike prices.
    """
    try:
        all_strikes = security_cache.get_available_strikes(expiry)

        if not all_strikes:
            return {"strikes": [], "atm": 0}

        # Get center strike
        if around:
            center = around
        else:
            spot = dhan_service.get_spot_price()
            center = security_cache.get_atm_strike(spot)

        # Find strikes around center
        half = count // 2
        center_idx = min(range(len(all_strikes)), key=lambda i: abs(all_strikes[i] - center))

        start_idx = max(0, center_idx - half)
        end_idx = min(len(all_strikes), center_idx + half + 1)

        selected = all_strikes[start_idx:end_idx]

        return {
            "strikes": selected,
            "atm": center,
            "total_available": len(all_strikes)
        }
    except Exception as e:
        logger.error(f"Strikes error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/order")
async def place_order(order: OrderRequest):
    """Place a buy or sell order (supports MARKET and LIMIT)"""
    try:
        # Validate limit order has price
        if order.order_type == "LIMIT" and not order.limit_price:
            return {"status": "failure", "message": "Limit price required for LIMIT orders"}

        # Get security ID first (needed for both mock and live)
        sec_id = security_cache.get_security_id(order.strike, order.option_type, order.expiry)
        if not sec_id:
            return {"status": "failure", "message": f"Security ID not found for NIFTY {order.strike} {order.option_type}"}

        contract = security_cache.get_contract(sec_id)
        symbol = contract.get('trading_symbol', f"NIFTY {order.strike} {order.option_type}") if contract else f"NIFTY {order.strike} {order.option_type}"

        trade_hist = get_trade_history()

        # Mock mode - simulate order
        if runtime_config.mock_mode:
            mock_order_id = f"MOCK_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"

            # Get current LTP for mock entry price
            option_data = dhan_service.get_option_data(order.strike, order.option_type, order.expiry)
            mock_entry_price = option_data.get('ltp', 0) if option_data else 0

            # For limit orders, use the limit price if it's better
            if order.order_type == "LIMIT" and order.limit_price:
                if order.side == "BUY":
                    mock_entry_price = min(mock_entry_price, order.limit_price) if mock_entry_price > 0 else order.limit_price
                else:
                    mock_entry_price = max(mock_entry_price, order.limit_price) if mock_entry_price > 0 else order.limit_price

            trade_hist.add_trade(
                symbol=symbol,
                strike=order.strike,
                option_type=order.option_type,
                side=order.side,
                quantity=order.quantity,
                price=mock_entry_price,
                order_id=mock_order_id,
                expiry=order.expiry,
                security_id=str(sec_id),
                order_type=order.order_type,
                limit_price=order.limit_price,
                is_mock=True
            )

            logger.info(f"[MOCK] Order placed: {order.side} {order.quantity} {symbol} @ {mock_entry_price}")
            return {
                "status": "success",
                "order_id": mock_order_id,
                "message": f"[MOCK] Order placed: {order.side} {order.quantity} NIFTY {order.strike} {order.option_type}",
                "mock": True,
                "entry_price": mock_entry_price
            }

        # Live order
        result = dhan_service.place_order(
            strike=order.strike,
            option_type=order.option_type,
            quantity=order.quantity,
            side=order.side,
            expiry=order.expiry,
            order_type=order.order_type,
            limit_price=order.limit_price or 0,
            product_type="MARGIN"
        )

        # Record trade if successful
        if result.get('status') == 'success':
            # Wait briefly for order to fill
            time.sleep(0.5)

            # Get actual fill price from positions (Dhan's averagePrice)
            actual_entry_price = 0
            try:
                positions = dhan_service.get_positions()
                for pos in positions:
                    if str(pos.get('security_id')) == str(sec_id):
                        actual_entry_price = pos.get('entry_price', 0)
                        break
            except Exception as e:
                logger.warning(f"Could not fetch position for entry price: {e}")

            # Fallback to LTP if position not found (order may not be filled yet)
            if actual_entry_price == 0:
                option_data = dhan_service.get_option_data(order.strike, order.option_type, order.expiry)
                actual_entry_price = option_data.get('ltp', 0) if option_data else 0

            trade_hist.add_trade(
                symbol=symbol,
                strike=order.strike,
                option_type=order.option_type,
                side=order.side,
                quantity=order.quantity,
                price=actual_entry_price,
                order_id=result.get('order_id', ''),
                expiry=order.expiry,
                security_id=str(sec_id),
                order_type=order.order_type,
                limit_price=order.limit_price,
                is_mock=False
            )

            result['entry_price'] = actual_entry_price

        return result

    except Exception as e:
        logger.error(f"Order error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/exit")
async def exit_position(req: ExitRequest):
    """Exit an existing position using security_id directly"""
    try:
        trade_hist = get_trade_history()

        # Mock mode - simulate exit
        if runtime_config.mock_mode:
            mock_order_id = f"MOCK_EXIT_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"

            # Get current LTP for exit price
            ltp_data = dhan_service.get_option_ltp({'NSE_FNO': [int(req.security_id)]})
            exit_price = ltp_data.get(str(req.security_id), 0)

            # Close trade in history
            trade_hist.close_trade_by_security(req.security_id, exit_price, mock_order_id)

            # Record exit trade
            trade_hist.add_trade(
                symbol=req.symbol,
                strike=0,
                option_type='',
                side='SELL' if req.qty > 0 else 'BUY',
                quantity=abs(req.qty),
                price=exit_price,
                order_id=mock_order_id,
                expiry='',
                security_id=req.security_id,
                is_mock=True
            )

            logger.info(f"[MOCK] Position exited: {req.symbol} @ {exit_price}")
            return {
                "status": "success",
                "order_id": mock_order_id,
                "message": f"[MOCK] Position exited: {req.symbol}",
                "mock": True,
                "exit_price": exit_price
            }

        # Live exit
        position = {
            'security_id': req.security_id,
            'symbol': req.symbol,
            'qty': req.qty,
            'product_type': req.product_type
        }

        result = dhan_service.exit_position(position)

        if result.get('status') == 'success':
            # Get exit price
            ltp_data = dhan_service.get_option_ltp({'NSE_FNO': [int(req.security_id)]})
            exit_price = ltp_data.get(str(req.security_id), 0)

            # Close trade in history
            trade_hist.close_trade_by_security(req.security_id, exit_price, result.get('order_id', ''))

            # Record exit trade
            trade_hist.add_trade(
                symbol=req.symbol,
                strike=0,
                option_type='',
                side='SELL' if req.qty > 0 else 'BUY',
                quantity=abs(req.qty),
                price=exit_price,
                order_id=result.get('order_id', ''),
                expiry='',
                security_id=req.security_id,
                is_mock=False
            )

            result['exit_price'] = exit_price

        return result

    except Exception as e:
        logger.error(f"Exit error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/positions")
async def get_positions():
    """Get current open positions"""
    try:
        # For mock mode, return positions from trade history
        if runtime_config.mock_mode:
            mock_positions = mock_trade_history.get_open_positions()

            # Fetch current LTPs for P/L calculation
            if mock_positions:
                sec_ids = [int(p['security_id']) for p in mock_positions if p.get('security_id')]
                if sec_ids:
                    ltp_data = dhan_service.get_option_ltp({'NSE_FNO': sec_ids})

                    for pos in mock_positions:
                        sid = str(pos.get('security_id', ''))
                        ltp = ltp_data.get(sid, pos['entry_price'])
                        pos['current_ltp'] = ltp

                        entry = pos['entry_price']
                        qty = pos['qty']

                        if qty > 0:
                            pos['pnl'] = (ltp - entry) * qty
                        else:
                            pos['pnl'] = (entry - ltp) * abs(qty)

                        pos['pnl_percent'] = (pos['pnl'] / (entry * abs(qty)) * 100) if entry * qty != 0 else 0

            return {"positions": mock_positions, "mock": True}

        # Live positions from Dhan
        positions = dhan_service.get_positions()
        return {"positions": positions, "mock": False}

    except Exception as e:
        logger.error(f"Positions error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trades")
async def get_trades(mode: str = "current", limit: int = 50):
    """
    Get trade history
    mode: 'live', 'mock', 'current' (based on mock_mode), or 'all'
    """
    try:
        if mode == "live":
            trades = live_trade_history.get_all_trades(limit)
            analytics = live_trade_history.get_analytics()
        elif mode == "mock":
            trades = mock_trade_history.get_all_trades(limit)
            analytics = mock_trade_history.get_analytics()
        elif mode == "all":
            live_trades = live_trade_history.get_all_trades(limit)
            mock_trades = mock_trade_history.get_all_trades(limit)
            trades = sorted(live_trades + mock_trades, key=lambda t: t['timestamp'], reverse=True)[:limit]
            # Combined analytics
            live_analytics = live_trade_history.get_analytics()
            mock_analytics = mock_trade_history.get_analytics()
            analytics = {
                'live': live_analytics,
                'mock': mock_analytics
            }
        else:  # current - based on mock_mode
            trade_hist = get_trade_history()
            trades = trade_hist.get_all_trades(limit)
            analytics = trade_hist.get_analytics()

        return {
            "trades": trades,
            "analytics": analytics,
            "mode": mode if mode != "current" else ("mock" if runtime_config.mock_mode else "live")
        }
    except Exception as e:
        logger.error(f"Trades error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trades/live")
async def get_live_trades(limit: int = 50):
    """Get live trades only"""
    try:
        trades = live_trade_history.get_all_trades(limit)
        analytics = live_trade_history.get_analytics()
        return {"trades": trades, "analytics": analytics, "mode": "live"}
    except Exception as e:
        logger.error(f"Live trades error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trades/mock")
async def get_mock_trades(limit: int = 50):
    """Get mock trades only"""
    try:
        trades = mock_trade_history.get_all_trades(limit)
        analytics = mock_trade_history.get_analytics()
        return {"trades": trades, "analytics": analytics, "mode": "mock"}
    except Exception as e:
        logger.error(f"Mock trades error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/analytics")
async def get_analytics(mode: str = "current"):
    """Get P/L analytics summary"""
    try:
        if mode == "live":
            return live_trade_history.get_analytics()
        elif mode == "mock":
            return mock_trade_history.get_analytics()
        elif mode == "all":
            return {
                "live": live_trade_history.get_analytics(),
                "mock": mock_trade_history.get_analytics()
            }
        else:
            return get_trade_history().get_analytics()
    except Exception as e:
        logger.error(f"Analytics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/analytics/chart")
async def get_chart_data(mode: str = "current", period: str = "week"):
    """Get P/L data formatted for charting"""
    try:
        if mode == "live":
            trade_hist = live_trade_history
        elif mode == "mock":
            trade_hist = mock_trade_history
        else:
            trade_hist = get_trade_history()

        closed_trades = trade_hist.get_closed_trades()

        # Group by date
        daily_pnl = {}
        for trade in closed_trades:
            trade_date = trade.timestamp[:10]  # YYYY-MM-DD
            daily_pnl[trade_date] = daily_pnl.get(trade_date, 0) + (trade.pnl or 0)

        # Sort by date
        sorted_dates = sorted(daily_pnl.keys())
        sorted_pnl = [daily_pnl[d] for d in sorted_dates]

        # Calculate cumulative P/L
        cumulative = list(accumulate(sorted_pnl))

        return {
            "labels": sorted_dates,
            "daily_pnl": sorted_pnl,
            "cumulative_pnl": cumulative,
            "mode": mode if mode != "current" else ("mock" if runtime_config.mock_mode else "live")
        }
    except Exception as e:
        logger.error(f"Chart data error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/cache/refresh")
async def refresh_cache(background_tasks: BackgroundTasks):
    """Force refresh the security cache"""
    try:
        background_tasks.add_task(security_cache.force_refresh)
        return {"status": "refresh_started", "message": "Cache refresh initiated in background"}
    except Exception as e:
        logger.error(f"Cache refresh error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/cache/status")
async def cache_status():
    """Get detailed cache status information"""
    try:
        expiry = security_cache.get_expiry_info()
        current_strikes = security_cache.get_available_strikes("current")
        next_strikes = security_cache.get_available_strikes("next")
        monthly_strikes = security_cache.get_available_strikes("monthly")

        # Get sample strikes around ATM
        spot = dhan_service.get_spot_price()
        atm = security_cache.get_atm_strike(spot)
        nearby_current = [s for s in current_strikes if abs(s - atm) <= 500]

        return {
            "expiry_info": expiry,
            "spot_price": spot,
            "atm_strike": atm,
            "current_week_strikes": len(current_strikes),
            "next_week_strikes": len(next_strikes),
            "monthly_strikes": len(monthly_strikes),
            "nearby_strikes_current": nearby_current[:20],
            "cache_file": security_cache.cache_path,
            "cache_exists": os.path.exists(security_cache.cache_path)
        }
    except Exception as e:
        logger.error(f"Cache status error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Static Files (Frontend) ====================

# Mount static files for production
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/app")
    async def serve_app():
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))


# ==================== Startup ====================

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    logger.info("=" * 50)
    logger.info("Nifty Option Trading Starting...")
    logger.info("=" * 50)

    # Log cache status
    expiry = security_cache.get_expiry_info()
    logger.info(f"Current Expiry: {expiry.get('current')}")
    logger.info(f"Next Expiry: {expiry.get('next')}")
    logger.info(f"Monthly Expiry: {expiry.get('monthly')}")

    strikes = security_cache.get_available_strikes("current")
    logger.info(f"Available strikes for current week: {len(strikes)}")

    logger.info("=" * 50)
    logger.info("Server ready!")
    logger.info(f"Server time (IST): {get_ist_time()}")
    logger.info("=" * 50)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
