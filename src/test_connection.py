"""
Test connection to mock dump1090
Windows version
"""
import requests
import time
import sys

print("Testing connection to mock dump1090...")
print("-" * 60)

try:
    response = requests.get('http://localhost:8080/data/aircraft.json', timeout=5)
    data = response.json()
    
    aircraft = data.get('aircraft', [])
    
    print("SUCCESS! Connected to mock server")
    print("-" * 60)
    print(f"Aircraft found: {len(aircraft)}")
    print(f"Timestamp: {data.get('now')}")
    print("")
    print("Aircraft list:")
    print("-" * 60)
    
    for i, ac in enumerate(aircraft[:5], 1):  # Show first 5
        callsign = ac.get('flight', 'UNKNOWN').strip()
        altitude = ac.get('alt_baro', 0)
        lat = ac.get('lat', 0)
        lon = ac.get('lon', 0)
        
        print(f"{i}. {callsign:8s} - {altitude:5d} ft at ({lat:.2f}, {lon:.2f})")
    
    if len(aircraft) > 5:
        print(f"... and {len(aircraft) - 5} more")
    
    print("")
    print("Mock server is working correctly!")
    
except requests.exceptions.ConnectionError:
    print("ERROR: Could not connect to mock server")
    print("")
    print("Make sure mock_dump1090.py is running:")
    print("  1. Open another Command Prompt")
    print("  2. cd flight-tracker")
    print("  3. venv\\Scripts\\activate")
    print("  4. cd src")
    print("  5. python mock_dump1090.py")
    sys.exit(1)
    
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)