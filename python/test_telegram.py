#!/usr/bin/env python3
"""
Quick test script to verify Telegram bot connection
"""

import requests
import json
import sys
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Your Telegram credentials from environment
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not BOT_TOKEN or not CHAT_ID:
    print("❌ ERROR: Missing environment variables!")
    print("Please set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in your .env file")
    sys.exit(1)

def test_telegram_connection():
    """Test if the Telegram bot can send messages"""

    # Test message
    message = """
🎯 **TELEGRAM BOT TEST**

✅ Connection successful!
📚 Educational monitoring system is ready.

This bot will send you alerts about:
• 🚀 New token launches
• 💚 Wallet buy activities
• 💔 Wallet sell activities
• 📈 Price movements
• 📊 Volume spikes
• 🎯 Pattern detections

⚠️ **IMPORTANT**: This is for educational purposes only!
No actual trading will be performed.
"""

    # Telegram API URL
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    # Payload
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        # Send the message
        response = requests.post(url, json=payload)

        if response.status_code == 200:
            print("✅ SUCCESS: Telegram bot is working!")
            print("Check your Telegram for the test message.")
            result = response.json()
            if result.get("ok"):
                print(f"Message ID: {result['result']['message_id']}")
            return True
        else:
            print(f"❌ ERROR: Failed to send message")
            print(f"Status Code: {response.status_code}")
            print(f"Response: {response.text}")
            return False

    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        return False

def get_bot_info():
    """Get information about the bot"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"

    try:
        response = requests.get(url)
        if response.status_code == 200:
            result = response.json()
            if result.get("ok"):
                bot = result["result"]
                print("\n📤 Bot Information:")
                print(f"  • Name: {bot.get('first_name', 'Unknown')}")
                print(f"  • Username: @{bot.get('username', 'Unknown')}")
                print(f"  • Can Join Groups: {bot.get('can_join_groups', False)}")
                print(f"  • Can Read Messages: {bot.get('can_read_all_group_messages', False)}")
                return True
        return False
    except Exception as e:
        print(f"Could not get bot info: {e}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("TELEGRAM BOT CONNECTION TEST")
    print("=" * 50)

    # Get bot info
    if get_bot_info():
        print("\n" + "=" * 50)
        print("Testing message sending...")
        print("=" * 50)

        # Test sending a message
        if test_telegram_connection():
            print("\n✅ Telegram bot is fully configured and working!")
            print("You can now run the educational monitoring bot.")
            sys.exit(0)
        else:
            print("\n❌ Failed to send test message.")
            print("Please check your bot token and chat ID.")
            sys.exit(1)
    else:
        print("\n❌ Could not connect to Telegram bot.")
        print("Please check your bot token.")
        sys.exit(1)