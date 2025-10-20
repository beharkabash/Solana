# Migration Guide - Environment Variables Update

This guide helps you update your existing installation after the recent security and functionality improvements.

## Quick Start

If you're setting up for the first time, follow these steps:

### Python Monitoring System

1. **Copy the environment template**
```bash
cd python
cp .env.example .env
```

2. **Edit `.env` with your credentials**
```bash
nano .env  # or use your preferred editor
```

3. **Required settings:**
   - `TELEGRAM_BOT_TOKEN`: Get from @BotFather on Telegram
   - `TELEGRAM_CHAT_ID`: Get from @userinfobot on Telegram
   - `SOLANA_RPC_HTTP`: Your Solana RPC endpoint
   - `ETHEREUM_RPC_HTTP`: Your Ethereum RPC endpoint (or use public)
   - `BNB_RPC_HTTP`: Your BNB Chain RPC endpoint (or use public)
   - `BASE_RPC_HTTP`: Your Base Chain RPC endpoint (or use public)

4. **Test your setup**
```bash
python3 test_telegram.py
python3 test_monitor.py
```

### Rust Trading Bot

1. **Copy the environment template**
```bash
cd /workspaces/Solana/Solana
cp src/env.example .env
```

2. **Edit `.env` with your configuration**
```bash
nano .env
```

3. **Required settings:**
   - `PRIVATE_KEY`: Your base58-encoded Solana wallet private key
   - `RPC_HTTP`: Your Solana RPC endpoint
   - `YELLOWSTONE_GRPC_HTTP`: Your Yellowstone gRPC endpoint
   - `YELLOWSTONE_GRPC_TOKEN`: Your Yellowstone authentication token

4. **Build and test**
```bash
source "$HOME/.cargo/env"
cargo build --release
cargo test
```

---

## Migrating Existing Installation

### If You Had Hardcoded Credentials

#### Step 1: Update Python Scripts

The `test_telegram.py` file no longer accepts hardcoded credentials. You must set them in `.env`:

```bash
cd python
echo "TELEGRAM_BOT_TOKEN=your_bot_token_here" >> .env
echo "TELEGRAM_CHAT_ID=your_chat_id_here" >> .env
```

Replace `your_bot_token_here` and `your_chat_id_here` with your actual values.

#### Step 2: Remove Old Credentials

If you had credentials in your code, you can safely remove them. They're now loaded from `.env`.

#### Step 3: Verify

```bash
python3 test_telegram.py
```

You should see:
```
✅ SUCCESS: Telegram bot is working!
```

### If You're Using Custom Configurations

All custom settings can now be configured through environment variables:

1. **Copy new `.env.example` files**
   - `python/.env.example` for Python system
   - `src/env.example` for Rust system

2. **Merge your settings**
   - Keep your existing RPC endpoints
   - Add new variables from the templates
   - Update any deprecated settings

3. **Review new options**
   - Alert thresholds
   - Liquidity minimums
   - Scoring weights
   - Risk management settings

---

## Breaking Changes

### Python System

1. **`test_telegram.py`**
   - ❌ No longer accepts hardcoded credentials
   - ✅ Must use environment variables
   - ✅ Validates credentials before running

2. **Liquidity Calculations**
   - ❌ No longer returns placeholder values
   - ✅ Queries actual on-chain data
   - ⚠️ Requires valid RPC endpoints

3. **Price Change Tracking**
   - ❌ No longer returns mock data (2.5)
   - ✅ Returns 0.0 when no data available
   - ⏳ TODO: Implement actual price tracking

### Rust System

1. **Yellowstone Configuration**
   - ❌ No longer accepts default placeholder token
   - ✅ Must set `YELLOWSTONE_GRPC_TOKEN` environment variable
   - ✅ Returns clear error if missing

---

## Configuration Examples

### Minimal Python Setup (Public RPCs)

```env
# Telegram
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=123456789

# RPC Endpoints (Public - may be slow)
SOLANA_RPC_HTTP=https://api.mainnet-beta.solana.com
ETHEREUM_RPC_HTTP=https://eth.llamarpc.com
BNB_RPC_HTTP=https://bsc-dataseed1.binance.org
BASE_RPC_HTTP=https://mainnet.base.org

# Basic Settings
MIN_LIQUIDITY_USD=10000
HIGH_CONFIDENCE_THRESHOLD=80
LOG_LEVEL=INFO
```

