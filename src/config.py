"""
Configuration management for flight tracker.
Loads/saves config.json from the project root.
"""
import json
import os

DEFAULT_CONFIG = {
    "lat": 47.6541,
    "lon": -122.35,
    "location_name": "Seattle, WA",
    "dump1090_url": "http://localhost/tar1090",
    "auto_rotate_interval": 300,    # 5 minutes (normal mode)
    "fast_mode_interval": 30,       # 30 seconds (fast mode)
    "history_hours": 24,
    "idle_timeout_minutes": 5,
    "max_range_miles": 250,
    "display_range_miles": 250,
}

# config.json lives at the project root (one level above src/)
CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config.json",
)


def load_config():
    """Load config from disk, falling back to defaults for missing keys."""
    config = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                data = json.load(f)
            config.update(data)
        except (json.JSONDecodeError, IOError):
            pass
    return config


def save_config(config):
    """Persist config dict to disk."""
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)
