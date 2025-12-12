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
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
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
            padding: 20px;
            min-height: 100vh;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--accent);
        }
        h1 { font-size: 1.8em; font-weight: 600; }
        .status-badge {
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: 500;
        }
        .status-ok { background: var(--success); color: #000; }
        .status-warning { background: var(--warning); color: #000; }
        .status-error { background: var(--danger); color: #fff; }
        
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .zone-card {
            background: var(--bg-card);
            border-radius: 12px;
            padding: 20px;
            border: 1px solid var(--accent);
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .zone-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(0,0,0,0.3);
        }
        .zone-card.override {
            border-color: var(--danger);
            box-shadow: 0 0 15px rgba(255, 107, 107, 0.2);
        }
        .zone-name {
            font-size: 1.1em;
            font-weight: 600;
            margin-bottom: 15px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .zone-mode {
            font-size: 0.7em;
            padding: 4px 8px;
            border-radius: 4px;
            font-weight: 500;
        }
        .mode-schedule { background: var(--success); color: #000; }
        .mode-override { background: var(--danger); color: #fff; }
        .mode-permanent { background: var(--warning); color: #000; }
        
        .temps {
            display: flex;
            justify-content: space-around;
            text-align: center;
            margin: 15px 0;
        }
        .temp-block label {
            display: block;
            font-size: 0.75em;
            color: var(--text-muted);
            margin-bottom: 5px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .temp-value {
            font-size: 2em;
            font-weight: 300;
        }
        .temp-value.current { color: var(--info); }
        .temp-value.target { color: var(--warning); }
        
        .section {
            background: var(--bg-card);
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 25px;
            border: 1px solid var(--accent);
        }
        .section h2 {
            font-size: 1.2em;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 1px solid var(--accent);
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
        th {
            font-weight: 600;
            color: var(--text-muted);
            font-size: 0.85em;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        tr:hover { background: rgba(255,255,255,0.03); }
        
        .timestamp {
            color: var(--text-muted);
            font-size: 0.85em;
        }
        .nav-links {
            display: flex;
            gap: 15px;
            margin-bottom: 20px;
        }
        .nav-links a {
            color: var(--info);
            text-decoration: none;
            padding: 8px 16px;
            border-radius: 6px;
            background: var(--accent);
            transition: background 0.2s;
        }
        .nav-links a:hover { background: #1a4a7a; }
        
        .stat-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
        }
        .stat-card {
            text-align: center;
            padding: 20px;
            background: var(--accent);
            border-radius: 8px;
        }
        .stat-value {
            font-size: 2.5em;
            font-weight: 300;
            color: var(--info);
        }
        .stat-label {
            font-size: 0.8em;
            color: var(--text-muted);
            text-transform: uppercase;
            margin-top: 5px;
        }
        
        @media (max-width: 600px) {
            .header { flex-direction: column; gap: 15px; text-align: center; }
            .grid { grid-template-columns: 1fr; }
            .temps { flex-direction: column; gap: 15px; }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🏠 Evohome HR92 Monitor</h1>
        <div>
            <span class="status-badge {{ 'status-ok' if system_mode == 'Auto' else 'status-warning' }}">
                {{ system_mode or 'Unknown' }}
            </span>
            <span class="timestamp" style="margin-left: 15px;">
                Updated: {{ last_update }}
            </span>
        </div>
    </div>
    
    <div class="nav-links">
        <a href="/">Dashboard</a>
        <a href="/forensics">Forensics</a>
        <a href="/api/state">API: State</a>
        <a href="/api/events">API: Events</a>
    </div>
    
    <div class="grid">
        {% for zone in zones %}
        <div class="zone-card {{ 'override' if zone.is_override else '' }}">
            <div class="zone-name">
                {{ zone.name }}
                <span class="zone-mode {{ 'mode-schedule' if zone.setpoint_mode == 'FollowSchedule' else 'mode-override' if zone.setpoint_mode == 'TemporaryOverride' else 'mode-permanent' }}">
                    {{ zone.setpoint_mode.replace('Override', ' Override') }}
                </span>
            </div>
            <div class="temps">
                <div class="temp-block">
                    <label>Current</label>
                    <div class="temp-value current">
                        {{ '%.1f' % zone.current_temp if zone.current_temp else '--' }}°
                    </div>
                </div>
                <div class="temp-block">
                    <label>Target</label>
                    <div class="temp-value target">{{ '%.1f' % zone.target_temp }}°</div>
                </div>
            </div>
        </div>
        {% endfor %}
    </div>
    
    {% if active_overrides %}
    <div class="section" style="border-color: var(--danger);">
        <h2>⚠️ Active Overrides</h2>
        <table>
            <thead>
                <tr>
                    <th>Zone</th>
                    <th>Type</th>
                    <th>Target</th>
                    <th>Since</th>
                </tr>
            </thead>
            <tbody>
                {% for override in active_overrides %}
                <tr>
                    <td>{{ override.name }}</td>
                    <td>{{ override.mode }}</td>
                    <td>{{ override.target }}°C</td>
                    <td class="timestamp">{{ override.since }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% endif %}
    
    <div class="section">
        <h2>📊 Recent Events (Last 24h)</h2>
        {% if recent_events %}
        <table>
            <thead>
                <tr>
                    <th>Time</th>
                    <th>Zone</th>
                    <th>Event</th>
                    <th>Change</th>
                    <th>Classification</th>
                </tr>
            </thead>
            <tbody>
                {% for event in recent_events %}
                <tr>
                    <td class="timestamp">{{ event.time }}</td>
                    <td>{{ event.zone_name }}</td>
                    <td>{{ event.event_type }}</td>
                    <td>{{ event.previous_target }}° → {{ event.new_target }}°</td>
                    <td>{{ event.override_type or '-' }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <p style="color: var(--text-muted);">No events in the last 24 hours.</p>
        {% endif %}
    </div>
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
    active_overrides = []
    system_mode = "Unknown"
    last_update = "Never"
    
    if _current_state:
        system_mode = _current_state.system_mode
        last_update = _current_state.timestamp.strftime("%H:%M:%S")
        
        for zone in _current_state.zones.values():
            zones.append({
                "name": zone.name,
                "current_temp": zone.current_temp,
                "target_temp": zone.target_temp,
                "setpoint_mode": zone.setpoint_mode,
                "is_override": zone.is_override,
                "is_available": zone.is_available
            })
            
            if zone.is_override:
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
