"""
Dhan API Service - Matching Original Working Code
Uses ticker_data for LTP, MARGIN product_type for Normal orders
Supports both MARKET and LIMIT orders
"""

import time
from typing import Dict, List, Optional
from dhanhq import dhanhq

from logger import setup_logger
from config import LOT_SIZE, INDEX_SECURITY_ID, load_credentials
from security_cache import security_cache

logger = setup_logger(__name__)


class DhanService:
    """Dhan API service - matches original working implementation exactly."""
    
    def __init__(self):
        # Load credentials fresh from file
        creds = load_credentials()
        client_id = creds.get("client_id", "")
        access_token = creds.get("access_token", "")
        
        if not client_id or not access_token:
            logger.warning("No credentials configured! Go to /settings to configure.")
            self.dhan = None
        else:
            self.dhan = dhanhq(client_id, access_token)
            logger.info(f"DhanService initialized for client: {client_id}")
        
        # Cache to protect against rate limiting
        self._spot_cache = {'value': 0.0, 'time': 0}
        self._funds_cache = {'value': 0.0, 'time': 0}
        self._ltp_cache = {}
        self._cache_ttl = 5  # 5 second cache - Dhan rate limits are strict
        
        # Global request throttle
        self._last_api_call = 0
        self._min_call_interval = 1.0  # Minimum 1 second between API calls
        
        # Initialize security cache if we have credentials
        if self.dhan:
            security_cache.initialize(self.dhan)
        logger.info("DhanService initialized")
    
    def _throttle(self):
        """Ensure minimum interval between API calls"""
        now = time.time()
        elapsed = now - self._last_api_call
        if elapsed < self._min_call_interval:
            time.sleep(self._min_call_interval - elapsed)
        self._last_api_call = time.time()
    
    def get_spot_price(self) -> float:
        """Get NIFTY 50 spot price - EXACT copy of original"""
        if not self.dhan:
            return 0.0
            
        now = time.time()
        if now - self._spot_cache['time'] < self._cache_ttl and self._spot_cache['value'] > 0:
            return self._spot_cache['value']
        
        try:
            self._throttle()  # Rate limit protection
            # Original: self.dhan.quote_data({'IDX_I': [13]})
            resp = self.dhan.quote_data({'IDX_I': [INDEX_SECURITY_ID]})
            
            if resp.get('status') == 'success':
                data = resp.get('data', {})
                
                # Original parsing logic
                if 'IDX_I' in data and str(INDEX_SECURITY_ID) in data['IDX_I']:
                    quote = data['IDX_I'][str(INDEX_SECURITY_ID)]
                    self._spot_cache['value'] = float(quote.get('last_price', 0.0))
                    self._spot_cache['time'] = now
                    return self._spot_cache['value']
                
                # Handle nested structure
                if 'data' in data:
                    inner = data['data']
                    if 'IDX_I' in inner and str(INDEX_SECURITY_ID) in inner['IDX_I']:
                        quote = inner['IDX_I'][str(INDEX_SECURITY_ID)]
                        self._spot_cache['value'] = float(quote.get('last_price', 0.0))
                        self._spot_cache['time'] = now
                        return self._spot_cache['value']
            
            logger.warning(f"Spot price fetch issue: {resp}")
            return self._spot_cache['value']
            
        except Exception as e:
            logger.error(f"Error fetching spot: {e}")
            return self._spot_cache['value']
    
    def get_funds(self) -> float:
        """Get available funds - EXACT copy of original"""
        if not self.dhan:
            return 0.0
            
        now = time.time()
        if now - self._funds_cache['time'] < self._cache_ttl and self._funds_cache['value'] > 0:
            return self._funds_cache['value']
        
        try:
            self._throttle()  # Rate limit protection
            resp = self.dhan.get_fund_limits()
            
            if resp.get('status') == 'success':
                data = resp.get('data', {})
                # Use availabelBalance first (note: Dhan API has typo)
                for key in ['availabelBalance', 'availableBalance', 'availFinanceLimit', 'availObjLimit']:
                    if key in data:
                        val = float(data[key])
                        if val > 0:
                            self._funds_cache['value'] = val
                            self._funds_cache['time'] = now
                            return val
            
            return self._funds_cache['value']
            
        except Exception as e:
            logger.error(f"Error fetching funds: {e}")
            return self._funds_cache['value']
    
    def get_option_ltp(self, security_ids: Dict[str, List[int]]) -> Dict[str, float]:
        """
        Get LTP using ticker_data - EXACT COPY OF ORIGINAL WORKING CODE
        
        Args:
            security_ids: {'NSE_FNO': [47613, 47614, ...]}
        Returns:
            {sec_id_str: ltp}
        """
        if not security_ids or not security_ids.get('NSE_FNO'):
            return {}
        
        now = time.time()
        result = {}
        ids_to_fetch = []
        
        # Check cache first
        for sid in security_ids.get('NSE_FNO', []):
            sid_str = str(sid)
            cached = self._ltp_cache.get(sid_str)
            if cached and now - cached.get('time', 0) < self._cache_ttl:
                result[sid_str] = cached['ltp']
            else:
                ids_to_fetch.append(int(sid))
        
        if not ids_to_fetch:
            return result
        
        try:
            logger.info(f"Requesting LTP for: {len(ids_to_fetch)} securities")
            
            self._throttle()  # Rate limit protection
            
            # ORIGINAL CODE USES ticker_data, NOT quote_data!
            resp = self.dhan.ticker_data({'NSE_FNO': ids_to_fetch})
            
            logger.debug(f"ticker_data response status: {resp.get('status')}")
            
            if resp.get('status') != 'success':
                # Rate limited - return cached values
                logger.warning(f"LTP fetch failed (likely rate limited), using cache")
                for sid in ids_to_fetch:
                    sid_str = str(sid)
                    if sid_str in self._ltp_cache:
                        result[sid_str] = self._ltp_cache[sid_str]['ltp']
                return result
            
            # Parse response - Original logic
            data = resp.get('data', {})
            
            # Handle the extra 'data' nesting
            if 'data' in data and isinstance(data['data'], dict):
                data = data['data']
            
            for segment, securities in data.items():
                if isinstance(securities, dict):
                    for sec_id, quote in securities.items():
                        if isinstance(quote, dict) and 'last_price' in quote:
                            ltp = float(quote['last_price'])
                            result[str(sec_id)] = ltp
                            self._ltp_cache[str(sec_id)] = {'ltp': ltp, 'time': now}
                            logger.debug(f"Got LTP for {sec_id}: {ltp}")
            
            logger.info(f"Final LTP result: {len(result)} prices fetched")
            return result
            
        except Exception as e:
            logger.error(f"Error fetching option LTP: {e}")
            import traceback
            traceback.print_exc()
            return result
    
    def get_option_data(self, strike: int, option_type: str, expiry: str = "current") -> Optional[dict]:
        """Get option contract info WITH LTP (single fetch on demand)"""
        sec_id = security_cache.get_security_id(strike, option_type, expiry)
        if not sec_id:
            return None
        
        contract = security_cache.get_contract(sec_id)
        if not contract:
            return None
        
        # Fetch LTP for this single option
        ltp_data = self.get_option_ltp({'NSE_FNO': [int(sec_id)]})
        ltp = ltp_data.get(str(sec_id), 0)
        
        return {
            **contract,
            'ltp': ltp
        }
    
    def get_multiple_strikes_data(self, strikes: List[int], expiry: str = "current") -> dict:
        """Get CE and PE contract info for multiple strikes - NO LTP fetch to avoid rate limits"""
        result = {}
        for strike in strikes:
            ce_id = security_cache.get_security_id(strike, 'CE', expiry)
            pe_id = security_cache.get_security_id(strike, 'PE', expiry)
            
            ce_contract = security_cache.get_contract(ce_id) if ce_id else None
            pe_contract = security_cache.get_contract(pe_id) if pe_id else None
            
            result[strike] = {
                'ce': ce_contract,
                'pe': pe_contract
            }
        
        return result
    
    def get_positions(self) -> List[dict]:
        """Get OPEN positions only (netQty != 0)"""
        try:
            self._throttle()  # Rate limit protection
            resp = self.dhan.get_positions()
            
            if resp.get('status') != 'success':
                logger.warning(f"Positions fetch failed: {resp}")
                return []
            
            positions = resp.get('data', [])
            result = []
            sec_ids = []
            
            for pos in positions:
                net_qty = int(pos.get('netQty', 0))
                symbol = pos.get('tradingSymbol', '')
                
                # ONLY open positions (netQty != 0)
                if net_qty != 0 and 'NIFTY' in symbol:
                    sec_id = str(pos.get('securityId', ''))
                    sec_ids.append(int(sec_id))
                    result.append({
                        'security_id': sec_id,
                        'symbol': symbol,
                        'qty': net_qty,
                        'entry_price': float(pos.get('averagePrice', 0)),
                        'product_type': pos.get('productType', 'MARGIN'),
                    })
            
            # Fetch current LTPs for P/L calculation
            if sec_ids:
                ltp_data = self.get_option_ltp({'NSE_FNO': sec_ids})
                
                for pos in result:
                    ltp = ltp_data.get(str(pos['security_id']), pos['entry_price'])
                    pos['current_ltp'] = ltp
                    
                    entry = pos['entry_price']
                    qty = pos['qty']
                    
                    if qty > 0:
                        pos['pnl'] = (ltp - entry) * qty
                    else:
                        pos['pnl'] = (entry - ltp) * abs(qty)
                    
                    pos['pnl_percent'] = (pos['pnl'] / (entry * abs(qty)) * 100) if entry * qty != 0 else 0
            
            return result
            
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return []
    
    def place_order(
        self,
        strike: int,
        option_type: str,
        quantity: int,
        side: str,
        expiry: str = "current",
        order_type: str = "MARKET",
        limit_price: float = 0,
        product_type: str = "MARGIN"  # MARGIN = NRML (Normal), NOT INTRADAY
    ) -> dict:
        """
        Place order - Supports MARKET and LIMIT orders
        product_type="MARGIN" = Normal/NRML order (can carry forward)

        Args:
            strike: Strike price
            option_type: CE or PE
            quantity: Number of contracts
            side: BUY or SELL
            expiry: current, next, or monthly
            order_type: MARKET or LIMIT
            limit_price: Price for LIMIT orders (ignored for MARKET)
            product_type: MARGIN (Normal) or INTRADAY
        """
        if quantity <= 0:
            return {'status': 'failure', 'message': f'Invalid quantity: {quantity}'}

        if order_type == "LIMIT" and limit_price <= 0:
            return {'status': 'failure', 'message': 'Limit price required for LIMIT orders'}

        sec_id = security_cache.get_security_id(strike, option_type, expiry)
        if not sec_id:
            return {'status': 'failure', 'message': f'Security ID not found for NIFTY {strike} {option_type}'}

        try:
            # Build order params - supports both MARKET and LIMIT
            order_params = {
                'security_id': sec_id,
                'exchange_segment': 'NSE_FNO',
                'transaction_type': side,
                'quantity': quantity,
                'order_type': order_type,
                'product_type': product_type,
                'price': limit_price if order_type == "LIMIT" else 0,
                'trigger_price': 0,
                'validity': 'DAY'
            }
            
            logger.info(f"Order parameters: {order_params}")
            
            resp = self.dhan.place_order(**order_params)
            logger.info(f"Dhan place_order return: {resp}")
            
            if resp.get('status') == 'success' or resp.get('orderId'):
                return {
                    'status': 'success',
                    'order_id': resp.get('orderId'),
                    'message': f'Order placed: {side} {quantity} NIFTY {strike} {option_type}'
                }
            else:
                return {
                    'status': 'failure',
                    'message': str(resp.get('remarks', resp)),
                    'response': resp
                }
                
        except Exception as e:
            logger.error(f"Order error: {e}")
            return {'status': 'failure', 'message': str(e)}
    
    def exit_position(self, position: dict) -> dict:
        """
        Exit position using security_id directly - MATCHES ORIGINAL
        Uses same product_type as the position
        """
        sec_id = position.get('security_id')
        qty = abs(position.get('qty', 0))
        symbol = position.get('symbol', '')
        product_type = position.get('product_type', 'MARGIN')
        
        if not sec_id or qty <= 0:
            return {'status': 'failure', 'message': 'Invalid position data'}
        
        # If long (qty > 0), SELL to exit. If short, BUY to exit.
        side = 'SELL' if position.get('qty', 0) > 0 else 'BUY'
        
        try:
            order_params = {
                'security_id': sec_id,
                'exchange_segment': 'NSE_FNO',
                'transaction_type': side,
                'quantity': qty,
                'order_type': 'MARKET',
                'product_type': product_type,  # Same as position
                'price': 0,
                'trigger_price': 0,
                'validity': 'DAY'
            }
            
            logger.info(f"Exit order: {order_params}")
            
            resp = self.dhan.place_order(**order_params)
            logger.info(f"Exit response: {resp}")
            
            if resp.get('status') == 'success' or resp.get('orderId'):
                return {
                    'status': 'success',
                    'order_id': resp.get('orderId'),
                    'message': f'Position exited: {symbol}'
                }
            else:
                return {
                    'status': 'failure', 
                    'message': str(resp.get('remarks', resp))
                }
                
        except Exception as e:
            logger.error(f"Exit error: {e}")
            return {'status': 'failure', 'message': str(e)}


dhan_service = DhanService()
