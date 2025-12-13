"""
Evohome HR92 Monitor - Web Dashboard

FastAPI-based web interface for monitoring and forensic analysis.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

import config
from logger import ForensicLogger
from poller import SystemState

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Evohome HR92 Monitor",
    description="Monitoring, alerting, and forensic analysis for Evohome heating systems",
    version="1.0.0"
)

# Global state (set by main.py)
_current_state: Optional[SystemState] = None
_forensic_logger: Optional[ForensicLogger] = None


def set_current_state(state: SystemState):
    """Update the current state (called by the main polling loop)."""
    global _current_state
    _current_state = state


def set_forensic_logger(forensic_logger: ForensicLogger):
    """Set the forensic logger instance."""
    global _forensic_logger
    _forensic_logger = forensic_logger


# =============================================================================
# HTML TEMPLATES
# =============================================================================

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Evohome HR92 Monitor</title>
    <meta http-equiv="refresh" content="60">
    <style>
        :root {
            --bg-dark: #1a1a2e;
            --bg-card: #16213e;
            --accent: #0f3460;
            --text: #eee;
            --text-muted: #888;
            --success: #00d26a;
            --warning: #ffc107;
            --danger: #ff6b6b;
            --info: #4dabf7;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg-dark);
            color: var(--text);
            padding: 15px;
            min-height: 100vh;
        }

        /* Header - mobile first */
        .header {
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 2px solid var(--accent);
        }
        h1 {
            font-size: 1.5em;
            font-weight: 600;
            margin-bottom: 10px;
        }
        .header-info {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        .status-badge {
            padding: 8px 14px;
            border-radius: 20px;
            font-size: 0.9em;
            font-weight: 500;
            display: inline-block;
            width: fit-content;
        }
        .status-ok { background: var(--success); color: #000; }
        .status-warning { background: var(--warning); color: #000; }
        .timestamp {
            color: var(--text-muted);
            font-size: 0.85em;
        }

        /* Navigation - mobile optimized */
        .nav-links {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-bottom: 20px;
        }
        .nav-links a {
            color: var(--info);
            text-decoration: none;
            padding: 12px 18px;
            border-radius: 8px;
            background: var(--accent);
            font-size: 0.9em;
            min-height: 44px;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        /* Override Alert Section - Prominent */
        .override-alert {
            background: linear-gradient(135deg, rgba(255, 107, 107, 0.2), rgba(255, 107, 107, 0.1));
            border: 2px solid var(--danger);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 25px;
            box-shadow: 0 0 20px rgba(255, 107, 107, 0.3);
        }
        .override-alert h2 {
            font-size: 1.3em;
            margin-bottom: 15px;
            color: var(--danger);
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .override-count {
            background: var(--danger);
            color: #fff;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.8em;
            font-weight: 600;
        }

        /* Zone Cards - mobile first, larger touch targets */
        .zone-card {
            background: var(--bg-card);
            border-radius: 12px;
            padding: 18px;
            border: 2px solid var(--accent);
            margin-bottom: 15px;
        }
        .zone-card.override {
            border-color: var(--danger);
            background: linear-gradient(135deg, rgba(255, 107, 107, 0.1), var(--bg-card));
        }
        .zone-card.fault {
            border-color: var(--warning);
        }
        .zone-name {
            font-size: 1.15em;
            font-weight: 600;
            margin-bottom: 12px;
        }
        .zone-mode {
            font-size: 0.75em;
            padding: 5px 10px;
            border-radius: 6px;
            font-weight: 500;
            margin-top: 5px;
            display: inline-block;
        }
        .mode-schedule { background: var(--success); color: #000; }
        .mode-override { background: var(--danger); color: #fff; }
        .mode-permanent { background: var(--warning); color: #000; }

        .temps {
            display: flex;
            justify-content: space-around;
            gap: 15px;
            margin: 15px 0;
        }
        .temp-block {
            flex: 1;
            text-align: center;
        }
        .temp-block label {
            display: block;
            font-size: 0.75em;
            color: var(--text-muted);
            margin-bottom: 8px;
            text-transform: uppercase;
        }
        .temp-value {
            font-size: 2.2em;
            font-weight: 300;
        }
        .temp-value.current { color: var(--info); }
        .temp-value.target { color: var(--warning); }
        .temp-value.unavailable { color: var(--text-muted); opacity: 0.5; }

        .fault-indicator {
            margin-top: 10px;
            padding: 10px;
            background: rgba(255, 193, 7, 0.15);
            border-left: 4px solid var(--warning);
            border-radius: 6px;
            font-size: 0.85em;
            color: var(--warning);
        }
        .fault-indicator.offline {
            background: rgba(255, 107, 107, 0.15);
            border-left-color: var(--danger);
            color: var(--danger);
        }

        /* Collapsible Section */
        .collapsible-section {
            background: var(--bg-card);
            border-radius: 12px;
            padding: 0;
            margin-bottom: 20px;
            border: 1px solid var(--accent);
            overflow: hidden;
        }
        .collapsible-header {
            padding: 18px;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
            min-height: 50px;
            background: var(--accent);
        }
        .collapsible-header h2 {
            font-size: 1.2em;
            margin: 0;
        }
        .toggle-icon {
            font-size: 1.2em;
            transition: transform 0.3s;
        }
        .toggle-icon.expanded {
            transform: rotate(180deg);
        }
        .collapsible-content {
            padding: 15px;
            display: none;
        }
        .collapsible-content.expanded {
            display: block;
        }

        /* Events table - simplified for mobile */
        .events-section {
            background: var(--bg-card);
            border-radius: 12px;
            padding: 18px;
            margin-bottom: 20px;
            border: 1px solid var(--accent);
        }
        .events-section h2 {
            font-size: 1.2em;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid var(--accent);
        }
        .event-item {
            padding: 12px 0;
            border-bottom: 1px solid var(--accent);
        }
        .event-item:last-child {
            border-bottom: none;
        }
        .event-time {
            color: var(--text-muted);
            font-size: 0.8em;
            margin-bottom: 5px;
        }
        .event-zone {
            font-weight: 600;
            margin-bottom: 3px;
        }
        .event-details {
            font-size: 0.85em;
            color: var(--text-muted);
        }

        /* Tablet and Desktop - responsive grid */
        @media (min-width: 768px) {
            body { padding: 30px; }
            h1 { font-size: 2em; }
            .header {
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .header-info {
                flex-direction: row;
                align-items: center;
                gap: 20px;
            }
            .nav-links {
                gap: 15px;
            }
            .nav-links a {
                padding: 10px 18px;
                min-height: auto;
            }

            /* Grid layout for override cards on desktop */
            .override-cards {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
                gap: 20px;
            }
            .override-cards .zone-card {
                margin-bottom: 0;
            }

            /* Grid layout for all zones on desktop */
            .zone-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
                gap: 20px;
            }
            .zone-grid .zone-card {
                margin-bottom: 0;
            }

            .collapsible-content {
                padding: 20px;
            }
        }

        @media (min-width: 1200px) {
            .zone-grid {
                grid-template-columns: repeat(3, 1fr);
            }
            .override-cards {
                grid-template-columns: repeat(2, 1fr);
            }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🏠 Evohome Monitor</h1>
        <div class="header-info">
            <span class="status-badge {{ 'status-ok' if system_mode == 'Auto' else 'status-warning' }}">
                {{ system_mode or 'Unknown' }}
            </span>
            <span class="timestamp">Updated: {{ last_update }}</span>
        </div>
    </div>

    <div class="nav-links">
        <a href="/">Dashboard</a>
        <a href="/forensics">Forensics</a>
    </div>

    <!-- Active Overrides Section - Prominent at Top -->
    {% if active_overrides %}
    <div class="override-alert">
        <h2>
            ⚠️ Active Overrides
            <span class="override-count">{{ active_overrides|length }}</span>
        </h2>
        <div class="override-cards">
            {% for zone in override_zones %}
            <div class="zone-card override">
                <div class="zone-name">{{ zone.name }}</div>
                <div class="zone-mode {{ 'mode-override' if zone.setpoint_mode == 'TemporaryOverride' else 'mode-permanent' }}">
                    {{ zone.setpoint_mode.replace('Override', ' Override') }}
                </div>
                <div class="temps">
                    <div class="temp-block">
                        <label>Current</label>
                        <div class="temp-value current {{ 'unavailable' if not zone.is_available else '' }}">
                            {{ '%.1f' % zone.current_temp if zone.current_temp else '--' }}°
                        </div>
                    </div>
                    <div class="temp-block">
                        <label>Target</label>
                        <div class="temp-value target">{{ '%.1f' % zone.target_temp }}°</div>
                    </div>
                </div>
                {% if not zone.is_available %}
                <div class="fault-indicator offline">⚠️ No temperature reading</div>
                {% endif %}
                {% for fault in zone.active_faults %}
                <div class="fault-indicator">🔧 {{ fault }}</div>
                {% endfor %}
            </div>
            {% endfor %}
        </div>
    </div>
    {% endif %}

    <!-- All Zones - Collapsible -->
    <div class="collapsible-section">
        <div class="collapsible-header" onclick="toggleSection('allZones')">
            <h2>📍 All Zones ({{ zones|length }})</h2>
            <span class="toggle-icon" id="allZones-icon">▼</span>
        </div>
        <div class="collapsible-content" id="allZones-content">
            <div class="zone-grid">
                {% for zone in zones %}
                <div class="zone-card {{ 'fault' if zone.has_faults or not zone.is_available else '' }}">
                    <div class="zone-name">{{ zone.name }}</div>
                    <div class="zone-mode {{ 'mode-schedule' if zone.setpoint_mode == 'FollowSchedule' else 'mode-override' if zone.setpoint_mode == 'TemporaryOverride' else 'mode-permanent' }}">
                        {{ zone.setpoint_mode.replace('Override', ' Override') }}
                    </div>
                    <div class="temps">
                        <div class="temp-block">
                            <label>Current</label>
                            <div class="temp-value current {{ 'unavailable' if not zone.is_available else '' }}">
                                {{ '%.1f' % zone.current_temp if zone.current_temp else '--' }}°
                            </div>
                        </div>
                        <div class="temp-block">
                            <label>Target</label>
                            <div class="temp-value target">{{ '%.1f' % zone.target_temp }}°</div>
                        </div>
                    </div>
                    {% if not zone.is_available %}
                    <div class="fault-indicator offline">⚠️ No temperature reading</div>
                    {% endif %}
                    {% for fault in zone.active_faults %}
                    <div class="fault-indicator">🔧 {{ fault }}</div>
                    {% endfor %}
                </div>
                {% endfor %}
            </div>
        </div>
    </div>

    <!-- Recent Events - Collapsible -->
    <div class="collapsible-section">
        <div class="collapsible-header" onclick="toggleSection('events')">
            <h2>📊 Recent Events (Last 24h)</h2>
            <span class="toggle-icon" id="events-icon">▼</span>
        </div>
        <div class="collapsible-content" id="events-content">
            {% if recent_events %}
                {% for event in recent_events %}
                <div class="event-item">
                    <div class="event-time">{{ event.time }}</div>
                    <div class="event-zone">{{ event.zone_name }}</div>
                    <div class="event-details">
                        {{ event.event_type }}: {{ event.previous_target }}° → {{ event.new_target }}°
                        {% if event.override_type %} ({{ event.override_type }}){% endif %}
                    </div>
                </div>
                {% endfor %}
            {% else %}
                <p style="color: var(--text-muted);">No events in the last 24 hours.</p>
            {% endif %}
        </div>
    </div>

    <script>
        function toggleSection(sectionId) {
            const content = document.getElementById(sectionId + '-content');
            const icon = document.getElementById(sectionId + '-icon');

            if (content.classList.contains('expanded')) {
                content.classList.remove('expanded');
                icon.classList.remove('expanded');
            } else {
                content.classList.add('expanded');
                icon.classList.add('expanded');
            }
        }

        // Auto-expand All Zones on desktop, collapsed on mobile
        if (window.innerWidth >= 768) {
            document.getElementById('allZones-content').classList.add('expanded');
            document.getElementById('allZones-icon').classList.add('expanded');
        }
    </script>
</body>
</html>
"""

