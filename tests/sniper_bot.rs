use super::*;
use solana_vntr_sniper::processor::sniper_bot::*;
use solana_vntr_sniper::common::config::{Config, AppState, SwapConfig};
use solana_vntr_sniper::processor::swap::{SwapDirection, SwapProtocol, SwapInType};
use solana_vntr_sniper::processor::transaction_parser::{DexType, TradeInfoFromToken};
use std::sync::Arc;

#[tokio::test]
async fn test_execute_buy_does_not_panic() {
    // This is a basic test to ensure that the execute_buy function can be called without panicking.
    // It does not actually execute a buy transaction on the blockchain.

    let config = Config::new().await;
    let app_state = Arc::new(config.lock().await.app_state.clone());
    let swap_config = Arc::new(config.lock().await.swap_config.clone());

    let trade_info = TradeInfoFromToken {
        dex_type: DexType::PumpFun,
        slot: 0,
        signature: "".to_string(),
        pool_id: "".to_string(),
        mint: "So11111111111111111111111111111111111111112".to_string(),
        timestamp: 0,
        is_buy: true,
        price: 0,
        is_reverse_when_pump_swap: false,
        coin_creator: "".to_string(),
        sol_change: 0.0,
        token_change: 0.0,
        liquidity: 0.0,
        virtual_sol_reserves: 0,
        virtual_token_reserves: 0,
    };

    let result = execute_buy(trade_info, app_state, swap_config, SwapProtocol::PumpFun).await;

    // The function should return an error when called with empty/invalid data
    // rather than panicking
    assert!(result.is_err(), "Expected error with invalid trade info");
}

#[tokio::test]
async fn test_trade_info_validation() {
    // Test that TradeInfoFromToken can be created with valid data
    let valid_trade_info = TradeInfoFromToken {
        dex_type: DexType::PumpFun,
        slot: 12345,
        signature: "test_signature_123".to_string(),
        pool_id: "test_pool_id_456".to_string(),
        mint: "So11111111111111111111111111111111111111112".to_string(),
        timestamp: 1234567890,
        is_buy: true,
        price: 100,
        is_reverse_when_pump_swap: false,
        coin_creator: "creator_address_123".to_string(),
        sol_change: 1.5,
        token_change: 1000.0,
        liquidity: 50000.0,
        virtual_sol_reserves: 10000,
        virtual_token_reserves: 1000000,
    };

    // Verify fields are set correctly
    assert_eq!(valid_trade_info.slot, 12345);
    assert_eq!(valid_trade_info.is_buy, true);
    assert_eq!(valid_trade_info.liquidity, 50000.0);
    assert_eq!(valid_trade_info.dex_type, DexType::PumpFun);
}

#[test]
fn test_dex_type_equality() {
    // Test DexType enum comparison
    assert_eq!(DexType::PumpFun, DexType::PumpFun);
    assert_ne!(DexType::PumpFun, DexType::RaydiumAmm);
}

#[test]
fn test_swap_protocol_variants() {
    // Test that SwapProtocol variants can be created
    let protocols = vec![
        SwapProtocol::PumpFun,
        SwapProtocol::RaydiumAmm,
        SwapProtocol::RaydiumCpmm,
        SwapProtocol::RaydiumClmm,
    ];

    assert_eq!(protocols.len(), 4);
}

