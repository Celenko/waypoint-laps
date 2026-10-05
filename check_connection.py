#!/usr/bin/env python3
#!/usr/bin/env python3
"""
check_connection.py - confirm MAVSDK can talk to your vehicle (SITL or real Pixhawk).

Read-only: it never arms or moves the drone.

Usage:
  python check_connection.py                                  # Mission Planner SITL, direct TCP
  python check_connection.py udpin://0.0.0.0:14540            # Mission Planner MAVLink mirror (UDP)
  python3 check_connection.py serial:///dev/ttyTHS1:921600    # Jetson -> Pixhawk TELEM2
  python3 check_connection.py serial:///dev/ttyACM0:115200    # Jetson -> Pixhawk USB
"""

import asyncio
import sys

# Uses the gRPC MAVSDK-Python API (pip install mavsdk-grpc).
# Note: "pip install mavsdk" now installs v4, which has a different API.
from mavsdk_grpc import System

DEFAULT_ADDRESS = "tcpout://127.0.0.1:5762"
CONNECT_TIMEOUT_S = 30
READ_TIMEOUT_S = 10


async def first(stream_factory, label):
    """Return the first item from a telemetry stream, or None after a timeout."""
    async def _get():
        async for item in stream_factory():
            return item

    try:
        return await asyncio.wait_for(_get(), timeout=READ_TIMEOUT_S)
    except asyncio.TimeoutError:
        print(f"  {label:<13} (no data in {READ_TIMEOUT_S}s)")
        return None


async def request_rates(drone):
    """Ask the autopilot to stream the data we need. Some links send nothing until asked."""
    for name, call in [
        ("position", drone.telemetry.set_rate_position),
        ("gps_info", drone.telemetry.set_rate_gps_info),
        ("battery", drone.telemetry.set_rate_battery),
    ]:
        try:
            await asyncio.wait_for(call(2.0), timeout=5)
        except Exception as exc:  # not fatal, just report it
            print(f"  (could not set {name} rate: {exc})")


async def main(address: str) -> None:
    drone = System()
    print(f"Connecting to {address} ...")
    await drone.connect(system_address=address)

    async def _wait_connected():
        async for state in drone.core.connection_state():
            if state.is_connected:
                return

    try:
        await asyncio.wait_for(_wait_connected(), timeout=CONNECT_TIMEOUT_S)
    except asyncio.TimeoutError:
        print(f"No vehicle found within {CONNECT_TIMEOUT_S}s. Check that the simulation is running "
              "and the connection string / port is right.")
        return

    print("Connected to vehicle.")

    try:
        info = await asyncio.wait_for(drone.info.get_version(), timeout=READ_TIMEOUT_S)
        print(f"  Firmware:     {info.flight_sw_major}.{info.flight_sw_minor}.{info.flight_sw_patch}")
    except Exception as exc:
        print(f"  Firmware:     (unavailable: {exc})")

    await request_rates(drone)

    mode = await first(drone.telemetry.flight_mode, "Flight mode:")
    if mode is not None:
        print(f"  Flight mode:  {mode}")

    armed = await first(drone.telemetry.armed, "Armed:")
    if armed is not None:
        print(f"  Armed:        {armed}")

    gps = await first(drone.telemetry.gps_info, "GPS:")
    if gps is not None:
        print(f"  GPS:          {gps.fix_type}, {gps.num_satellites} satellites")

    pos = await first(drone.telemetry.position, "Position:")
    if pos is not None:
        print(f"  Position:     lat {pos.latitude_deg:.7f}, lon {pos.longitude_deg:.7f}, "
              f"rel alt {pos.relative_altitude_m:.1f} m")

    batt = await first(drone.telemetry.battery, "Battery:")
    if batt is not None:
        print(f"  Battery:      {batt.remaining_percent:.0f}%")

    health = await first(drone.telemetry.health, "Health:")
    if health is not None:
        print(f"  Home set:     {health.is_home_position_ok}")
        print(f"  Global pos:   {health.is_global_position_ok}")
        print(f"  Armable:      {health.is_armable}")

    if health is not None and health.is_global_position_ok and pos is not None:
        print("\nSetup looks good.")
    else:
        print("\nConnected, but some data didn't arrive - paste this output to debug.")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ADDRESS))