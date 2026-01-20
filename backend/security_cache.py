"""
Smart Security Cache for NIFTY Options
Solves the 33MB download nightmare by:
1. Filtering to NIFTY options only (~4000 contracts -> ~150KB)
2. Pre-building strike→security_id lookup maps
3. Caching with smart invalidation (expiry-aware)
"""

import os
import json
from datetime import datetime, date, timedelta
from typing import Dict, Optional, List
from dataclasses import dataclass, asdict
from dhanhq import dhanhq

from logger import setup_logger
from config import CACHE_DIR, NIFTY_CACHE_FILE, CACHE_VALIDITY_HOURS, CLIENT_ID, ACCESS_TOKEN

logger = setup_logger(__name__)


@dataclass
class OptionContract:
    security_id: str
    trading_symbol: str
    custom_symbol: str
    strike_price: float
    option_type: str  # CE or PE
    expiry_date: str
    lot_size: int


@dataclass
class NiftyOptionsCache:
    """Cached NIFTY options data with lookup maps"""
    last_updated: str
    current_expiry: str
    next_expiry: str
    monthly_expiry: str
    contracts: Dict[str, dict]  # security_id -> contract details
    
    # Pre-built lookup maps for O(1) access
    strike_map_current: Dict[str, Dict[str, str]]  # {strike: {CE: sec_id, PE: sec_id}}
    strike_map_next: Dict[str, Dict[str, str]]
    strike_map_monthly: Dict[str, Dict[str, str]]


