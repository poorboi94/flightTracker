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
- **SSH:** `ssh pi@10.0.0.11`
- **tar1090 web UI:** http://10.0.0.11/tar1090
- **Aircraft JSON:** http://10.0.0.11:8080/data/aircraft.json

## Development (Windows)

Run the mock ADS-B server and the app in desktop mode:

```bash
# Terminal 1 — mock ADS-B server
python src/mock_dump1090.py

# Terminal 2 — app in windowed mode
python src/main.py --desktop
```

## Pi Setup

See `my_flight_tracker_tasks_v2.docx.txt` for the full task list.

ADS-B decoding is handled by `readsb` (RTL-SDR enabled build from wiedehopf).
