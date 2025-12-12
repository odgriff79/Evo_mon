# Evohome HR92 Monitor

A monitoring, alerting, and forensic analysis tool for Honeywell Evohome heating systems, specifically designed to detect and diagnose erroneous HR92 valve overrides.

## Features

### 🔍 Monitoring
- Real-time polling of Evohome API (configurable interval, default 5 mins)
- Web dashboard showing all zones, temperatures, and current states
- Active override tracking with duration

### 🔔 Alerting
- Instant Telegram notifications when overrides are detected
- Intelligent classification of override types
- Cooldown periods to prevent notification spam
- Optional quiet hours

### 🔬 Forensic Debugging
- SQLite database logging all state changes and events
- Override classification by likely cause:
  - **firmware_35c**: The known 35°C optimum start bug
  - **firmware_5c**: Zones dropping to 5°C unexpectedly
  - **pre_sched_drop**: Override just before scheduled temperature decrease
  - **threshold_stuck**: 0.5°C threshold sensitivity issue
  - **comms_loss**: RF communication problems
  - **user_manual**: Likely legitimate user override
- Statistical analysis: frequency by zone, time distribution, pattern detection
- API endpoints for data export and analysis

## Quick Start

### 1. Clone and Install

```bash
git clone https://github.com/yourusername/evohome-monitor.git
cd evohome-monitor
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

Copy the config template and add your credentials:

```bash
cp config.py config_local.py
nano config_local.py
```

Edit `config_local.py`:

```python
# Evohome credentials (Total Connect Comfort account)
EVOHOME_USERNAME = "your_email@example.com"
EVOHOME_PASSWORD = "your_password"

# Telegram notifications
TELEGRAM_ENABLED = True
TELEGRAM_BOT_TOKEN = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
TELEGRAM_CHAT_ID = "987654321"
```

### 3. Test Configuration

```bash
python main.py --test
```

### 4. Run

```bash
python main.py
```

Access the dashboard at `http://localhost:8080`

## Setting Up Telegram Notifications

1. Open Telegram and search for `@BotFather`
2. Send `/newbot` and follow the prompts
3. Copy the API token you receive
4. Start a chat with your new bot
5. Get your chat ID:
   - Visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
   - Send a message to your bot
   - Refresh the page and find `"chat":{"id":123456789}`
6. Add both values to `config_local.py`

## Deployment on Oracle Cloud Free Tier

### 1. Create a Free VM

1. Sign up at [oracle.com/cloud/free](https://oracle.com/cloud/free)
2. Create a Compute instance:
   - Shape: VM.Standard.E2.1.Micro (Always Free)
   - Image: Ubuntu 22.04
   - Download SSH keys

### 2. Configure Firewall

In Oracle Console:
- Virtual Cloud Networks → Your VCN → Security Lists
- Add Ingress Rule: Source 0.0.0.0/0, TCP, Port 8080

On the VM:
```bash
sudo iptables -I INPUT -p tcp --dport 8080 -j ACCEPT
```

### 3. Install and Configure

```bash
ssh -i your-key.pem ubuntu@<public-ip>

# Install dependencies
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip python3-venv git -y

# Clone and setup
git clone https://github.com/yourusername/evohome-monitor.git
cd evohome-monitor
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure
cp config.py config_local.py
nano config_local.py  # Add credentials
```

### 4. Run as a Service

Create `/etc/systemd/system/evohome-monitor.service`:

```ini
[Unit]
Description=Evohome HR92 Monitor
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/evohome-monitor
Environment=PATH=/home/ubuntu/evohome-monitor/venv/bin
ExecStart=/home/ubuntu/evohome-monitor/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable evohome-monitor
sudo systemctl start evohome-monitor
sudo systemctl status evohome-monitor
```

View logs:
```bash
sudo journalctl -u evohome-monitor -f
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Web dashboard |
| `GET /forensics` | Forensic analysis page |
| `GET /api/state` | Current system state (JSON) |
| `GET /api/events` | Override events with filters |
| `GET /api/diagnostics` | Statistical summary |
| `GET /api/zone/{id}/history` | Zone history |
| `GET /health` | Health check |

### Query Parameters for `/api/events`

- `zone_id`: Filter by zone
- `override_type`: Filter by classification
- `days`: Number of days to include (default: 30)
- `suspicious_only`: Only suspicious events (default: false)

## Known Override Causes

Based on community research, these are the known causes of false overrides:

| Pattern | Symptoms | Likely Cause |
|---------|----------|--------------|
| 35°C spike | Target jumps to 35°C with optimum start icon | Firmware bug in optimum start/stop |
| 5°C drop | Zone drops to 5°C | Comms loss or firmware bug |
| Pre-schedule override | Override 8-15 mins before scheduled decrease | Optimum stop bug |
| Stuck override | Override won't clear after schedule change | 0.5°C threshold sensitivity |
| Multi-zone sync | Override in multi-room zone won't clear | Controller doesn't track local overrides |

## Configuration Reference

| Setting | Default | Description |
|---------|---------|-------------|
| `POLL_INTERVAL_SECONDS` | 300 | How often to poll (5 min recommended) |
| `ALERT_ON_ALL_OVERRIDES` | True | Alert on all overrides, not just suspicious |
| `SUSPICIOUS_TEMPS` | [35.0, 5.0] | Temperatures flagged as suspicious |
| `ALERT_COOLDOWN_SECONDS` | 1800 | Minimum time between alerts per zone |
| `QUIET_HOURS_ENABLED` | False | Suppress notifications during quiet hours |
| `QUIET_HOURS_START` | 23 | Quiet hours start (24hr) |
| `QUIET_HOURS_END` | 7 | Quiet hours end (24hr) |
| `LOG_RETENTION_DAYS` | 90 | How long to keep forensic data |
| `WEB_PORT` | 8080 | Web dashboard port |

## File Structure

```
evohome-monitor/
├── main.py           # Entry point, orchestration
├── config.py         # Default configuration
├── config_local.py   # Your local config (gitignored)
├── poller.py         # Evohome API interaction
├── detector.py       # Override detection & classification
├── notifier.py       # Telegram notifications
├── logger.py         # SQLite forensic logging
├── web.py            # FastAPI web dashboard
├── requirements.txt  # Python dependencies
├── data/             # SQLite database (created at runtime)
└── README.md
```

## Troubleshooting

### "No state available yet"
The first poll hasn't completed. Wait 5 seconds after startup.

### Telegram notifications not working
1. Verify bot token with `https://api.telegram.org/bot<TOKEN>/getMe`
2. Ensure you've sent a message to the bot first
3. Check chat ID is correct (use getUpdates endpoint)

### API rate limiting
Honeywell limits API calls. Don't poll more frequently than every 5 minutes.

### Override not detected
The detector compares consecutive states. If an override starts and ends between polls, it may be missed. Consider reducing poll interval (but not below 5 mins).

## Contributing

Issues and PRs welcome. This was built to solve a specific problem (erroneous HR92 overrides) - if you've identified other patterns, please share!

## License

MIT
