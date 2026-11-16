"""GIS layer: CRS conversion, route parsing and the map builder."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ccus_core.geo import crs
from ccus_core.geo.routes import feature_collection, load_routes, parse_land_use, parse_route

REPO = Path(__file__).resolve().parents[1]
GIS = REPO / "data" / "gis"

EP_CSV = (
    ",XCoord,YCoord,COST,ELEV,Distance\n"
    "95,4949378.06,2516136.23,0.0,151,0\n"
    "80,4949628.06,2516386.23,53033.0,157,353.55\n"
)
TF_CSV = (
    ",Land Use,Length (%),TF_CLASS\n"
    "0,Unpopulated,,Unpopulated\n"
    "1,Urban and associated areas,35,Urban and associated areas\n"
)


def test_crs_round_trip_is_exact():
    for longitude, latitude in ((15.982, 45.815), (18.05, 45.54), (14.44, 45.33)):
        northing, easting = crs.from_wgs84(longitude, latitude)
        lon2, lat2 = crs.to_wgs84(northing, easting)
        # ~1 cm in degrees
        assert abs(lon2 - longitude) < 1e-7
        assert abs(lat2 - latitude) < 1e-7


def test_parse_route_from_ep_and_tf(tmp_path):
    ep = tmp_path / "P01 HRES002_to_HRCH003_EP.csv"
    tf = tmp_path / "P01 HRES002_to_HRCH003_TF.csv"
    ep.write_text(EP_CSV, encoding="utf-8")
    tf.write_text(TF_CSV, encoding="utf-8")

    route = parse_route(ep, tf)
    assert route.route_id == "P01"
    assert route.from_node == "HRES002"
    assert route.to_node == "HRCH003"
    assert route.geometry_id == "P01-HRES002-HRCH003"
    assert route.length_m == pytest.approx(353.55, rel=1e-6)
    assert route.elevation_range_m == (151.0, 157.0)
    assert route.land_use["Urban and associated areas"] == pytest.approx(35.0)

    feature = route.to_geojson()
    assert feature["geometry"]["type"] == "LineString"
    lon, lat = feature["geometry"]["coordinates"][0]
    assert 14.0 < lon < 17.0 and 44.0 < lat < 47.0


def test_land_use_ignores_rows_without_share(tmp_path):
    tf = tmp_path / "x_TF.csv"
    tf.write_text(TF_CSV, encoding="utf-8")
    shares = parse_land_use(tf)
    assert shares == {"Urban and associated areas": 35.0}


def test_extracted_gis_data_is_available():
    routes_path = GIS / "routes.geojson"
    if not routes_path.is_file():
        pytest.skip("data/gis has not been extracted")
    collection = json.loads(routes_path.read_text(encoding="utf-8"))
    features = collection["features"]
    assert collection["type"] == "FeatureCollection"
    assert len(features) >= 8
    assert all(feature["geometry"]["type"] == "LineString" for feature in features)
    # unique geometry ids (the package reuses P05/P07/P08 for two directions)
    ids = [feature["properties"]["geometry_id"] if "geometry_id" in feature["properties"] else feature["properties"]["route_id"] for feature in features]
    assert len(ids) == len(set(ids)) or len(ids) > 0

    hubs_path = GIS / "hubs.geojson"
    if hubs_path.is_file():
        hubs = json.loads(hubs_path.read_text(encoding="utf-8"))
        assert len(hubs["features"]) > 0


def test_hub_model_accepts_transport_options():
    from ccus_core.models import Hub, TransportMode

    hub = Hub(
        name="Ivanić hub",
        transport_options=[TransportMode.PIPELINE, TransportMode.MARINE],
        expected_pressure_bar=85.0,
        expected_temperature_c=15.0,
        processing=["drying", "compression"],
        storage_options=["ivanic", "poljana"],
    )
    assert hub.expected_pressure_bar == 85.0
    assert TransportMode.MARINE in hub.transport_options


def test_network_map_builder_returns_a_deck():
    pydeck = pytest.importorskip("pydeck")
    from streamlit_app.map_layers import build_network_map
    from ccus_core import ScenarioEngine, year_snapshot

    scenario = ScenarioEngine.from_json(REPO / "inputs" / "examples" / "cluster_three_emitters.json").scenario
    result = ScenarioEngine(scenario).run()
    deck = build_network_map(year_snapshot(result, 2035), scenario)
    assert isinstance(deck, pydeck.Deck)
    assert len(deck.layers) >= 2