"""
Evohome HR92 Monitor - Override Detector

Compares states, detects overrides, and classifies them by likely cause.
"""

import logging
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from poller import ZoneState, SystemState
import config

logger = logging.getLogger(__name__)


class OverrideType(Enum):
    """Classification of override causes based on known patterns."""
    UNKNOWN = "unknown"
    USER_MANUAL = "user_manual"           # Legitimate user override
    FIRMWARE_35C_BUG = "firmware_35c"     # The optimum start 35°C bug
    FIRMWARE_5C_BUG = "firmware_5c"       # Zones dropping to 5°C
    PRE_SCHEDULE_DROP = "pre_sched_drop"  # Override just before scheduled decrease
    THRESHOLD_STUCK = "threshold_stuck"   # 0.5°C threshold issue
    COMMS_LOSS = "comms_loss"             # Possible RF communication issue
    MULTI_ZONE_SYNC = "multi_zone_sync"   # Multi-room zone sync bug


@dataclass
class OverrideEvent:
    """Represents a detected override event with forensic data."""
    zone_id: str
    zone_name: str
    timestamp: datetime
    
    # State change
    previous_mode: str
    new_mode: str
    previous_target: float
    new_target: float
    current_temp: Optional[float]
    
    # Classification
    override_type: OverrideType
    confidence: float  # 0.0 to 1.0
    
    # Forensic context
    scheduled_target: Optional[float] = None
    next_schedule_change: Optional[datetime] = None
    next_scheduled_temp: Optional[float] = None
    minutes_to_next_change: Optional[int] = None
    temp_delta_from_schedule: Optional[float] = None
    
    # Flags
    is_suspicious: bool = False
    diagnostic_notes: str = ""
    
    def to_alert_message(self) -> str:
        """Format as a notification message."""
        import config
        emoji = "🔴" if self.is_suspicious else "🟡"

        lines = [
            f"{emoji} Evohome Override Detected",
            f"",
            f"Zone: {self.zone_name}",
            f"Change: {self.previous_mode} → {self.new_mode}",
            f"Setpoint: {self.previous_target}°C → {self.new_target}°C",
            f"Current temp: {self.current_temp}°C" if self.current_temp else "",
            f"Time: {self.timestamp.strftime('%H:%M:%S')}",
        ]

        if self.override_type != OverrideType.UNKNOWN:
            lines.append(f"")
            lines.append(f"Likely cause: {self.override_type.value}")

        if self.diagnostic_notes:
            lines.append(f"")
            lines.append(f"Notes: {self.diagnostic_notes}")

        # Add dashboard link
        dashboard_url = getattr(config, 'DASHBOARD_URL', None)
        if dashboard_url:
            lines.append(f"")
            lines.append(f"🔗 <a href='{dashboard_url}'>View Dashboard</a>")

        return "\n".join(line for line in lines if line is not None)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "zone_id": self.zone_id,
            "zone_name": self.zone_name,
            "timestamp": self.timestamp.isoformat(),
            "previous_mode": self.previous_mode,
            "new_mode": self.new_mode,
            "previous_target": self.previous_target,
            "new_target": self.new_target,
            "current_temp": self.current_temp,
            "override_type": self.override_type.value,
            "confidence": self.confidence,
            "scheduled_target": self.scheduled_target,
            "next_schedule_change": self.next_schedule_change.isoformat() if self.next_schedule_change else None,
            "next_scheduled_temp": self.next_scheduled_temp,
            "minutes_to_next_change": self.minutes_to_next_change,
            "temp_delta_from_schedule": self.temp_delta_from_schedule,
            "is_suspicious": self.is_suspicious,
            "diagnostic_notes": self.diagnostic_notes,
        }


@dataclass 
class ClearedOverrideEvent:
    """Represents an override being cleared (return to schedule)."""
    zone_id: str
    zone_name: str
    timestamp: datetime
    previous_mode: str
    previous_target: float
    new_target: float
    override_duration_mins: Optional[int] = None
    
    def to_alert_message(self) -> str:
        """Format as a notification message."""
        import config
        duration_str = f" (was active {self.override_duration_mins} mins)" if self.override_duration_mins else ""

        message = (
            f"🟢 Override Cleared\n\n"
            f"Zone: {self.zone_name}\n"
            f"Returned to: FollowSchedule\n"
            f"Setpoint: {self.previous_target}°C → {self.new_target}°C{duration_str}"
        )

        # Add dashboard link
        dashboard_url = getattr(config, 'DASHBOARD_URL', None)
        if dashboard_url:
            message += f"\n\n🔗 <a href='{dashboard_url}'>View Dashboard</a>"

        return message


