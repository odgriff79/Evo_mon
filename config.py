"""
Evohome HR92 Monitor - Configuration

Copy this file to config_local.py and fill in your credentials.
config_local.py is gitignored and will override these defaults.
"""

import os
from pathlib import Path

# =============================================================================
# EVOHOME CREDENTIALS
# =============================================================================
# Your Total Connect Comfort / Resideo account credentials
EVOHOME_USERNAME = os.getenv("EVOHOME_USERNAME", "your_email@example.com")
EVOHOME_PASSWORD = os.getenv("EVOHOME_PASSWORD", "your_password")

# =============================================================================
# TELEGRAM NOTIFICATIONS
# =============================================================================
# Create a bot via @BotFather on Telegram, get the token
# Then message your bot and get your chat_id from:
# https://api.telegram.org/bot<TOKEN>/getUpdates
TELEGRAM_ENABLED = True
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# =============================================================================
# POLLING SETTINGS
# =============================================================================
# How often to poll Evohome API (in seconds)
# Honeywell rate limits aggressively - 300s (5 mins) is safe
POLL_INTERVAL_SECONDS = 300

# =============================================================================
# ALERT SETTINGS
# =============================================================================
# Only alert on overrides to these "suspicious" temperatures (empty = alert on all)
SUSPICIOUS_TEMPS = [35.0, 5.0]  # Known firmware bug values

# Alert on ANY override, not just suspicious ones
ALERT_ON_ALL_OVERRIDES = True

# Cooldown per zone - don't spam if valve is flapping (seconds)
ALERT_COOLDOWN_SECONDS = 1800  # 30 minutes

# Quiet hours - no notifications during these times (24hr format)
QUIET_HOURS_ENABLED = False
QUIET_HOURS_START = 23  # 11 PM
QUIET_HOURS_END = 7     # 7 AM

# =============================================================================
# FORENSIC LOGGING
# =============================================================================
# SQLite database path for forensic logs
DATA_DIR = Path(__file__).parent / "data"
DATABASE_PATH = DATA_DIR / "evohome_forensics.db"

# How long to keep detailed logs (days)
LOG_RETENTION_DAYS = 90

# =============================================================================
# WEB DASHBOARD
# =============================================================================
WEB_ENABLED = True
WEB_HOST = "0.0.0.0"
WEB_PORT = 8080

# =============================================================================
# DEBUGGING
# =============================================================================
# Known firmware bug patterns to flag
# Pre-schedule-drop: override happens within N minutes of a scheduled temp decrease
PRE_SCHEDULE_DROP_WINDOW_MINS = 15

# 0.5°C threshold: flag when current temp is within this of next scheduled setpoint
TEMP_THRESHOLD_WARNING = 0.5

# =============================================================================
# OVERRIDE WITH LOCAL CONFIG
# =============================================================================
try:
    from config_local import *
except ImportError:
    pass
