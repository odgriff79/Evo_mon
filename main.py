#!/usr/bin/env python3
"""
Evohome HR92 Monitor - Main Application

Monitors Honeywell Evohome heating systems for erroneous overrides,
provides real-time alerting via Telegram, and logs forensic data
for debugging.

Usage:
    python main.py              # Run the monitor
    python main.py --web-only   # Run only the web dashboard
    python main.py --test       # Test configuration and exit
"""

import argparse
import asyncio
import logging
import signal
import sys
import threading
from datetime import datetime, timedelta
from typing import Optional

import config
from poller import EvohomePoller, SystemState
from detector import OverrideDetector
from notifier import NotificationManager
from logger import ForensicLogger
import web

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Reduce noise from libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("uvicorn").setLevel(logging.WARNING)


class EvohomeMonitor:
    """
    Main application class that orchestrates polling, detection,
    notification, and logging.
    """
    
    def __init__(self):
        self.poller = EvohomePoller()
        self.detector = OverrideDetector()
        self.notifier = NotificationManager()
        self.forensic_logger = ForensicLogger()
        
        self._running = False
        self._last_poll: Optional[datetime] = None
        self._poll_count = 0
        self._error_count = 0
        self._consecutive_errors = 0
        
        # Pass forensic logger to web module
        web.set_forensic_logger(self.forensic_logger)
    
    async def _poll_once(self) -> Optional[SystemState]:
        """Execute a single poll cycle."""
        try:
            # Poll the Evohome API
            state = await self.poller.poll()
            self._poll_count += 1
            self._consecutive_errors = 0
            self._last_poll = datetime.now()
            
            # Update web dashboard state
            web.set_current_state(state)
            
            # Log state snapshot (every poll)
            self.forensic_logger.log_state_snapshot(state)
            
            # Detect overrides
            new_overrides, cleared_overrides = self.detector.compare(state)
            
            # Process new overrides
            for event in new_overrides:
                # Log to database
                self.forensic_logger.log_override_event(event)
                
                # Send notification
                self.notifier.notify_override(event)
            
            # Process cleared overrides
            for event in cleared_overrides:
                self.forensic_logger.log_override_cleared(event)
                self.notifier.notify_override_cleared(event)
            
            return state
            
        except Exception as e:
            self._error_count += 1
            self._consecutive_errors += 1
            logger.error(f"Poll error: {e}")
            
            # Notify on repeated failures
            if self._consecutive_errors == 3:
                self.notifier.notify_error(f"Multiple poll failures: {e}")
            
            return None
    
    async def _fetch_schedules(self, state: SystemState):
        """Fetch and cache schedules for all zones (for forensic analysis)."""
        for zone_id in state.zones:
            try:
                schedule = await self.poller.get_zone_schedule(zone_id)
                if schedule:
                    self.detector.set_zone_schedule(zone_id, schedule)
                    logger.debug(f"Cached schedule for zone {zone_id}")
            except Exception as e:
                logger.warning(f"Could not fetch schedule for zone {zone_id}: {e}")
    
    async def run(self):
        """Main run loop."""
        logger.info("=" * 60)
        logger.info("Evohome HR92 Monitor Starting")
        logger.info("=" * 60)
        logger.info(f"Poll interval: {config.POLL_INTERVAL_SECONDS}s")
        logger.info(f"Web dashboard: http://{config.WEB_HOST}:{config.WEB_PORT}")
        logger.info(f"Database: {config.DATABASE_PATH}")
        
        self._running = True
        
        # Send startup notification
        self.notifier.notify_startup()
        
        # Initial poll
        state = await self._poll_once()
        
        if state:
            # Fetch schedules on startup (for forensic context)
            await self._fetch_schedules(state)
            logger.info(f"Initial poll successful: {len(state.zones)} zones found")
            for zone in state.zones.values():
                status = "⚠️ OVERRIDE" if zone.is_override else "✓"
                logger.info(f"  {status} {zone.name}: {zone.current_temp}°C → {zone.target_temp}°C")
        
        # Main loop
        last_cleanup = datetime.now()
        last_schedule_refresh = datetime.now()
        
        while self._running:
            try:
                # Wait for next poll
                await asyncio.sleep(config.POLL_INTERVAL_SECONDS)
                
                if not self._running:
                    break
                
                # Poll
                state = await self._poll_once()
                
                # Periodic tasks
                now = datetime.now()
                
                # Refresh schedules every 6 hours
                if state and (now - last_schedule_refresh) > timedelta(hours=6):
                    await self._fetch_schedules(state)
                    last_schedule_refresh = now
                
                # Cleanup old data daily
                if (now - last_cleanup) > timedelta(days=1):
                    self.forensic_logger.cleanup_old_data()
                    last_cleanup = now
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")
                await asyncio.sleep(60)  # Back off on unexpected errors
        
        # Shutdown
        logger.info("Shutting down...")
        self.notifier.notify_shutdown()
        await self.poller.close()
        logger.info("Shutdown complete")
    
    def stop(self):
        """Signal the monitor to stop."""
        self._running = False