class OverrideDetector:
    """
    Detects and classifies override events by comparing system states.
    """
    
    def __init__(self):
        self._previous_state: Optional[SystemState] = None
        self._override_start_times: dict[str, datetime] = {}  # zone_id -> when override started
        self._zone_schedules: dict[str, dict] = {}  # Cached schedules
    
    def set_zone_schedule(self, zone_id: str, schedule: dict):
        """Cache a zone's schedule for forensic analysis."""
        self._zone_schedules[zone_id] = schedule
    
    def compare(self, new_state: SystemState) -> tuple[list[OverrideEvent], list[ClearedOverrideEvent]]:
        """
        Compare new state to previous state and detect changes.
        
        Returns:
            Tuple of (new_override_events, cleared_override_events)
        """
        new_overrides = []
        cleared_overrides = []
        
        if self._previous_state is None:
            # First run - just record overrides that are already active
            for zone_id, zone in new_state.zones.items():
                if zone.is_override:
                    self._override_start_times[zone_id] = new_state.timestamp
                    logger.info(f"Zone {zone.name} already in override mode at startup")
            self._previous_state = new_state
            return new_overrides, cleared_overrides
        
        # Compare each zone
        for zone_id, new_zone in new_state.zones.items():
            prev_zone = self._previous_state.zones.get(zone_id)
            
            if prev_zone is None:
                # New zone appeared
                if new_zone.is_override:
                    self._override_start_times[zone_id] = new_state.timestamp
                continue
            
            # Detect override START
            if new_zone.is_override and not prev_zone.is_override:
                self._override_start_times[zone_id] = new_state.timestamp
                event = self._create_override_event(prev_zone, new_zone, new_state.timestamp)
                new_overrides.append(event)
                logger.warning(
                    f"Override detected: {new_zone.name} "
                    f"{prev_zone.target_temp}°C → {new_zone.target_temp}°C "
                    f"({event.override_type.value})"
                )
            
            # Detect override END (return to schedule)
            elif not new_zone.is_override and prev_zone.is_override:
                start_time = self._override_start_times.pop(zone_id, None)
                duration = None
                if start_time:
                    duration = int((new_state.timestamp - start_time).total_seconds() / 60)
                
                event = ClearedOverrideEvent(
                    zone_id=zone_id,
                    zone_name=new_zone.name,
                    timestamp=new_state.timestamp,
                    previous_mode=prev_zone.setpoint_mode,
                    previous_target=prev_zone.target_temp,
                    new_target=new_zone.target_temp,
                    override_duration_mins=duration
                )
                cleared_overrides.append(event)
                logger.info(f"Override cleared: {new_zone.name} (was active {duration} mins)")
            
            # Detect override CHANGE (override to different override)
            elif new_zone.is_override and prev_zone.is_override:
                if new_zone.target_temp != prev_zone.target_temp:
                    event = self._create_override_event(prev_zone, new_zone, new_state.timestamp)
                    new_overrides.append(event)
                    logger.warning(
                        f"Override changed: {new_zone.name} "
                        f"{prev_zone.target_temp}°C → {new_zone.target_temp}°C"
                    )
        
        self._previous_state = new_state
        return new_overrides, cleared_overrides
    
    def _create_override_event(
        self, 
        prev_zone: ZoneState, 
        new_zone: ZoneState, 
        timestamp: datetime
    ) -> OverrideEvent:
        """Create an OverrideEvent with classification."""
        
        # Get schedule context if available
        schedule = self._zone_schedules.get(new_zone.zone_id, {})
        scheduled_target, next_change, next_temp = self._get_schedule_context(schedule, timestamp)
        
        minutes_to_next = None
        if next_change:
            minutes_to_next = int((next_change - timestamp).total_seconds() / 60)
        
        temp_delta = None
        if scheduled_target is not None:
            temp_delta = new_zone.target_temp - scheduled_target
        
        # Classify the override
        override_type, confidence, notes = self._classify_override(
            prev_zone, new_zone, scheduled_target, next_change, next_temp, minutes_to_next
        )
        
        # Determine if suspicious
        is_suspicious = (
            new_zone.target_temp in config.SUSPICIOUS_TEMPS or
            override_type in (
                OverrideType.FIRMWARE_35C_BUG,
                OverrideType.FIRMWARE_5C_BUG,
                OverrideType.PRE_SCHEDULE_DROP,
                OverrideType.COMMS_LOSS
            )
        )
        
        return OverrideEvent(
            zone_id=new_zone.zone_id,
            zone_name=new_zone.name,
            timestamp=timestamp,
            previous_mode=prev_zone.setpoint_mode,
            new_mode=new_zone.setpoint_mode,
            previous_target=prev_zone.target_temp,
            new_target=new_zone.target_temp,
            current_temp=new_zone.current_temp,
            override_type=override_type,
            confidence=confidence,
            scheduled_target=scheduled_target,
            next_schedule_change=next_change,
            next_scheduled_temp=next_temp,
            minutes_to_next_change=minutes_to_next,
            temp_delta_from_schedule=temp_delta,
            is_suspicious=is_suspicious,
            diagnostic_notes=notes
        )
    
    def _classify_override(
        self,
        prev_zone: ZoneState,
        new_zone: ZoneState,
        scheduled_target: Optional[float],
        next_change: Optional[datetime],
        next_temp: Optional[float],
        minutes_to_next: Optional[int]
    ) -> tuple[OverrideType, float, str]:
        """
        Classify the likely cause of an override based on known patterns.
        
        Returns:
            Tuple of (OverrideType, confidence 0-1, diagnostic notes)
        """
        notes = []
        
        # Pattern 1: The 35°C firmware bug
        if new_zone.target_temp == 35.0:
            notes.append("Target is 35°C - known firmware bug value")
            return OverrideType.FIRMWARE_35C_BUG, 0.9, "; ".join(notes)
        
        # Pattern 2: The 5°C firmware bug  
        if new_zone.target_temp == 5.0:
            notes.append("Target is 5°C - possible firmware bug or comms loss")
            return OverrideType.FIRMWARE_5C_BUG, 0.7, "; ".join(notes)
        
        # Pattern 3: Pre-schedule drop (override just before temp decrease)
        if (minutes_to_next is not None and 
            next_temp is not None and
            minutes_to_next <= config.PRE_SCHEDULE_DROP_WINDOW_MINS and
            next_temp < prev_zone.target_temp):
            notes.append(
                f"Override occurred {minutes_to_next}min before scheduled drop "
                f"({prev_zone.target_temp}°C → {next_temp}°C)"
            )
            return OverrideType.PRE_SCHEDULE_DROP, 0.8, "; ".join(notes)
        
        # Pattern 4: 0.5°C threshold stuck
        if (scheduled_target is not None and
            abs(new_zone.target_temp - scheduled_target) <= config.TEMP_THRESHOLD_WARNING):
            notes.append(
                f"Target within 0.5°C of schedule ({new_zone.target_temp}°C vs {scheduled_target}°C) - "
                f"possible threshold bug"
            )
            return OverrideType.THRESHOLD_STUCK, 0.6, "; ".join(notes)
        
        # Pattern 5: Communication loss (zone not available)
        if not new_zone.is_available:
            notes.append("Zone reporting unavailable - possible RF communication loss")
            return OverrideType.COMMS_LOSS, 0.8, "; ".join(notes)
        
        # Pattern 6: Could be legitimate user override
        # Check if it's a "reasonable" temperature change
        if 15.0 <= new_zone.target_temp <= 25.0:
            notes.append("Temperature in normal range - may be legitimate user override")
            return OverrideType.USER_MANUAL, 0.5, "; ".join(notes)
        
        # Unknown
        notes.append("No matching pattern identified")
        return OverrideType.UNKNOWN, 0.3, "; ".join(notes)
    
    def _get_schedule_context(
        self, 
        schedule: dict, 
        now: datetime
    ) -> tuple[Optional[float], Optional[datetime], Optional[float]]:
        """
        Parse schedule to determine what should be happening now.
        
        Returns:
            Tuple of (current_scheduled_temp, next_change_time, next_temp)
        """
        if not schedule:
            return None, None, None
        
        try:
            # Evohome schedules are structured by day
            day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            today_name = day_names[now.weekday()]
            tomorrow_name = day_names[(now.weekday() + 1) % 7]
            
            daily_schedules = schedule.get("DailySchedules", [])
            
            today_schedule = None
            tomorrow_schedule = None
            for ds in daily_schedules:
                if ds.get("DayOfWeek") == today_name:
                    today_schedule = ds.get("Switchpoints", [])
                if ds.get("DayOfWeek") == tomorrow_name:
                    tomorrow_schedule = ds.get("Switchpoints", [])
            
            if not today_schedule:
                return None, None, None
            
            current_time = now.time()
            current_temp = None
            next_change = None
            next_temp = None
            
            # Find current period and next switchpoint
            for i, sp in enumerate(today_schedule):
                sp_time = datetime.strptime(sp["TimeOfDay"], "%H:%M:%S").time()
                sp_temp = sp["heatSetpoint"]
                
                if sp_time <= current_time:
                    current_temp = sp_temp
                else:
                    # This is the next switchpoint
                    next_change = datetime.combine(now.date(), sp_time)
                    next_temp = sp_temp
                    break
            
            # If no next switchpoint today, use tomorrow's first
            if next_change is None and tomorrow_schedule:
                sp = tomorrow_schedule[0]
                sp_time = datetime.strptime(sp["TimeOfDay"], "%H:%M:%S").time()
                next_change = datetime.combine(now.date() + timedelta(days=1), sp_time)
                next_temp = sp["heatSetpoint"]
            
            return current_temp, next_change, next_temp
            
        except Exception as e:
            logger.error(f"Error parsing schedule: {e}")
            return None, None, None
    
    def get_current_overrides(self) -> dict[str, datetime]:
        """Return dict of zone_id -> when override started for active overrides."""
        return self._override_start_times.copy()