FORENSICS_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Forensics - Evohome Monitor</title>
    <style>
        :root {
            --bg-dark: #1a1a2e;
            --bg-card: #16213e;
            --accent: #0f3460;
            --text: #eee;
            --text-muted: #888;
            --success: #00d26a;
            --warning: #ffc107;
            --danger: #ff6b6b;
            --info: #4dabf7;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg-dark);
            color: var(--text);
            padding: 20px;
        }
        h1 { margin-bottom: 30px; }
        h2 { margin: 30px 0 15px; font-size: 1.2em; color: var(--info); }
        
        .nav-links {
            display: flex;
            gap: 15px;
            margin-bottom: 30px;
        }
        .nav-links a {
            color: var(--info);
            text-decoration: none;
            padding: 8px 16px;
            border-radius: 6px;
            background: var(--accent);
        }
        
        .stat-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: var(--bg-card);
            padding: 25px;
            border-radius: 12px;
            text-align: center;
            border: 1px solid var(--accent);
        }
        .stat-value {
            font-size: 3em;
            font-weight: 300;
            color: var(--info);
        }
        .stat-value.danger { color: var(--danger); }
        .stat-label {
            color: var(--text-muted);
            font-size: 0.85em;
            margin-top: 10px;
            text-transform: uppercase;
        }
        
        .section {
            background: var(--bg-card);
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 25px;
            border: 1px solid var(--accent);
        }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid var(--accent);
        }
        th { color: var(--text-muted); font-size: 0.85em; text-transform: uppercase; }
        
        .bar-chart {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        .bar-row {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .bar-label {
            width: 80px;
            font-size: 0.85em;
            color: var(--text-muted);
        }
        .bar-container {
            flex: 1;
            height: 24px;
            background: var(--accent);
            border-radius: 4px;
            overflow: hidden;
        }
        .bar-fill {
            height: 100%;
            background: var(--info);
            border-radius: 4px;
            display: flex;
            align-items: center;
            padding-left: 10px;
            font-size: 0.8em;
            min-width: 30px;
        }
    </style>
</head>
<body>
    <h1>🔍 Forensic Analysis</h1>
    
    <div class="nav-links">
        <a href="/">Dashboard</a>
        <a href="/forensics">Forensics</a>
        <a href="/api/diagnostics">API: Diagnostics</a>
    </div>
    
    <div class="stat-grid">
        <div class="stat-card">
            <div class="stat-value">{{ total_overrides }}</div>
            <div class="stat-label">Total Overrides (30d)</div>
        </div>
        <div class="stat-card">
            <div class="stat-value danger">{{ total_suspicious }}</div>
            <div class="stat-label">Suspicious Events</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{{ most_problematic_zone }}</div>
            <div class="stat-label">Most Problematic Zone</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{{ peak_hour }}:00</div>
            <div class="stat-label">Peak Override Hour</div>
        </div>
    </div>
    
    <div class="section">
        <h2>Override Frequency by Zone</h2>
        {% if zone_frequency %}
        <table>
            <thead>
                <tr>
                    <th>Zone</th>
                    <th>Total Overrides</th>
                    <th>Suspicious</th>
                    <th>Frequency</th>
                </tr>
            </thead>
            <tbody>
                {% for zone in zone_frequency %}
                <tr>
                    <td>{{ zone.zone_name }}</td>
                    <td>{{ zone.override_count }}</td>
                    <td style="color: var(--danger);">{{ zone.suspicious_count }}</td>
                    <td>
                        <div class="bar-container" style="width: 200px;">
                            <div class="bar-fill" style="width: {{ zone.percentage }}%;">
                                {{ zone.override_count }}
                            </div>
                        </div>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <p style="color: var(--text-muted);">No override data yet.</p>
        {% endif %}
    </div>
    
    <div class="section">
        <h2>Override Distribution by Hour</h2>
        <div class="bar-chart">
            {% for hour in time_distribution %}
            <div class="bar-row">
                <span class="bar-label">{{ '%02d' % hour.hour }}:00</span>
                <div class="bar-container">
                    <div class="bar-fill" style="width: {{ hour.percentage }}%;">
                        {{ hour.count }}
                    </div>
                </div>
            </div>
            {% endfor %}
        </div>
    </div>
    
    <div class="section">
        <h2>Classification Distribution</h2>
        <table>
            <thead>
                <tr>
                    <th>Type</th>
                    <th>Count</th>
                    <th>Avg Confidence</th>
                </tr>
            </thead>
            <tbody>
                {% for item in type_distribution %}
                <tr>
                    <td>{{ item.override_type }}</td>
                    <td>{{ item.count }}</td>
                    <td>{{ '%.0f' % (item.avg_confidence * 100) }}%</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</body>
</html>
"""


# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard page."""
    from jinja2 import Template

    zones = []
    override_zones = []
    active_overrides = []
    system_mode = "Unknown"
    last_update = "Never"

    if _current_state:
        system_mode = _current_state.system_mode
        last_update = _current_state.timestamp.strftime("%H:%M:%S")

        for zone in _current_state.zones.values():
            zone_data = {
                "name": zone.name,
                "current_temp": zone.current_temp,
                "target_temp": zone.target_temp,
                "setpoint_mode": zone.setpoint_mode,
                "is_override": zone.is_override,
                "is_available": zone.is_available,
                "active_faults": zone.active_faults,
                "has_faults": len(zone.active_faults) > 0
            }
            zones.append(zone_data)

            if zone.is_override:
                override_zones.append(zone_data)
                active_overrides.append({
                    "name": zone.name,
                    "mode": zone.setpoint_mode,
                    "target": zone.target_temp,
                    "since": zone.timestamp.strftime("%H:%M")
                })

    # Get recent events
    recent_events = []
    if _forensic_logger:
        events = _forensic_logger.get_override_events(days=1)
        for e in events[:10]:
            recent_events.append({
                "time": datetime.fromisoformat(e["timestamp"]).strftime("%H:%M"),
                "zone_name": e["zone_name"],
                "event_type": e["event_type"].replace("_", " ").title(),
                "previous_target": e["previous_target"],
                "new_target": e["new_target"],
                "override_type": e.get("override_type", "").replace("_", " ")
            })

    template = Template(DASHBOARD_HTML)
    html = template.render(
        zones=sorted(zones, key=lambda z: z["name"]),
        override_zones=sorted(override_zones, key=lambda z: z["name"]),
        active_overrides=active_overrides,
        recent_events=recent_events,
        system_mode=system_mode,
        last_update=last_update
    )
    return HTMLResponse(content=html)


@app.get("/forensics", response_class=HTMLResponse)
async def forensics_page(request: Request):
    """Forensics analysis page."""
    from jinja2 import Template
    
    total_overrides = 0
    total_suspicious = 0
    most_problematic_zone = "-"
    peak_hour = 0
    zone_frequency = []
    time_distribution = []
    type_distribution = []
    
    if _forensic_logger:
        diagnostics = _forensic_logger.get_diagnostics_summary(days=30)
        
        total_overrides = diagnostics["total_overrides"]
        total_suspicious = diagnostics["total_suspicious"]
        
        # Zone frequency
        zone_freq = diagnostics["zone_frequency"]
        max_count = max((z["override_count"] for z in zone_freq), default=1)
        for z in zone_freq:
            z["percentage"] = (z["override_count"] / max_count) * 100
        zone_frequency = zone_freq
        
        if zone_freq:
            most_problematic_zone = zone_freq[0]["zone_name"]
        
        # Time distribution
        time_dist = diagnostics["time_distribution"]
        max_count = max((t["count"] for t in time_dist), default=1)
        for t in time_dist:
            t["percentage"] = (t["count"] / max_count) * 100
        time_distribution = sorted(time_dist, key=lambda x: x["hour"])
        
        if time_dist:
            peak_hour = max(time_dist, key=lambda x: x["count"])["hour"]
        
        type_distribution = diagnostics["type_distribution"]
    
    template = Template(FORENSICS_HTML)
    html = template.render(
        total_overrides=total_overrides,
        total_suspicious=total_suspicious,
        most_problematic_zone=most_problematic_zone,
        peak_hour=peak_hour,
        zone_frequency=zone_frequency,
        time_distribution=time_distribution,
        type_distribution=type_distribution
    )
    return HTMLResponse(content=html)


@app.get("/api/state")
async def get_state():
    """Get current system state as JSON."""
    if not _current_state:
        raise HTTPException(status_code=503, detail="No state available yet")
    
    return {
        "timestamp": _current_state.timestamp.isoformat(),
        "system_mode": _current_state.system_mode,
        "zones": {
            zone_id: {
                "name": zone.name,
                "current_temp": zone.current_temp,
                "target_temp": zone.target_temp,
                "setpoint_mode": zone.setpoint_mode,
                "is_override": zone.is_override,
                "is_available": zone.is_available
            }
            for zone_id, zone in _current_state.zones.items()
        }
    }


@app.get("/api/events")
async def get_events(
    zone_id: str = None,
    override_type: str = None,
    days: int = 30,
    suspicious_only: bool = False
):
    """Get override events with optional filters."""
    if not _forensic_logger:
        raise HTTPException(status_code=503, detail="Forensic logger not available")
    
    events = _forensic_logger.get_override_events(
        zone_id=zone_id,
        override_type=override_type,
        days=days,
        suspicious_only=suspicious_only
    )
    return {"events": events, "count": len(events)}


@app.get("/api/diagnostics")
async def get_diagnostics(days: int = 30):
    """Get diagnostic summary."""
    if not _forensic_logger:
        raise HTTPException(status_code=503, detail="Forensic logger not available")
    
    return _forensic_logger.get_diagnostics_summary(days)


@app.get("/api/zone/{zone_id}/history")
async def get_zone_history(zone_id: str, hours: int = 24):
    """Get history for a specific zone."""
    if not _forensic_logger:
        raise HTTPException(status_code=503, detail="Forensic logger not available")
    
    history = _forensic_logger.get_zone_history(zone_id, hours)
    return {"zone_id": zone_id, "history": history}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "has_state": _current_state is not None,
        "last_update": _current_state.timestamp.isoformat() if _current_state else None
    }


def run_server():
    """Run the web server."""
    uvicorn.run(
        app,
        host=config.WEB_HOST,
        port=config.WEB_PORT,
        log_level="warning"
    )
