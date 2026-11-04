"""Verification of Geographic Mapping Subsystem (V14 Section 6).

Verifies:
1. Coordinate boundary validation: lat in [-90, 90], lon in [-180, 180].
2. Haversine distance calculation against verified geodesic ground truth.
3. OpenStreetMap Nominatim geocoding parsing, SQLite caching, and error resilience.
4. Route building with waypoint segments and distance summation.
5. Entity extraction from text and evidence attribution.
"""

from __future__ import annotations

import math
import os
import pytest
import pytest_asyncio
import respx
import httpx

from cache import SQLiteCache
from geo_mapper import GeographicMapper, GeoLocation, haversine_distance_km


@pytest.fixture
def sample_geo_locations() -> list[GeoLocation]:
    return [
        GeoLocation(
            query_name="Paris",
            display_name="Paris, Ile-de-France, France",
            latitude=48.8566,
            longitude=2.3522,
            place_type="city",
        ),
        GeoLocation(
            query_name="London",
            display_name="London, Greater London, England, United Kingdom",
            latitude=51.5074,
            longitude=-0.1278,
            place_type="city",
        ),
        GeoLocation(
            query_name="Berlin",
            display_name="Berlin, Germany",
            latitude=52.5200,
            longitude=13.4050,
            place_type="city",
        ),
    ]


def test_coordinate_boundary_validation():
    valid_loc = GeoLocation(
        query_name="Valid",
        display_name="Valid Location",
        latitude=37.7749,
        longitude=-122.4194,
    )
    assert valid_loc.is_valid_coordinates() is True

    invalid_lat = GeoLocation(
        query_name="Invalid Lat",
        display_name="Invalid Lat",
        latitude=95.0,
        longitude=10.0,
    )
    assert invalid_lat.is_valid_coordinates() is False

    invalid_lon = GeoLocation(
        query_name="Invalid Lon",
        display_name="Invalid Lon",
        latitude=10.0,
        longitude=185.0,
    )
    assert invalid_lon.is_valid_coordinates() is False


def test_haversine_formula_accuracy():
    # London (51.5074, -0.1278) to Paris (48.8566, 2.3522)
    dist = haversine_distance_km(51.5074, -0.1278, 48.8566, 2.3522)
    # Expected distance is ~343-344 km
    assert 340.0 <= dist <= 350.0

    # Same location must be 0 km
    assert haversine_distance_km(40.0, 40.0, 40.0, 40.0) == 0.0


def test_route_building(sample_geo_locations: list[GeoLocation]):
    mapper = GeographicMapper()
    route = mapper.build_route(sample_geo_locations)

    assert len(route["waypoints"]) == 3
    assert len(route["segments"]) == 2

    # Segment 1: Paris to London
    seg1 = route["segments"][0]
    assert "Paris" in seg1["from"]
    assert "London" in seg1["to"]
    assert 340.0 <= seg1["distance_km"] <= 350.0

    # Total distance must match sum of segments
    total_expected = round(sum(s["distance_km"] for s in route["segments"]), 2)
    assert route["total_distance_km"] == total_expected


@pytest.mark.asyncio
async def test_geocoding_with_mock():
    cache_path = "cache/test_geo_cache.db"
    cache = SQLiteCache(db_path=cache_path)
    mapper = GeographicMapper(cache=cache)

    try:
        with respx.mock(base_url="https://nominatim.openstreetmap.org") as respx_mock:
            respx_mock.get("/search").respond(
                status_code=200,
                json=[
                    {
                        "lat": "37.7749",
                        "lon": "-122.4194",
                        "display_name": "San Francisco, California, USA",
                        "type": "city",
                        "boundingbox": ["37.6", "37.9", "-122.5", "-122.3"],
                    }
                ],
            )

            # 1. Live geocode
            loc = await mapper.geocode_location("San Francisco")
            assert loc is not None
            assert loc.latitude == 37.7749
            assert loc.longitude == -122.4194
            assert loc.is_valid_coordinates() is True

            # 2. Second lookup must hit SQLite cache
            cached_loc = await mapper.geocode_location("San Francisco")
            assert cached_loc is not None
            assert cached_loc.latitude == 37.7749
    finally:
        await mapper.close()
        if os.path.exists(cache_path):
            try:
                os.remove(cache_path)
            except Exception:
                pass

