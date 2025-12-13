"""
Evohome HR92 Monitor - API Poller

Handles communication with the Evohome/Total Connect Comfort API
using the evohomeclient2 library.
"""

import logging
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional
from evohomeasync2 import EvohomeClient
try:
    from evohomeasync2 import EvohomeClientOld
    USE_OLD_CLIENT = True
except ImportError:
    USE_OLD_CLIENT = False

import config

logger = logging.getLogger(__name__)


@dataclass
class ZoneState:
    """Represents the current state of a single zone/HR92."""
    zone_id: str
    name: str
    current_temp: Optional[float]
    target_temp: float
    setpoint_mode: str  # "FollowSchedule", "TemporaryOverride", "PermanentOverride"
    until: Optional[datetime] = None  # For temporary overrides
    is_available: bool = True
    active_faults: list = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    
    @property
    def is_override(self) -> bool:
        return self.setpoint_mode in ("TemporaryOverride", "PermanentOverride")
    
    @property
    def is_temporary_override(self) -> bool:
        return self.setpoint_mode == "TemporaryOverride"
    
    @property
    def is_permanent_override(self) -> bool:
        return self.setpoint_mode == "PermanentOverride"


@dataclass
class SystemState:
    """Represents the full system state at a point in time."""
    timestamp: datetime
    system_mode: str  # "Auto", "Away", "HeatingOff", etc.
    zones: dict[str, ZoneState] = field(default_factory=dict)
    raw_data: dict = field(default_factory=dict)


class EvohomePoller:
    """Polls the Evohome API and returns structured state data."""
    
    def __init__(self, username: str = None, password: str = None):
        self.username = username or config.EVOHOME_USERNAME
        self.password = password or config.EVOHOME_PASSWORD
        self._client: Optional[EvohomeClient] = None
        self._last_login: Optional[datetime] = None
    
    async def _ensure_client(self):
        """Ensure we have an authenticated client."""
        if self._client is None:
            logger.info("Creating new Evohome client connection")
            if USE_OLD_CLIENT:
                logger.info("Using EvohomeClientOld (compatible with username/password)")
                self._client = EvohomeClientOld(self.username, self.password)
                # Old client uses update() instead of login()
                await self._client.update()
            else:
                logger.info("Using EvohomeClient (new API)")
                self._client = EvohomeClient(self.username, self.password)
                await self._client.login()
            self._last_login = datetime.now()
        return self._client
    
    async def poll(self) -> SystemState:
        """
        Poll the Evohome API and return the current system state.
        
        Returns:
            SystemState object containing all zone information
        """
        try:
            client = await self._ensure_client()

            # Refresh the status
            if USE_OLD_CLIENT:
                # Old client refreshes all data with update()
                await client.update()
            else:
                # New client refreshes specific location
                await client.locations[0].refresh_status()

            location = client.locations[0]

            # Old vs new client API differences
            if USE_OLD_CLIENT:
                tcs = location.gateways[0].systems[0]
                system_mode = tcs.mode
            else:
                tcs = location._gateways[0]._control_systems[0]
                system_mode = tcs.system_mode
            
            # Extract zone states
            zones = {}
            for zone in tcs.zones:
                # Old vs new client API differences
                if USE_OLD_CLIENT:
                    zone_id = zone.id
                    setpoint_mode = zone.mode
                else:
                    zone_id = zone.zone_id
                    setpoint_mode = zone.setpoint_mode

                # Parse the until time if present
                until = None
                if hasattr(zone, 'setpoint_status') and zone.setpoint_status:
                    until_str = zone.setpoint_status.get('until')
                    if until_str:
                        try:
                            until = datetime.fromisoformat(until_str.replace('Z', '+00:00'))
                        except (ValueError, AttributeError):
                            pass

                zone_state = ZoneState(
                    zone_id=zone_id,
                    name=zone.name,
                    current_temp=zone.temperature,
                    target_temp=zone.target_heat_temperature,
                    setpoint_mode=setpoint_mode,
                    until=until,
                    is_available=zone.temperature is not None,
                    active_faults=list(zone.active_faults) if hasattr(zone, 'active_faults') else [],
                    timestamp=datetime.now()
                )
                zones[zone_id] = zone_state
                
                logger.debug(
                    f"Zone {zone.name}: {zone.temperature}°C -> {zone.target_heat_temperature}°C "
                    f"({setpoint_mode})"
                )
            
            state = SystemState(
                timestamp=datetime.now(),
                system_mode=system_mode,
                zones=zones,
                raw_data={}  # Could store raw API response here if needed
            )
            
            logger.info(f"Polled {len(zones)} zones successfully")
            return state
            
        except Exception as e:
            logger.error(f"Error polling Evohome API: {e}")
            # Reset client on error to force re-authentication
            self._client = None
            raise
    
    async def get_zone_schedule(self, zone_id: str) -> dict:
        """
        Get the schedule for a specific zone.

        Useful for determining what the zone *should* be doing.
        """
        try:
            client = await self._ensure_client()
            location = client.locations[0]

            # Old vs new client API differences
            if USE_OLD_CLIENT:
                tcs = location.gateways[0].systems[0]
            else:
                tcs = location._gateways[0]._control_systems[0]

            for zone in tcs.zones:
                # Check zone ID based on client type
                if USE_OLD_CLIENT:
                    zone_match = (zone.id == zone_id)
                else:
                    zone_match = (zone.zone_id == zone_id)

                if zone_match:
                    schedule = await zone.get_schedule()
                    return schedule

            return {}
        except Exception as e:
            logger.error(f"Error fetching schedule for zone {zone_id}: {e}")
            return {}
    
    async def cancel_override(self, zone_id: str) -> bool:
        """
        Cancel an override on a zone, returning it to schedule.

        This is a remediation action, not typically called automatically.
        """
        try:
            client = await self._ensure_client()
            location = client.locations[0]

            # Old vs new client API differences
            if USE_OLD_CLIENT:
                tcs = location.gateways[0].systems[0]
            else:
                tcs = location._gateways[0]._control_systems[0]

            for zone in tcs.zones:
                # Check zone ID based on client type
                if USE_OLD_CLIENT:
                    zone_match = (zone.id == zone_id)
                else:
                    zone_match = (zone.zone_id == zone_id)

                if zone_match:
                    await zone.reset()
                    logger.info(f"Cancelled override on zone {zone.name}")
                    return True

            return False
        except Exception as e:
            logger.error(f"Error cancelling override for zone {zone_id}: {e}")
            return False
    
    async def close(self):
        """Close the client connection."""
        self._client = None


# Synchronous wrapper for non-async contexts
class EvohomePollerSync:
    """Synchronous wrapper around the async poller."""
    
    def __init__(self, username: str = None, password: str = None):
        self._async_poller = EvohomePoller(username, password)
    
    def poll(self) -> SystemState:
        import asyncio
        return asyncio.get_event_loop().run_until_complete(self._async_poller.poll())
    
    def get_zone_schedule(self, zone_id: str) -> dict:
        import asyncio
        return asyncio.get_event_loop().run_until_complete(
            self._async_poller.get_zone_schedule(zone_id)
        )
    
    def cancel_override(self, zone_id: str) -> bool:
        import asyncio
        return asyncio.get_event_loop().run_until_complete(
            self._async_poller.cancel_override(zone_id)
        )
    
    def close(self):
        import asyncio
        asyncio.get_event_loop().run_until_complete(self._async_poller.close())