class SecurityCache:
    """
    High-performance security lookup with smart caching.
    
    Key improvements over original:
    - Loads only NIFTY options (1.5% of total data)
    - Pre-builds lookup maps at startup
    - Caches to JSON for instant reload
    - Smart refresh on expiry change
    """
    
    def __init__(self):
        self.cache_path = os.path.join(CACHE_DIR, NIFTY_CACHE_FILE)
        self.cache: Optional[NiftyOptionsCache] = None
        self.dhan: Optional[dhanhq] = None
        
        os.makedirs(CACHE_DIR, exist_ok=True)
    
    def initialize(self, dhan_client: dhanhq):
        """Initialize cache with Dhan client"""
        self.dhan = dhan_client
        self._load_or_refresh_cache()
    
    def _get_expiry_dates_from_data(self, df) -> tuple:
        """
        Extract actual expiry dates from the data.
        Returns (current_expiry, next_expiry, monthly_expiry) as YYYY-MM-DD strings.
        """
        today = date.today()
        
        # Get unique expiry dates from NIFTY options
        nifty_mask = (
            (df['SEM_TRADING_SYMBOL'].str.startswith('NIFTY-', na=False)) &
            (df['SEM_INSTRUMENT_NAME'] == 'OPTIDX')
        )
        nifty_df = df[nifty_mask]
        
        # Parse expiry dates
        expiry_dates = []
        for exp in nifty_df['SEM_EXPIRY_DATE'].unique():
            try:
                exp_date = datetime.strptime(str(exp)[:10], "%Y-%m-%d").date()
                if exp_date >= today:
                    expiry_dates.append(exp_date)
            except:
                continue
        
        expiry_dates = sorted(set(expiry_dates))
        
        if not expiry_dates:
            # Fallback to calculated dates
            return self._get_expiry_dates_calculated()
        
        # Current expiry = nearest upcoming
        current_expiry = expiry_dates[0]
        
        # Next expiry = second nearest (if exists)
        next_expiry = expiry_dates[1] if len(expiry_dates) > 1 else current_expiry
        
        # Monthly expiry = find the one at end of month (usually has larger gap)
        monthly_expiry = current_expiry
        for exp in expiry_dates:
            # Monthly expiries are typically at month end
            if exp.day >= 24 or (len(expiry_dates) > 3 and exp == expiry_dates[3]):
                monthly_expiry = exp
                break
        
        logger.info(f"Expiry dates from data: current={current_expiry}, next={next_expiry}, monthly={monthly_expiry}")
        
        return (
            current_expiry.strftime("%Y-%m-%d"),
            next_expiry.strftime("%Y-%m-%d"),
            monthly_expiry.strftime("%Y-%m-%d")
        )
    
    def _get_expiry_dates_calculated(self) -> tuple:
        """Fallback: Calculate expiry dates (assumes Thursday expiry)"""
        today = date.today()
        
        # Find current week's Thursday
        days_to_thursday = (3 - today.weekday()) % 7
        if days_to_thursday == 0 and datetime.now().hour >= 16:
            days_to_thursday = 7
        current_thursday = today + timedelta(days=days_to_thursday)
        next_thursday = current_thursday + timedelta(days=7)
        
        # Monthly expiry
        next_month = today.replace(day=28) + timedelta(days=4)
        last_day = next_month - timedelta(days=next_month.day)
        days_to_last_thursday = (last_day.weekday() - 3) % 7
        monthly_thursday = last_day - timedelta(days=days_to_last_thursday)
        
        if monthly_thursday < today:
            next_month = (today.replace(day=28) + timedelta(days=32)).replace(day=28) + timedelta(days=4)
            last_day = next_month - timedelta(days=next_month.day)
            days_to_last_thursday = (last_day.weekday() - 3) % 7
            monthly_thursday = last_day - timedelta(days=days_to_last_thursday)
        
        return (
            current_thursday.strftime("%Y-%m-%d"),
            next_thursday.strftime("%Y-%m-%d"),
            monthly_thursday.strftime("%Y-%m-%d")
        )
    
    def _get_expiry_dates(self) -> tuple:
        """Get expiry dates - tries from cache first, then calculates"""
        if self.cache:
            return (
                self.cache.current_expiry,
                self.cache.next_expiry,
                self.cache.monthly_expiry
            )
        return self._get_expiry_dates_calculated()
    
    def _should_refresh(self) -> bool:
        """Check if cache needs refresh"""
        if not os.path.exists(self.cache_path):
            logger.info("Cache file not found, need to create")
            return True
        
        try:
            with open(self.cache_path, 'r') as f:
                data = json.load(f)
            
            # Check age
            last_updated = datetime.fromisoformat(data['last_updated'])
            age_hours = (datetime.now() - last_updated).total_seconds() / 3600
            
            if age_hours > CACHE_VALIDITY_HOURS:
                logger.info(f"Cache is {age_hours:.1f} hours old, refreshing")
                return True
            
            # Check if current expiry has passed
            current_expiry_str = data.get('current_expiry', '')
            if current_expiry_str:
                try:
                    current_expiry_date = datetime.strptime(current_expiry_str, "%Y-%m-%d").date()
                    if current_expiry_date < date.today():
                        logger.info(f"Current expiry {current_expiry_str} has passed, refreshing")
                        return True
                except:
                    pass
            
            # Check if cache has any strikes
            if not data.get('strike_map_current') or len(data.get('strike_map_current', {})) == 0:
                logger.info("Cache has no strikes for current expiry, refreshing")
                return True
            
            logger.info(f"Cache is valid ({age_hours:.1f} hours old, {len(data.get('strike_map_current', {}))} strikes)")
            return False
            
        except Exception as e:
            logger.warning(f"Cache read error: {e}, refreshing")
            return True
    
    def _load_or_refresh_cache(self):
        """Load from cache or refresh from Dhan API"""
        if self._should_refresh():
            self._refresh_from_api()
        else:
            self._load_from_file()
    
    def _load_from_file(self):
        """Load cache from JSON file"""
        try:
            with open(self.cache_path, 'r') as f:
                data = json.load(f)
            
            self.cache = NiftyOptionsCache(
                last_updated=data['last_updated'],
                current_expiry=data['current_expiry'],
                next_expiry=data['next_expiry'],
                monthly_expiry=data['monthly_expiry'],
                contracts=data['contracts'],
                strike_map_current=data['strike_map_current'],
                strike_map_next=data['strike_map_next'],
                strike_map_monthly=data['strike_map_monthly']
            )
            logger.info(f"Loaded {len(self.cache.contracts)} contracts from cache")
            
        except Exception as e:
            logger.error(f"Failed to load cache: {e}")
            self._refresh_from_api()
    
    def _refresh_from_api(self):
        """Download security master from Dhan and filter to NIFTY options only"""
        if not self.dhan:
            raise RuntimeError("Dhan client not initialized")
        
        logger.info("Downloading security master from Dhan API...")
        
        try:
            # Download to temp file
            temp_file = os.path.join(CACHE_DIR, "temp_security_master.csv")
            df = self.dhan.fetch_security_list(mode='compact', filename=temp_file)
            
            if df is None or len(df) == 0:
                # Try fallback to existing file
                fallback_file = "data/security_master.csv"
                if os.path.exists(fallback_file):
                    logger.warning("API download failed, using existing security_master.csv")
                    import pandas as pd
                    df = pd.read_csv(fallback_file)
                else:
                    raise RuntimeError("Failed to download security master and no fallback available")
            
            logger.info(f"Downloaded {len(df)} total securities")
            
            # Filter to NIFTY index options only (not BANKNIFTY, FINNIFTY, etc.)
            nifty_mask = (
                (df['SEM_TRADING_SYMBOL'].str.startswith('NIFTY-', na=False)) &
                (df['SEM_INSTRUMENT_NAME'] == 'OPTIDX') &
                (df['SEM_OPTION_TYPE'].isin(['CE', 'PE']))
            )
            nifty_df = df[nifty_mask].copy()
            logger.info(f"Filtered to {len(nifty_df)} NIFTY options")
            
            # Get expiry dates FROM THE ACTUAL DATA
            current_expiry, next_expiry, monthly_expiry = self._get_expiry_dates_from_data(df)
            logger.info(f"Expiry dates: current={current_expiry}, next={next_expiry}, monthly={monthly_expiry}")
            
            # Build contracts dict and lookup maps
            contracts = {}
            strike_map_current = {}
            strike_map_next = {}
            strike_map_monthly = {}
            
            for _, row in nifty_df.iterrows():
                sec_id = str(row['SEM_SMST_SECURITY_ID'])
                strike = int(float(row['SEM_STRIKE_PRICE']))
                opt_type = row['SEM_OPTION_TYPE']
                expiry_raw = row['SEM_EXPIRY_DATE']
                
                # Parse expiry date
                try:
                    expiry_dt = datetime.strptime(str(expiry_raw)[:10], "%Y-%m-%d")
                    expiry_str = expiry_dt.strftime("%Y-%m-%d")
                except:
                    continue
                
                contract = {
                    'security_id': sec_id,
                    'trading_symbol': row['SEM_TRADING_SYMBOL'],
                    'custom_symbol': row['SEM_CUSTOM_SYMBOL'],
                    'strike_price': strike,
                    'option_type': opt_type,
                    'expiry_date': expiry_str,
                    'lot_size': int(float(row['SEM_LOT_UNITS']))
                }
                contracts[sec_id] = contract
                
                # Build lookup maps
                strike_key = str(strike)
                
                if expiry_str == current_expiry:
                    if strike_key not in strike_map_current:
                        strike_map_current[strike_key] = {}
                    strike_map_current[strike_key][opt_type] = sec_id
                    
                elif expiry_str == next_expiry:
                    if strike_key not in strike_map_next:
                        strike_map_next[strike_key] = {}
                    strike_map_next[strike_key][opt_type] = sec_id
                    
                elif expiry_str == monthly_expiry:
                    if strike_key not in strike_map_monthly:
                        strike_map_monthly[strike_key] = {}
                    strike_map_monthly[strike_key][opt_type] = sec_id
            
            # Create cache object
            self.cache = NiftyOptionsCache(
                last_updated=datetime.now().isoformat(),
                current_expiry=current_expiry,
                next_expiry=next_expiry,
                monthly_expiry=monthly_expiry,
                contracts=contracts,
                strike_map_current=strike_map_current,
                strike_map_next=strike_map_next,
                strike_map_monthly=strike_map_monthly
            )
            
            # Save to file
            cache_data = {
                'last_updated': self.cache.last_updated,
                'current_expiry': self.cache.current_expiry,
                'next_expiry': self.cache.next_expiry,
                'monthly_expiry': self.cache.monthly_expiry,
                'contracts': self.cache.contracts,
                'strike_map_current': self.cache.strike_map_current,
                'strike_map_next': self.cache.strike_map_next,
                'strike_map_monthly': self.cache.strike_map_monthly
            }
            
            with open(self.cache_path, 'w') as f:
                json.dump(cache_data, f)
            
            # Cleanup temp file
            if os.path.exists(temp_file):
                os.remove(temp_file)
            
            logger.info(f"Cache saved: {len(contracts)} contracts, "
                       f"Current: {len(strike_map_current)} strikes, "
                       f"Next: {len(strike_map_next)} strikes, "
                       f"Monthly: {len(strike_map_monthly)} strikes")
            
        except Exception as e:
            logger.error(f"Failed to refresh cache: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def get_security_id(self, strike: int, option_type: str, expiry: str = "current") -> Optional[str]:
        """
        O(1) lookup for security ID.
        
        Args:
            strike: Strike price (e.g., 23500)
            option_type: 'CE' or 'PE'
            expiry: 'current', 'next', or 'monthly'
        
        Returns:
            Security ID string or None if not found
        """
        if not self.cache:
            logger.warning("Cache not initialized")
            return None
        
        strike_key = str(strike)
        
        if expiry == "current":
            strike_map = self.cache.strike_map_current
            exp_date = self.cache.current_expiry
        elif expiry == "next":
            strike_map = self.cache.strike_map_next
            exp_date = self.cache.next_expiry
        else:
            strike_map = self.cache.strike_map_monthly
            exp_date = self.cache.monthly_expiry
        
        result = strike_map.get(strike_key, {}).get(option_type)
        
        if not result:
            # Log available strikes near the requested one for debugging
            available = sorted([int(k) for k in strike_map.keys()])
            nearby = [s for s in available if abs(s - strike) <= 500]
            logger.warning(f"Strike {strike} {option_type} not found for {expiry} ({exp_date}). "
                          f"Available nearby: {nearby[:10]}")
        
        return result
    
    def get_contract(self, security_id: str) -> Optional[dict]:
        """Get contract details by security ID"""
        if not self.cache:
            return None
        return self.cache.contracts.get(security_id)
    
    def get_available_strikes(self, expiry: str = "current") -> List[int]:
        """Get list of available strikes for an expiry"""
        if not self.cache:
            return []
        
        if expiry == "current":
            strike_map = self.cache.strike_map_current
        elif expiry == "next":
            strike_map = self.cache.strike_map_next
        else:
            strike_map = self.cache.strike_map_monthly
        
        return sorted([int(s) for s in strike_map.keys()])
    
    def get_atm_strike(self, spot_price: float) -> int:
        """Get ATM strike for given spot price"""
        from config import STRIKE_INTERVAL
        return round(spot_price / STRIKE_INTERVAL) * STRIKE_INTERVAL
    
    def get_expiry_info(self) -> dict:
        """Get current expiry dates"""
        if not self.cache:
            current, next_exp, monthly = self._get_expiry_dates()
            return {
                'current': current,
                'next': next_exp,
                'monthly': monthly
            }
        return {
            'current': self.cache.current_expiry,
            'next': self.cache.next_expiry,
            'monthly': self.cache.monthly_expiry
        }
    
    def force_refresh(self):
        """Force refresh cache from API"""
        self._refresh_from_api()


# Singleton instance
security_cache = SecurityCache()