### Production Python Setup (Premium RPCs)

```env
# Telegram
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_CHAT_ID=your_chat_id_here

# Premium RPC Endpoints
SOLANA_RPC_HTTP=https://rpc.shyft.to?api_key=YOUR_API_KEY
SOLANA_RPC_WS=wss://rpc.shyft.to?api_key=YOUR_API_KEY
ETHEREUM_RPC_HTTP=https://eth-mainnet.g.alchemy.com/v2/YOUR_API_KEY
BNB_RPC_HTTP=https://bsc-dataseed.binance.org
BASE_RPC_HTTP=https://base-mainnet.g.alchemy.com/v2/YOUR_API_KEY

# API Keys
DEXSCREENER_API_KEY=your_key_here
COINGECKO_API_KEY=your_key_here
ETHERSCAN_API_KEY=your_key_here

# Advanced Settings
MIN_LIQUIDITY_USD=50000
MIN_VOLUME_24H_USD=100000
HIGH_CONFIDENCE_THRESHOLD=85
MAX_TAX_PERCENTAGE=5
ENABLE_HONEYPOT_CHECK=true
ENABLE_RUG_DETECTION=true
```

### Rust Trading Bot Setup

```env
# Target Wallets
COPY_TRADING_TARGET_ADDRESS=wallet1,wallet2,wallet3
IS_MULTI_COPY_TRADING=true
EXCLUDED_ADDRESSES=scam_address1,scam_address2

# Trading
TOKEN_AMOUNT=0.01
SLIPPAGE=3000
TAKE_PROFIT=8.0
STOP_LOSS=-2

# RPC & Services
RPC_HTTP=https://rpc.shyft.to?api_key=YOUR_API_KEY
YELLOWSTONE_GRPC_HTTP=https://grpc.ny.shyft.to
YELLOWSTONE_GRPC_TOKEN=YOUR_GRPC_TOKEN
TRANSACTION_LANDING_SERVICE=zeroslot

# Wallet
PRIVATE_KEY=your_base58_private_key_here

# Telegram (Optional)
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

---

## Troubleshooting

### "Missing environment variables!" error

**Cause**: Required environment variables not set

**Solution**:
1. Check if `.env` file exists
2. Verify it contains required variables
3. Ensure no typos in variable names
4. Try loading manually: `source .env` (Linux/Mac)

### "Error getting pool liquidity" messages

**Cause**: Invalid RPC endpoint or network issues

**Solution**:
1. Verify RPC endpoint is accessible
2. Check if you need an API key
3. Try a different RPC provider
4. Check your internet connection

### Telegram bot not sending messages

**Cause**: Invalid credentials or bot not started

**Solution**:
1. Verify token format: `1234567890:ABCdef...`
2. Start chat with your bot on Telegram
3. Verify chat ID is correct (numeric)
4. Run `python3 test_telegram.py` to diagnose

### Rust compile errors

**Cause**: Missing dependencies or environment variables

**Solution**:
1. Ensure Rust is installed: `cargo --version`
2. Update dependencies: `cargo update`
3. Check all required env vars are set
4. Run `cargo clean && cargo build`

---

## Getting Help

If you encounter issues:

1. Check the `FIXES_SUMMARY.md` for detailed change information
2. Review error messages carefully
3. Verify all environment variables are set correctly
4. Test components individually before full system
5. Check logs for detailed error information

---

## Security Reminders

- ⚠️ **NEVER** commit `.env` files to Git
- ⚠️ **NEVER** share your private keys or API tokens
- ✅ Always use `.env.example` as template
- ✅ Keep credentials in `.env` only
- ✅ Add `.env` to `.gitignore`

---

## Verification Checklist

After migration, verify:

- [ ] `.env` file exists and contains all required variables
- [ ] No hardcoded credentials in source code
- [ ] Telegram bot test passes
- [ ] RPC endpoints are accessible
- [ ] Rust code compiles without errors
- [ ] Tests pass successfully
- [ ] Logs show no error messages

---

Last Updated: October 20, 2025
