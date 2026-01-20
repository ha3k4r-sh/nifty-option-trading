# Nifty Option Trading

A modern, feature-rich NIFTY options trading dashboard built with FastAPI and React. This application provides a sleek interface for trading NIFTY 50 index options with real-time data integration via the Dhan Trading API.

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)
![React](https://img.shields.io/badge/React-18-blue.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## Features

### Trading Features
- **Real-time Options Chain**: View CE (Call) and PE (Put) options with live LTP (upto 3 contracts)
- **Smart Strike Selection**: Auto-calculates ATM (At The Money) strike based on spot price
- **Multiple Expiries**: Support for Current Week, Next Week, and Monthly expiries
- **Market & Limit Orders**: Place both market and limit price orders
- **Capital Allocation**: Quick capital percentage buttons (25%, 50%, 75%, 100%)
- **Live P/L Tracking**: Real-time profit/loss calculation for open positions
- **One-Click Exit**: Quick position exit with a single click

### Mock Trading Mode
- **Safe Testing Environment**: Test your strategies without risking real money
- **Realistic Simulation**: Uses real market prices for mock trades
- **Separate Trade History**: Mock and live trades are stored separately
- **Visual Indicator**: Orange border and badge when mock mode is active
- **Toggle Anytime**: Switch between mock and live mode instantly

### User Interface
- **Modern Dark/Light Theme**: Toggle between dark and light modes with persistent preference
- **Responsive Design**: Works on desktop and tablet screens
- **Tabbed Navigation**: Organized into Home, Trades, and Settings tabs
- **Real-time Updates**: Live IST clock and auto-refreshing data
- **Toast Notifications**: Clear feedback for all actions

### Analytics & History
- **Trade History**: Complete log of all trades with entry/exit prices
- **P/L Analytics**: Today's P/L, Total P/L, Win Rate, and Trade Count
- **Interactive Chart**: Visual cumulative P/L chart using Chart.js
- **Separate Views**: Filter trades by Live or Mock mode

### Security & Settings
- **Session Authentication**: Secure login with session tokens
- **Password Management**: Change password from Settings
- **API Credentials**: Securely store Dhan API credentials
- **IST Timezone**: All times displayed in Indian Standard Time

## Installation

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)
- A Dhan trading account with API access

### Quick Start

#### Windows
```batch
# Clone the repository
git clone https://github.com/ha3k4r-sh/nifty-option-trading.git
cd nifty-option-trading

# Run the application
run.bat
```

#### Linux/macOS
```bash
# Clone the repository
git clone https://github.com/ha3k4r-sh/nifty-option-trading.git
cd nifty-option-trading

# Make the script executable
chmod +x run.sh

# Run the application
./run.sh
```

The application will:
1. Install required Python dependencies
2. Create necessary directories (cache, data, logs)
3. Start the server at http://localhost:8000

### Manual Installation
```bash
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## Usage

### First Time Setup

1. **Open the application**: Navigate to http://localhost:8000/login
2. **Login**: Use default credentials `admin` / `admin`
3. **Configure API**: Go to Settings tab and enter your Dhan API credentials
   - Get your API key from [Dhan Trading APIs](https://web.dhan.co/index/profile)
   - Enter your Client ID and Access Token
   - Click "Save Credentials"

### Trading Workflow

1. **Select Contract**:
   - Choose expiry (Week/Next/Month)
   - Select a Call (CE) or Put (PE) option from the list
   - ATM strike is highlighted in gold

2. **Fetch Price**:
   - Click "FETCH PRICE" to get current LTP
   - Choose Market or Limit order type
   - For limit orders, enter your desired price

3. **Set Capital**:
   - Select capital allocation percentage
   - System auto-calculates lots based on available funds

4. **Place Order**:
   - Review quantity and cost
   - Click BUY button to place order

5. **Monitor Position**:
   - View live P/L in the right panel
   - Click EXIT to close position

### Mock Trading

Mock trading is perfect for:
- Testing new strategies without real money
- Learning the platform interface
- Paper trading during market hours
- Verifying order logic before going live

**To enable Mock Mode:**
1. Click the "Mock" toggle in the header, OR
2. Go to Settings > Preferences > Mock Trading Mode

**When mock mode is active:**
- Orange border appears around the app
- "Mock" badge shows in header
- Orders are simulated (no real trades placed)
- Trades are logged separately in mock history

### Viewing Trade History

1. Go to the **Trades** tab
2. Toggle between "Live Trades" and "Mock Trades"
3. View analytics: Today's P/L, Total P/L, Win Rate
4. See cumulative P/L chart
5. Review individual trade details

### Changing Password

1. Go to **Settings** tab
2. Find "Account Settings" section
3. Enter current password
4. Enter and confirm new password
5. Click "Change Password"

## Project Structure

```
nifty-option-trading/
├── backend/
│   ├── main.py              # FastAPI application & API endpoints
│   ├── dhan_service.py      # Dhan API integration
│   ├── security_cache.py    # Options chain caching
│   ├── trade_history.py     # Trade storage & analytics
│   ├── config.py            # Configuration & settings
│   ├── logger.py            # Centralized logging
│   ├── requirements.txt     # Python dependencies
│   ├── static/
│   │   ├── index.html       # Main React application
│   │   ├── login.html       # Login page
│   │   └── settings.html    # Standalone settings page
│   ├── cache/               # Security ID cache
│   ├── data/                # Trade history storage
│   │   ├── credentials.json # API credentials (auto-created)
│   │   ├── live_trades.json # Live trade history
│   │   └── mock_trades.json # Mock trade history
│   └── logs/                # Application logs
├── run.bat                  # Windows startup script
├── run.sh                   # Linux/macOS startup script
└── README.md
```

## API Endpoints

### Authentication
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/login` | POST | User login |
| `/api/auth/logout` | POST | User logout |
| `/api/auth/check` | GET | Verify session |
| `/api/auth/change-password` | POST | Change password |

