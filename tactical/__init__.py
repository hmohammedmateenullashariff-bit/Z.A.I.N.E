"""
tactical/
God's Eye Geospatial OSINT and Situational Intelligence for Project-Z (Z.A.I.N.E).
Managed under the tactical authority of F.R.I.D.A.Y.
Integrates bilawalsidhu/gods-eye-view open-source spatial data feeds:
- ADS-B live airspace flights (OpenSky)
- Satellite orbital trajectories (CelesTrak / ISS)
- USGS real-time seismic and earthquake hazards
- Local computer vision and biometric sensor fusion
"""

from tactical.gods_eye_bridge import (
    query_air_traffic,
    get_satellite_pass,
    get_seismic_hazards,
    get_local_tactical_status,
    get_tactical_overview
)

__all__ = [
    "query_air_traffic",
    "get_satellite_pass",
    "get_seismic_hazards",
    "get_local_tactical_status",
    "get_tactical_overview"
]

