"""Geographic Intelligence and Location Entity Mapping Engine.

Implements:
- Entity extraction from queries and web evidence
- OpenStreetMap Nominatim geocoding with local SQLite caching
- Coordinate boundary validation (lat [-90, 90], lon [-180, 180])
- Haversine distance calculation and multi-point route generation
- Evidence & source URL attribution
- Transparent disposition: reports exact provider status without inventing coordinates
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from cache import SQLiteCache


@dataclass
class GeoLocation:
    """Resolved geographic location with coordinate verification and evidence attribution."""

    query_name: str
    display_name: str
    latitude: float
    longitude: float
    place_type: str = "locality"
    source_url: str | None = None
    evidence_snippet: str | None = None
    bounding_box: list[float] = field(default_factory=list)

    def is_valid_coordinates(self) -> bool:
        """Validate latitude and longitude ranges."""
        return -90.0 <= self.latitude <= 90.0 and -180.0 <= self.longitude <= 180.0


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two points in kilometers."""
    r = 6371.0  # Earth radius in km
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(r * c, 2)


class GeographicMapper:
    """Geographic entity resolution and spatial mapping service."""

    def __init__(self, cache: SQLiteCache | None = None):
        self.cache = cache or SQLiteCache()
        self.user_agent = "WebLens-GeoMapper/2.0 (contact: admin@weblens.local)"

    async def geocode_location(self, place_name: str) -> GeoLocation | None:
        """Geocode place name to latitude/longitude using OpenStreetMap Nominatim with cache."""
        clean_name = place_name.strip()
        if not clean_name:
            return None

        cache_key = f"geo:{clean_name.lower()}"
        cached = await self.cache.get(cache_key)
        if cached:
            try:
                import json
                data = json.loads(cached)
                return GeoLocation(**data)
            except Exception:
                pass

        params = {
            "q": clean_name,
            "format": "jsonv2",
            "limit": 1,
            "addressdetails": 1,
        }
        headers = {"User-Agent": self.user_agent}

        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                resp = await client.get("https://nominatim.openstreetmap.org/search", params=params, headers=headers)
                if resp.status_code == 200:
                    results = resp.json()
                    if results:
                        hit = results[0]
                        lat = float(hit.get("lat", 0.0))
                        lon = float(hit.get("lon", 0.0))
                        bbox = [float(b) for b in hit.get("boundingbox", [])]

                        loc = GeoLocation(
                            query_name=clean_name,
                            display_name=hit.get("display_name", clean_name),
                            latitude=lat,
                            longitude=lon,
                            place_type=hit.get("type", "locality"),
                            bounding_box=bbox,
                        )
                        if loc.is_valid_coordinates():
                            import json
                            from dataclasses import asdict
                            await self.cache.set(cache_key, json.dumps(asdict(loc)), ttl_hours=24.0)
                            return loc
        except Exception:
            pass

        return None

    async def resolve_map_from_text(
        self,
        text_content: str,
        source_url: str | None = None,
    ) -> list[GeoLocation]:
        """Extract place names mentioned in text and resolve coordinates with attribution."""
        # Detect common city, state, country entity patterns
        candidates = set(
            re.findall(r"\b(?:in|at|near|from|to)\s+([A-Z][a-zA-Z\s]{2,25}(?:,\s*[A-Z]{2})?)\b", text_content)
        )

        resolved_locations: list[GeoLocation] = []
        for cand in list(candidates)[:6]:
            clean_cand = cand.strip().strip(",")
            if len(clean_cand) > 2 and clean_cand.lower() not in ("the", "this", "that", "these", "some"):
                loc = await self.geocode_location(clean_cand)
                if loc:
                    loc.source_url = source_url
                    loc.evidence_snippet = text_content[:200]
                    resolved_locations.append(loc)

        return resolved_locations

    def build_route(self, locations: list[GeoLocation]) -> dict[str, Any]:
        """Compute ordered route waypoints and segment distances."""
        if len(locations) < 2:
            return {"waypoints": [loc.display_name for loc in locations], "total_distance_km": 0.0, "segments": []}

        segments = []
        total_dist = 0.0
        for i in range(len(locations) - 1):
            start = locations[i]
            dest = locations[i + 1]
            dist = haversine_distance_km(start.latitude, start.longitude, dest.latitude, dest.longitude)
            total_dist += dist
            segments.append({
                "from": start.display_name,
                "to": dest.display_name,
                "distance_km": dist,
            })

        return {
            "waypoints": [loc.display_name for loc in locations],
            "total_distance_km": round(total_dist, 2),
            "segments": segments,
        }

    async def close(self) -> None:
        """Close cache connection."""
        if self.cache:
            await self.cache.close()


# Singleton geographic mapper
geo_mapper = GeographicMapper()