### Trading
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/market` | GET | Market data (spot, ATM, expiry) |
| `/api/options/{strike}` | GET | Option pair data |
| `/api/option/ltp` | GET | Single option LTP |
| `/api/order` | POST | Place order (supports MARKET/LIMIT) |
| `/api/exit` | POST | Exit position |
| `/api/positions` | GET | Current positions |

### Trades & Analytics
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/trades` | GET | Trade history |
| `/api/trades/live` | GET | Live trades only |
| `/api/trades/mock` | GET | Mock trades only |
| `/api/analytics` | GET | P/L analytics |
| `/api/analytics/chart` | GET | Chart data |

### Configuration
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/settings` | GET/POST | API credentials |
| `/api/config/mock-mode` | GET/POST | Mock mode toggle |
| `/api/cache/refresh` | POST | Refresh security cache |
| `/api/cache/status` | GET | Cache status |

## Technologies Used

- **Backend**: FastAPI, Python 3.8+, Uvicorn
- **Frontend**: React 18, Babel (in-browser transpilation)
- **Styling**: Custom CSS with CSS Variables for theming
- **Charts**: Chart.js
- **Fonts**: JetBrains Mono, Plus Jakarta Sans
- **API Integration**: Dhan Trading API (dhanhq library)

## How It Works

### Smart Security Cache
The application uses an intelligent caching system:
1. Downloads Dhan security master on first run (~33MB)
2. Filters to NIFTY options only (~4000 contracts, ~150KB)
3. Pre-builds strike → security_id lookup maps
4. Enables O(1) instant lookups instead of repeated CSV parsing
5. Auto-refreshes when cache is stale or expiry changes

### Mock Trading System
Mock mode provides realistic paper trading:
- Uses real market LTP prices for order fills
- Calculates P/L against live market data
- Stores trades separately from live trades
- No API calls to broker for order placement

### Trade History
All trades are persisted to JSON files:
- `live_trades.json` - Real broker trades
- `mock_trades.json` - Simulated trades
- Analytics calculated on-the-fly from trade data

## Configuration

### Credentials Storage
- API credentials stored in `backend/data/credentials.json`
- Passwords are session-based (reset on server restart)
- Session tokens expire after 24 hours

### Logging
- Logs written to `backend/logs/` directory
- Daily log rotation with timestamps
- Both console and file logging enabled

### Trading Settings
Edit `backend/config.py`:
```python
LOT_SIZE = 75              # NIFTY lot size
STRIKE_INTERVAL = 50       # Strike price interval
CACHE_VALIDITY_HOURS = 12  # Cache refresh interval
```

## Troubleshooting

### Common Issues

**"Not configured" error**
- Go to Settings and enter your Dhan API credentials

**"Invalid credentials" on login**
- Default credentials are `admin` / `admin`
- Password resets to default on server restart

**Orders not executing**
- Check if mock mode is enabled (orange border)
- Verify API credentials are correct
- Check market hours (9:15 AM - 3:30 PM IST)

**LTP showing 0**
- Market may be closed
- Try clicking "FETCH PRICE" again
- Check API connection in Settings

**Cache not loading**
```bash
# Delete cache and restart
rm backend/cache/nifty_options.json
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This software is for educational and informational purposes only. Trading in the stock market involves substantial risk of loss and is not suitable for every investor. Past performance is not indicative of future results. Always do your own research and consult with a qualified financial advisor before making any investment decisions.

The mock trading feature is provided for testing and learning purposes. It does not guarantee similar results in live trading.

---

**Developed by [ha3k4r.sh@gmail.com](mailto:ha3k4r.sh@gmail.com)**
