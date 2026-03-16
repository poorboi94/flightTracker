# Flight Tracker

Personal ADS-B flight tracker running on Raspberry Pi 5 with a 7" touchscreen.

## Hardware

- Raspberry Pi 5 (4GB)
- Hosyond 7" Touchscreen (800×480, DSI)
- FlightAware Pro Stick Plus RTL-SDR
- FlightAware Indoor Antenna (SMA)

## Pi Access

- **Hostname:** pi@flight-tracker
- **Local IP:** 10.0.0.11
- **Tailscale IP:** 100.99.69.36
- **SSH (local):** `ssh pi@10.0.0.11`
- **SSH (anywhere):** `ssh pi@100.99.69.36`
- **tar1090 web UI:** http://10.0.0.11/tar1090
- **Aircraft JSON:** http://10.0.0.11/tar1090/data/aircraft.json

## Development (Windows)

Run the mock ADS-B server and the app in desktop mode:

```bash
# Terminal 1 — mock ADS-B server
python src/mock_dump1090.py

# Terminal 2 — app in windowed mode
python src/main.py --desktop
```

## Tests

107 unit tests covering decoder, API client, database, and notification manager.

```bash
python -m pytest tests/ -v
```

## Pi Setup

See `my_flight_tracker_tasks_v2.docx.txt` for the full task list.

ADS-B decoding is handled by `readsb` (RTL-SDR enabled build from wiedehopf).

### Desktop icon (first time)

After pulling the repo on the Pi, run these once to generate the airplane icon and add a launcher to the desktop:

```bash
cd ~/flightTracker && git pull
python src/assets/create_icon.py
cp flighttracker.desktop ~/Desktop/
chmod +x ~/Desktop/flighttracker.desktop
```

### Update app

```bash
ssh pi@100.99.69.36
cd ~/flightTracker && git pull
```

Then reboot or re-launch via the desktop icon.
