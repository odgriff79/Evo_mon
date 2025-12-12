#!/usr/bin/env python3
"""
Evohome HR92 Monitor - CLI Forensics Tool

Query the forensic database from the command line.

Usage:
    python cli.py events                    # Show recent override events
    python cli.py events --zone "Kitchen"   # Filter by zone name
    python cli.py events --type firmware_35c # Filter by classification
    python cli.py events --suspicious       # Only suspicious events
    python cli.py stats                     # Show statistics summary
    python cli.py zones                     # List zones by override frequency
    python cli.py hours                     # Show hourly distribution
    python cli.py export events.json        # Export events to JSON
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from logger import ForensicLogger
import config


def format_timestamp(iso_str: str) -> str:
    """Format ISO timestamp for display."""
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%Y-%m-%d %H:%M")
    except:
        return iso_str


def cmd_events(args):
    """Show override events."""
    logger = ForensicLogger()
    
    # Handle zone name to ID lookup (simplified - just filter by name in results)
    events = logger.get_override_events(
        override_type=args.type,
        days=args.days,
        suspicious_only=args.suspicious
    )
    
    # Filter by zone name if provided
    if args.zone:
        events = [e for e in events if args.zone.lower() in e["zone_name"].lower()]
    
    if not events:
        print("No events found matching criteria.")
        return
    
    print(f"\n{'Time':<18} {'Zone':<20} {'Event':<18} {'Change':<15} {'Type':<20}")
    print("-" * 95)
    
    for e in events[:args.limit]:
        time_str = format_timestamp(e["timestamp"])
        event_type = e["event_type"].replace("_", " ").title()
        change = f"{e['previous_target']}° → {e['new_target']}°"
        override_type = e.get("override_type", "-") or "-"
        
        suspicious = "⚠️ " if e.get("is_suspicious") else ""
        
        print(f"{time_str:<18} {e['zone_name']:<20} {event_type:<18} {change:<15} {suspicious}{override_type:<20}")
    
    if len(events) > args.limit:
        print(f"\n... and {len(events) - args.limit} more events. Use --limit to see more.")
    
    print(f"\nTotal: {len(events)} events in last {args.days} days")


def cmd_stats(args):
    """Show statistics summary."""
    logger = ForensicLogger()
    stats = logger.get_diagnostics_summary(days=args.days)
    
    print(f"\n{'='*50}")
    print(f"EVOHOME OVERRIDE STATISTICS (Last {args.days} days)")
    print(f"{'='*50}")
    
    print(f"\nTotal overrides:     {stats['total_overrides']}")
    print(f"Suspicious events:   {stats['total_suspicious']}")
    
    if stats['zone_frequency']:
        worst_zone = stats['zone_frequency'][0]
        print(f"Most affected zone:  {worst_zone['zone_name']} ({worst_zone['override_count']} overrides)")
    
    if stats['type_distribution']:
        print(f"\nBy classification:")
        for t in stats['type_distribution']:
            print(f"  {t['override_type']:<25} {t['count']:>4} ({t['avg_confidence']*100:.0f}% avg confidence)")


def cmd_zones(args):
    """List zones by override frequency."""
    logger = ForensicLogger()
    zones = logger.get_zone_override_frequency(days=args.days)
    
    if not zones:
        print("No override data found.")
        return
    
    print(f"\n{'Zone':<25} {'Overrides':<12} {'Suspicious':<12} {'Bar'}")
    print("-" * 70)
    
    max_count = zones[0]["override_count"] if zones else 1
    
    for z in zones:
        bar_len = int((z["override_count"] / max_count) * 30)
        bar = "█" * bar_len
        susp = f"({z['suspicious_count']})" if z['suspicious_count'] else ""
        
        print(f"{z['zone_name']:<25} {z['override_count']:<12} {susp:<12} {bar}")


def cmd_hours(args):
    """Show hourly distribution of overrides."""
    logger = ForensicLogger()
    hours = logger.get_override_time_distribution(days=args.days)
    
    if not hours:
        print("No override data found.")
        return
    
    # Fill in missing hours with 0
    hour_counts = {h["hour"]: h["count"] for h in hours}
    max_count = max(hour_counts.values()) if hour_counts else 1
    
    print(f"\nOverride distribution by hour (last {args.days} days):\n")
    
    for hour in range(24):
        count = hour_counts.get(hour, 0)
        bar_len = int((count / max_count) * 40) if max_count > 0 else 0
        bar = "█" * bar_len
        print(f"{hour:02d}:00  {count:>4}  {bar}")


def cmd_export(args):
    """Export events to JSON."""
    logger = ForensicLogger()
    events = logger.get_override_events(days=args.days)
    
    output = {
        "exported_at": datetime.now().isoformat(),
        "days": args.days,
        "event_count": len(events),
        "events": events
    }
    
    if args.output == "-":
        print(json.dumps(output, indent=2))
    else:
        with open(args.output, "w") as f:
            json.dump(output, f, indent=2)
        print(f"Exported {len(events)} events to {args.output}")


def main():
    parser = argparse.ArgumentParser(
        description="Evohome HR92 Monitor - CLI Forensics Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", help="Command")
    
    # Events command
    events_parser = subparsers.add_parser("events", help="Show override events")
    events_parser.add_argument("--zone", "-z", help="Filter by zone name")
    events_parser.add_argument("--type", "-t", help="Filter by override type")
    events_parser.add_argument("--suspicious", "-s", action="store_true", help="Only suspicious events")
    events_parser.add_argument("--days", "-d", type=int, default=30, help="Days to look back (default: 30)")
    events_parser.add_argument("--limit", "-l", type=int, default=50, help="Max events to show (default: 50)")
    events_parser.set_defaults(func=cmd_events)
    
    # Stats command
    stats_parser = subparsers.add_parser("stats", help="Show statistics summary")
    stats_parser.add_argument("--days", "-d", type=int, default=30, help="Days to analyze")
    stats_parser.set_defaults(func=cmd_stats)
    
    # Zones command
    zones_parser = subparsers.add_parser("zones", help="List zones by override frequency")
    zones_parser.add_argument("--days", "-d", type=int, default=30, help="Days to analyze")
    zones_parser.set_defaults(func=cmd_zones)
    
    # Hours command
    hours_parser = subparsers.add_parser("hours", help="Show hourly distribution")
    hours_parser.add_argument("--days", "-d", type=int, default=30, help="Days to analyze")
    hours_parser.set_defaults(func=cmd_hours)
    
    # Export command
    export_parser = subparsers.add_parser("export", help="Export events to JSON")
    export_parser.add_argument("output", help="Output file (use '-' for stdout)")
    export_parser.add_argument("--days", "-d", type=int, default=30, help="Days to export")
    export_parser.set_defaults(func=cmd_export)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Check database exists
    if not config.DATABASE_PATH.exists():
        print(f"Database not found at {config.DATABASE_PATH}")
        print("Run the monitor first to create the database.")
        sys.exit(1)
    
    args.func(args)


if __name__ == "__main__":
    main()
