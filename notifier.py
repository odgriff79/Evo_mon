"""
Evohome HR92 Monitor - Notification System

Sends alerts via Telegram (or other providers).
"""

import logging
import requests
from datetime import datetime, timedelta
from typing import Optional

import config

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Sends notifications via Telegram Bot API."""
    
    def __init__(
        self, 
        bot_token: str = None, 
        chat_id: str = None,
        cooldown_seconds: int = None
    ):
        self.bot_token = bot_token or config.TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or config.TELEGRAM_CHAT_ID
        self.cooldown_seconds = cooldown_seconds or config.ALERT_COOLDOWN_SECONDS
        self._last_alert_times: dict[str, datetime] = {}  # zone_id -> last alert time
        
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram not configured - notifications disabled")
    
    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)
    
    def _is_in_quiet_hours(self) -> bool:
        """Check if we're in quiet hours."""
        if not config.QUIET_HOURS_ENABLED:
            return False
        
        now = datetime.now()
        hour = now.hour
        
        start = config.QUIET_HOURS_START
        end = config.QUIET_HOURS_END
        
        # Handle overnight quiet hours (e.g., 23:00 to 07:00)
        if start > end:
            return hour >= start or hour < end
        else:
            return start <= hour < end
    
    def _is_in_cooldown(self, zone_id: str) -> bool:
        """Check if zone is in cooldown period."""
        if zone_id not in self._last_alert_times:
            return False
        
        last_alert = self._last_alert_times[zone_id]
        cooldown_until = last_alert + timedelta(seconds=self.cooldown_seconds)
        
        return datetime.now() < cooldown_until
    
    def send(
        self, 
        message: str, 
        zone_id: str = None,
        force: bool = False,
        silent: bool = False
    ) -> bool:
        """
        Send a notification via Telegram.
        
        Args:
            message: The message to send
            zone_id: Optional zone ID for cooldown tracking
            force: Bypass cooldown and quiet hours
            silent: Send without notification sound
            
        Returns:
            True if sent successfully
        """
        if not self.is_configured:
            logger.debug("Telegram not configured, skipping notification")
            return False
        
        # Check quiet hours
        if not force and self._is_in_quiet_hours():
            logger.info(f"In quiet hours, suppressing notification for {zone_id or 'system'}")
            return False
        
        # Check cooldown
        if not force and zone_id and self._is_in_cooldown(zone_id):
            logger.info(f"Zone {zone_id} in cooldown, suppressing notification")
            return False
        
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_notification": silent
            }
            
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            
            # Update cooldown tracker
            if zone_id:
                self._last_alert_times[zone_id] = datetime.now()
            
            logger.info(f"Telegram notification sent successfully")
            return True
            
        except requests.RequestException as e:
            logger.error(f"Failed to send Telegram notification: {e}")
            return False
    
    def send_startup_message(self) -> bool:
        """Send a startup notification."""
        message = (
            "🟢 <b>Evohome Monitor Started</b>\n\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Poll interval: {config.POLL_INTERVAL_SECONDS}s\n"
            f"Quiet hours: {'enabled' if config.QUIET_HOURS_ENABLED else 'disabled'}"
        )
        return self.send(message, force=True)
    
    def send_shutdown_message(self) -> bool:
        """Send a shutdown notification."""
        message = (
            "🔴 <b>Evohome Monitor Stopped</b>\n\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        return self.send(message, force=True)
    
    def send_error_message(self, error: str) -> bool:
        """Send an error notification."""
        message = (
            "⚠️ <b>Evohome Monitor Error</b>\n\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Error: {error}"
        )
        return self.send(message, force=True, silent=True)


class NotificationManager:
    """
    Manages notifications across multiple providers.
    Currently supports Telegram, extensible to others.
    """
    
    def __init__(self):
        self.telegram = TelegramNotifier() if config.TELEGRAM_ENABLED else None
        self._providers = []
        
        if self.telegram and self.telegram.is_configured:
            self._providers.append(self.telegram)
            logger.info("Telegram notifications enabled")
        else:
            logger.warning("No notification providers configured")
    
    def notify_override(self, event) -> bool:
        """Send an override notification."""
        if not self._providers:
            return False
        
        # Check if we should alert on this type
        if not config.ALERT_ON_ALL_OVERRIDES:
            if event.new_target not in config.SUSPICIOUS_TEMPS:
                logger.debug(f"Skipping notification - temp {event.new_target} not in suspicious list")
                return False
        
        message = event.to_alert_message()
        success = False
        
        for provider in self._providers:
            if provider.send(message, zone_id=event.zone_id):
                success = True
        
        return success
    
    def notify_override_cleared(self, event) -> bool:
        """Send a notification that an override was cleared."""
        if not self._providers:
            return False
        
        message = event.to_alert_message()
        success = False
        
        for provider in self._providers:
            # Use silent notification for cleared events
            if provider.send(message, zone_id=event.zone_id, silent=True):
                success = True
        
        return success
    
    def notify_startup(self) -> bool:
        """Send startup notifications."""
        for provider in self._providers:
            provider.send_startup_message()
        return bool(self._providers)
    
    def notify_shutdown(self) -> bool:
        """Send shutdown notifications."""
        for provider in self._providers:
            provider.send_shutdown_message()
        return bool(self._providers)
    
    def notify_error(self, error: str) -> bool:
        """Send error notifications."""
        for provider in self._providers:
            provider.send_error_message(error)
        return bool(self._providers)
