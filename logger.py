"""
Evohome HR92 Monitor - Forensic Logger

Stores all state changes and override events in SQLite for later analysis.
"""

import sqlite3
import logging
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

from poller import SystemState, ZoneState
from detector import OverrideEvent, ClearedOverrideEvent, OverrideType
import config

logger = logging.getLogger(__name__)


class ForensicLogger:
    """
    SQLite-based forensic logging for Evohome state and events.
    """
    
    def __init__(self, db_path: Path = None):
        self.db_path = db_path or config.DATABASE_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()
    
    def _init_database(self):
        """Initialize the database schema."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Table for periodic state snapshots
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS state_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    system_mode TEXT,
                    zones_json TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Table for zone state history (every change)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS zone_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    zone_id TEXT NOT NULL,
                    zone_name TEXT NOT NULL,
                    current_temp REAL,
                    target_temp REAL NOT NULL,
                    setpoint_mode TEXT NOT NULL,
                    is_available INTEGER NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Table for override events (the main forensic data)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS override_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    zone_id TEXT NOT NULL,
                    zone_name TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    previous_mode TEXT,
                    new_mode TEXT,
                    previous_target REAL,
                    new_target REAL,
                    current_temp REAL,
                    override_type TEXT,
                    confidence REAL,
                    scheduled_target REAL,
                    next_schedule_change TEXT,
                    next_scheduled_temp REAL,
                    minutes_to_next_change INTEGER,
                    temp_delta_from_schedule REAL,
                    is_suspicious INTEGER,
                    diagnostic_notes TEXT,
                    duration_mins INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Indexes for common queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_zone_history_zone 
                ON zone_history(zone_id, timestamp)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_override_events_zone 
                ON override_events(zone_id, timestamp)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_override_events_type 
                ON override_events(override_type, timestamp)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_state_snapshots_time 
                ON state_snapshots(timestamp)
            """)
            
            conn.commit()
            logger.info(f"Database initialized at {self.db_path}")
    
    @contextmanager
    def _get_connection(self):
        """Get a database connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def log_state_snapshot(self, state: SystemState):
        """Log a complete system state snapshot."""
        zones_data = {
            zone_id: {
                "name": zone.name,
                "current_temp": zone.current_temp,
                "target_temp": zone.target_temp,
                "setpoint_mode": zone.setpoint_mode,
                "is_available": zone.is_available,
                "active_faults": zone.active_faults
            }
            for zone_id, zone in state.zones.items()
        }
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO state_snapshots (timestamp, system_mode, zones_json)
                VALUES (?, ?, ?)
            """, (
                state.timestamp.isoformat(),
                state.system_mode,
                json.dumps(zones_data)
            ))
            conn.commit()
    
    def log_zone_state(self, zone: ZoneState, timestamp: datetime = None):
        """Log a single zone's state."""
        timestamp = timestamp or datetime.now()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO zone_history 
                (timestamp, zone_id, zone_name, current_temp, target_temp, setpoint_mode, is_available)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                timestamp.isoformat(),
                zone.zone_id,
                zone.name,
                zone.current_temp,
                zone.target_temp,
                zone.setpoint_mode,
                1 if zone.is_available else 0
            ))
            conn.commit()
    
    def log_override_event(self, event: OverrideEvent):
        """Log an override event."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO override_events 
                (timestamp, zone_id, zone_name, event_type, previous_mode, new_mode,
                 previous_target, new_target, current_temp, override_type, confidence,
                 scheduled_target, next_schedule_change, next_scheduled_temp,
                 minutes_to_next_change, temp_delta_from_schedule, is_suspicious,
                 diagnostic_notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event.timestamp.isoformat(),
                event.zone_id,
                event.zone_name,
                "override_start",
                event.previous_mode,
                event.new_mode,
                event.previous_target,
                event.new_target,
                event.current_temp,
                event.override_type.value,
                event.confidence,
                event.scheduled_target,
                event.next_schedule_change.isoformat() if event.next_schedule_change else None,
                event.next_scheduled_temp,
                event.minutes_to_next_change,
                event.temp_delta_from_schedule,
                1 if event.is_suspicious else 0,
                event.diagnostic_notes
            ))
            conn.commit()
            logger.debug(f"Logged override event for {event.zone_name}")
    
    def log_override_cleared(self, event: ClearedOverrideEvent):
        """Log an override cleared event."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO override_events 
                (timestamp, zone_id, zone_name, event_type, previous_mode, new_mode,
                 previous_target, new_target, duration_mins)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event.timestamp.isoformat(),
                event.zone_id,
                event.zone_name,
                "override_cleared",
                event.previous_mode,
                "FollowSchedule",
                event.previous_target,
                event.new_target,
                event.override_duration_mins
            ))
            conn.commit()
            logger.debug(f"Logged override cleared for {event.zone_name}")
    
    def cleanup_old_data(self, days: int = None):
        """Remove data older than specified days."""
        days = days or config.LOG_RETENTION_DAYS
        cutoff = datetime.now() - timedelta(days=days)
        cutoff_str = cutoff.isoformat()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM state_snapshots WHERE timestamp < ?", (cutoff_str,))
            snapshots_deleted = cursor.rowcount
            
            cursor.execute("DELETE FROM zone_history WHERE timestamp < ?", (cutoff_str,))
            history_deleted = cursor.rowcount
            
            cursor.execute("DELETE FROM override_events WHERE timestamp < ?", (cutoff_str,))
            events_deleted = cursor.rowcount
            
            conn.commit()
            
            if snapshots_deleted or history_deleted or events_deleted:
                logger.info(
                    f"Cleaned up old data: {snapshots_deleted} snapshots, "
                    f"{history_deleted} history records, {events_deleted} events"
                )
            
            # Vacuum to reclaim space
            cursor.execute("VACUUM")
    
    # =========================================================================
    # QUERY METHODS FOR FORENSIC ANALYSIS
    # =========================================================================
    
    def get_override_events(
        self, 
        zone_id: str = None, 
        override_type: str = None,
        days: int = 30,
        suspicious_only: bool = False
    ) -> list[dict]:
        """
        Query override events with filters.
        
        Args:
            zone_id: Filter by zone ID
            override_type: Filter by override type
            days: How many days back to query
            suspicious_only: Only return suspicious events
        
        Returns:
            List of event dictionaries
        """
        cutoff = datetime.now() - timedelta(days=days)
        
        query = "SELECT * FROM override_events WHERE timestamp > ?"
        params = [cutoff.isoformat()]
        
        if zone_id:
            query += " AND zone_id = ?"
            params.append(zone_id)
        
        if override_type:
            query += " AND override_type = ?"
            params.append(override_type)
        
        if suspicious_only:
            query += " AND is_suspicious = 1"
        
        query += " ORDER BY timestamp DESC"
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    
    def get_zone_override_frequency(self, days: int = 30) -> list[dict]:
        """Get override frequency by zone."""
        cutoff = datetime.now() - timedelta(days=days)
        
        query = """
            SELECT 
                zone_id,
                zone_name,
                COUNT(*) as override_count,
                SUM(CASE WHEN is_suspicious = 1 THEN 1 ELSE 0 END) as suspicious_count
            FROM override_events 
            WHERE timestamp > ? AND event_type = 'override_start'
            GROUP BY zone_id, zone_name
            ORDER BY override_count DESC
        """
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (cutoff.isoformat(),))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_override_time_distribution(self, days: int = 30) -> list[dict]:
        """Get override distribution by hour of day."""
        cutoff = datetime.now() - timedelta(days=days)
        
        query = """
            SELECT 
                CAST(strftime('%H', timestamp) AS INTEGER) as hour,
                COUNT(*) as count
            FROM override_events 
            WHERE timestamp > ? AND event_type = 'override_start'
            GROUP BY hour
            ORDER BY hour
        """
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (cutoff.isoformat(),))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_override_type_distribution(self, days: int = 30) -> list[dict]:
        """Get distribution of override types."""
        cutoff = datetime.now() - timedelta(days=days)
        
        query = """
            SELECT 
                override_type,
                COUNT(*) as count,
                AVG(confidence) as avg_confidence
            FROM override_events 
            WHERE timestamp > ? AND event_type = 'override_start'
            GROUP BY override_type
            ORDER BY count DESC
        """
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (cutoff.isoformat(),))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_zone_history(
        self, 
        zone_id: str, 
        hours: int = 24
    ) -> list[dict]:
        """Get recent history for a specific zone."""
        cutoff = datetime.now() - timedelta(hours=hours)
        
        query = """
            SELECT * FROM zone_history 
            WHERE zone_id = ? AND timestamp > ?
            ORDER BY timestamp DESC
        """
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (zone_id, cutoff.isoformat()))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_recent_state_snapshots(self, hours: int = 24) -> list[dict]:
        """Get recent state snapshots."""
        cutoff = datetime.now() - timedelta(hours=hours)
        
        query = """
            SELECT * FROM state_snapshots 
            WHERE timestamp > ?
            ORDER BY timestamp DESC
        """
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (cutoff.isoformat(),))
            results = []
            for row in cursor.fetchall():
                d = dict(row)
                d['zones'] = json.loads(d['zones_json'])
                del d['zones_json']
                results.append(d)
            return results
    
    def get_diagnostics_summary(self, days: int = 30) -> dict:
        """Get a summary of diagnostics data for the dashboard."""
        return {
            "zone_frequency": self.get_zone_override_frequency(days),
            "time_distribution": self.get_override_time_distribution(days),
            "type_distribution": self.get_override_type_distribution(days),
            "total_overrides": sum(z["override_count"] for z in self.get_zone_override_frequency(days)),
            "total_suspicious": sum(z["suspicious_count"] for z in self.get_zone_override_frequency(days)),
        }