async def run_with_web(monitor: EvohomeMonitor):
    """Run the monitor with the web server."""
    import uvicorn
    
    # Create web server config
    web_config = uvicorn.Config(
        web.app,
        host=config.WEB_HOST,
        port=config.WEB_PORT,
        log_level="warning"
    )
    server = uvicorn.Server(web_config)
    
    # Run both concurrently
    await asyncio.gather(
        monitor.run(),
        server.serve()
    )


def test_configuration():
    """Test the configuration and connectivity."""
    import asyncio
    
    print("Testing Evohome Monitor Configuration")
    print("=" * 50)
    
    # Test credentials
    print("\n1. Testing Evohome API connection...")
    try:
        poller = EvohomePoller()
        state = asyncio.get_event_loop().run_until_complete(poller.poll())
        print(f"   ✓ Connected successfully")
        print(f"   ✓ Found {len(state.zones)} zones:")
        for zone in state.zones.values():
            print(f"      - {zone.name}: {zone.current_temp}°C → {zone.target_temp}°C ({zone.setpoint_mode})")
        asyncio.get_event_loop().run_until_complete(poller.close())
    except Exception as e:
        print(f"   ✗ Failed: {e}")
        return False
    
    # Test Telegram
    print("\n2. Testing Telegram notifications...")
    if config.TELEGRAM_ENABLED and config.TELEGRAM_BOT_TOKEN:
        notifier = NotificationManager()
        if notifier.telegram and notifier.telegram.is_configured:
            if notifier.telegram.send("🧪 Test notification from Evohome Monitor", force=True):
                print("   ✓ Telegram notification sent")
            else:
                print("   ✗ Failed to send Telegram notification")
        else:
            print("   ⚠ Telegram not fully configured")
    else:
        print("   ⚠ Telegram disabled or not configured")
    
    # Test database
    print("\n3. Testing database...")
    try:
        forensic_logger = ForensicLogger()
        print(f"   ✓ Database initialized at {config.DATABASE_PATH}")
    except Exception as e:
        print(f"   ✗ Database error: {e}")
        return False
    
    print("\n" + "=" * 50)
    print("Configuration test complete!")
    return True


def main():
    parser = argparse.ArgumentParser(description="Evohome HR92 Monitor")
    parser.add_argument("--test", action="store_true", help="Test configuration and exit")
    parser.add_argument("--web-only", action="store_true", help="Run only the web dashboard")
    parser.add_argument("--no-web", action="store_true", help="Run without web dashboard")
    args = parser.parse_args()
    
    if args.test:
        success = test_configuration()
        sys.exit(0 if success else 1)
    
    if args.web_only:
        logger.info("Running web dashboard only...")
        web.run_server()
        return
    
    # Create monitor
    monitor = EvohomeMonitor()
    
    # Handle signals
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, stopping...")
        monitor.stop()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run
    if args.no_web:
        asyncio.run(monitor.run())
    else:
        asyncio.run(run_with_web(monitor))


if __name__ == "__main__":
    main()
