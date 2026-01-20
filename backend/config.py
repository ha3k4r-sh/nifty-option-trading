"""
Configuration for NIFTY ORBIT v2
Credentials loaded from data/credentials.json
"""

import os
import json
from datetime import datetime
from dataclasses import dataclass
from zoneinfo import ZoneInfo

CREDENTIALS_FILE = "data/credentials.json"

# IST Timezone
IST = ZoneInfo("Asia/Kolkata")


def get_ist_time() -> str:
    """Get current time in IST format"""
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")


def get_ist_datetime() -> datetime:
    """Get current datetime in IST"""
    return datetime.now(IST)


# Runtime Configuration (mutable state)
@dataclass
class RuntimeConfig:
    """Runtime configuration that can be changed during execution"""
    mock_mode: bool = False


# Singleton runtime config
runtime_config = RuntimeConfig()

def load_credentials():
    """Load credentials from file"""
    if os.path.exists(CREDENTIALS_FILE):
        try:
            with open(CREDENTIALS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {"client_id": "", "access_token": ""}

def save_credentials(client_id: str, access_token: str):
    """Save credentials to file"""
    os.makedirs(os.path.dirname(CREDENTIALS_FILE), exist_ok=True)
    with open(CREDENTIALS_FILE, 'w') as f:
        json.dump({"client_id": client_id, "access_token": access_token}, f)

# Load on import
_creds = load_credentials()
CLIENT_ID = _creds.get("client_id", "")
ACCESS_TOKEN = _creds.get("access_token", "")

# Instrument Constants (matching original)
EXCHANGE_SEGMENT = "NSE_FNO"
INSTRUMENT_TYPE = "OPTIDX"
UNDERLYING_SYMBOL = "NIFTY"

# Trading Constants
LOT_SIZE = 65  # NIFTY lot size
STRIKE_INTERVAL = 50

# Order Defaults
PRODUCT_TYPE = "MARGIN"  # MARGIN = NRML (Normal), NOT INTRADAY
ORDER_TYPE = "MARKET"
VALIDITY = "DAY"

# Underlying Index
INDEX_SECURITY_ID = 13  # NIFTY 50 index ID

# Cache Settings
CACHE_DIR = "cache"
NIFTY_CACHE_FILE = "nifty_options.json"
CACHE_VALIDITY_HOURS = 12
