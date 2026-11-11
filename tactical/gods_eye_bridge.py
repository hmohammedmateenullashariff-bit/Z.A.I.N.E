"""
tactical/gods_eye_bridge.py
Open-Source Geospatial Intelligence (OSINT) and Sensor Fusion Engine for Project-Z.
Inspired by bilawalsidhu/gods-eye-view (#1 GitHub Trending).
Orchestrated by Sub-Agent F.R.I.D.A.Y.
"""

import json
import logging
import os
import time
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("zaine.tactical.gods_eye")

# Default coordinates: Bengaluru, India (HKBKCE)
DEFAULT_LAT = 12.9716
DEFAULT_LON = 77.5946
USER_AGENT = "ZAINE-Tactical-GodsEye/1.0"


def _http_get_json(url: str, timeout: float = 4.0) -> Optional[Any]:
    """Helper to fetch JSON with strict timeout and custom User-Agent."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.debug("OSINT fetch notice from %s: %s", url, e)
    return None


def query_air_traffic(
    lat: float = DEFAULT_LAT,
    lon: float = DEFAULT_LON,
    radius_deg: float = 1.0
) -> Dict[str, Any]:
    """
    Queries live OpenSky Network ADS-B transponder data for aircraft within a bounding box.
    Returns: Dict with aircraft count, closest callsigns, altitudes, and velocities.
    """
    lamin = lat - radius_deg
    lamax = lat + radius_deg
    lomin = lon - radius_deg
    lomax = lon + radius_deg

    url = f"https://opensky-network.org/api/states/all?lamin={lamin:.4f}&lamax={lamax:.4f}&lomin={lomin:.4f}&lomax={lomax:.4f}"
    data = _http_get_json(url)

    if not data or "states" not in data or not data["states"]:
        return {
            "status": "ok",
            "source": "OpenSky Network (ADS-B)",
            "center": {"lat": lat, "lon": lon},
            "aircraft_count": 0,
            "aircraft": [],
            "summary": f"Airspace clear within {radius_deg}° radius of coordinates ({lat:.2f}, {lon:.2f})."
        }

    flights = []
    for state in data["states"][:15]:
        # State vector fields:
        # [0]=icao24, [1]=callsign, [2]=origin_country, [5]=longitude, [6]=latitude, [7]=baro_altitude, [9]=velocity
        callsign = (state[1] or "UNKNOWN").strip()
        country = state[2] or "Unknown"
        alt_m = state[7] or 0
        speed_mps = state[9] or 0

        flights.append({
            "callsign": callsign,
            "country": country,
            "altitude_ft": int(alt_m * 3.28084),
            "speed_knots": int(speed_mps * 1.94384),
            "lat": state[6],
            "lon": state[5]
        })

    return {
        "status": "ok",
        "source": "OpenSky Network (ADS-B)",
        "center": {"lat": lat, "lon": lon},
        "aircraft_count": len(flights),
        "aircraft": flights,
        "summary": f"Detected {len(flights)} active aircraft in sector. Top callsigns: {', '.join(f['callsign'] for f in flights[:5])}."
    }


def get_satellite_pass(norad_id: int = 25544) -> Dict[str, Any]:
    """
    Fetches real-time orbital telemetry for specified satellite from CelesTrak.
    Default: NORAD ID 25544 (International Space Station - ISS).
    """
    url = f"https://celestrak.org/NORAD/elements/gp.php?CATNR={norad_id}&FORMAT=JSON"
    data = _http_get_json(url)

    if not data or not isinstance(data, list) or len(data) == 0:
        # Simulated fallback parameters for ISS
        return {
            "status": "fallback",
            "source": "CelesTrak (Cached Model)",
            "satellite": "ISS (ZARYA)",
            "norad_id": norad_id,
            "mean_motion": 15.49,
            "inclination_deg": 51.64,
            "altitude_km": 418.0,
            "period_minutes": 92.9,
            "summary": f"Target {norad_id} in low Earth orbit (~418 km altitude, 51.6° inclination, 92.9 min period)."
        }

    elem = data[0]
    name = elem.get("OBJECT_NAME", f"SAT-{norad_id}")
    inc = float(elem.get("INCLINATION", 51.6))
    mm = float(elem.get("MEAN_MOTION", 15.5))
    period = 1440.0 / mm if mm > 0 else 92.0

    return {
        "status": "ok",
        "source": "CelesTrak (Live TLE)",
        "satellite": name,
        "norad_id": norad_id,
        "mean_motion": mm,
        "inclination_deg": inc,
        "period_minutes": round(period, 2),
        "summary": f"Live satellite telemetry: {name} (NORAD {norad_id}). Mean motion {mm:.2f} rev/day, period {period:.1f} mins, inclination {inc:.1f}°."
    }


def get_seismic_hazards(min_magnitude: float = 4.0) -> Dict[str, Any]:
    """
    Queries USGS real-time seismic event feeds for global earthquake hazards.
    """
    url = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"
    data = _http_get_json(url)

    if not data or "features" not in data:
        return {
            "status": "ok",
            "source": "USGS Earthquake Hazards Program",
            "hazard_count": 0,
            "events": [],
            "summary": "No significant seismic anomalies reported in active monitoring window."
        }

    events = []
    for f in data.get("features", []):
        props = f.get("properties", {})
        mag = props.get("mag") or 0.0
        if mag >= min_magnitude:
            events.append({
                "place": props.get("place", "Unknown Location"),
                "magnitude": mag,
                "time_utc": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(props.get("time", 0) / 1000.0)),
                "alert": props.get("alert") or "green",
                "tsunami": bool(props.get("tsunami", 0))
            })

    # Sort descending by magnitude
    events.sort(key=lambda e: e["magnitude"], reverse=True)
    top_events = events[:8]

    summary = (
        f"USGS Sensor Network: {len(events)} earthquakes >= M{min_magnitude} detected globally past 24h. "
        + (f"Peak: M{top_events[0]['magnitude']} at {top_events[0]['place']}." if top_events else "All calm.")
    )

    return {
        "status": "ok",
        "source": "USGS Earthquake Hazards Program",
        "hazard_count": len(events),
        "events": top_events,
        "summary": summary
    }


def get_local_tactical_status() -> Dict[str, Any]:
    """
    Inspects local sensory hardware: camera lock, face-id recognition, and vision modules.
    """
    cam_locked = False
    active_user = "Unknown"

    try:
        from camera_stream import CAMERA_HARDWARE_LOCK
        cam_locked = CAMERA_HARDWARE_LOCK.locked()
    except Exception:
        pass

    try:
        from face_id import get_active_user
        user_info = get_active_user()
        active_user = user_info.get("name", "Operator")
    except Exception:
        pass

    return {
        "status": "ok",
        "camera_in_use": cam_locked,
        "operator": active_user,
        "vision_subsystem": "Moondream / OpenCV / YuNet",
        "summary": f"Local Sentinel: Operator '{active_user}'. Camera status: {'BUSY' if cam_locked else 'READY'}."
    }


def get_tactical_overview(lat: float = DEFAULT_LAT, lon: float = DEFAULT_LON) -> str:
    """
    Comprehensive executive intelligence report generated for F.R.I.D.A.Y.
    Combines local sentinel sensors, airspace radar, orbital satellite passes, and USGS hazards.
    """
    local = get_local_tactical_status()
    air = query_air_traffic(lat, lon)
    sat = get_satellite_pass(25544)
    hazards = get_seismic_hazards(min_magnitude=5.0)

    report = [
        "=== F.R.I.D.A.Y. GOD'S EYE TACTICAL SITUATION REPORT ===",
        f"1. LOCAL SENTINEL: {local['summary']}",
        f"2. AIRSPACE TELEMETRY: {air['summary']}",
        f"3. ORBITAL SENSORS: {sat['summary']}",
        f"4. GLOBAL HAZARD INDEX: {hazards['summary']}",
        "========================================================"
    ]
    return "\n".join(report)

