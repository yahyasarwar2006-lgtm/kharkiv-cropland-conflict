import pandas as pd
from shapely.geometry import box

from agridisrupt.conflict import count_events_near, load_ucdp_events


def test_load_ucdp_events_filters(tmp_path):
    csv = tmp_path / "ged.csv"
    pd.DataFrame({
        "id": [1, 2, 3, 4, 5],
        "country": ["Ukraine", "Ukraine", "Ukraine", "Russia", "Ukraine"],
        "date_start": ["2022-03-01", "2021-12-31", "2022-05-01", "2022-03-01", "2023-12-31"],
        "where_prec": [1, 1, 4, 1, 2],
        "latitude": [49.3] * 5,
        "longitude": [36.0] * 5,
        "best": [1] * 5,
    }).to_csv(csv, index=False)

    events = load_ucdp_events(csv, "Ukraine", ("2022-02-24", "2023-12-31"), max_where_prec=2)

    # 2 = before period, 3 = too imprecise, 4 = wrong country
    assert sorted(events["id"]) == [1, 5]


def test_count_events_near_uses_buffer(tmp_path):
    csv = tmp_path / "ged.csv"
    # a point at (0 deg E, 0 deg N) is far from a box near Kharkiv; one near 36E 49.3N is inside
    pd.DataFrame({
        "id": [1, 2], "country": ["Ukraine"] * 2, "date_start": ["2022-03-01"] * 2,
        "where_prec": [1, 1], "latitude": [49.3, 0.0], "longitude": [36.0, 0.0], "best": [1, 1],
    }).to_csv(csv, index=False)
    events = load_ucdp_events(csv, "Ukraine", ("2022-01-01", "2023-12-31"), max_where_prec=2)

    point = events.to_crs("EPSG:3035").geometry.iloc[0]
    far_box = box(point.x + 15_000, point.y, point.x + 20_000, point.y + 5_000)  # 15 km away

    assert count_events_near(events, far_box, "EPSG:3035", buffer_m=10_000) == 0
    assert count_events_near(events, far_box, "EPSG:3035", buffer_m=20_000) == 1


def test_season_exposure_window_and_buffer(tmp_path):
    import geopandas as gpd
    from agridisrupt.conflict import exposure_group, load_acled_events, season_exposure
    csv = tmp_path / "acled.csv"
    pd.DataFrame({
        "event_id_cnty": ["a", "b", "c", "d", "e"],
        "event_date": ["2022-02-01", "2022-03-01", "2022-11-15", "2023-05-01", "2022-03-01"],
        "event_type": ["Battles", "Battles", "Battles", "Protests", "Battles"],
        "latitude": [49.3, 49.3, 49.3, 49.3, 49.3], "longitude": [36.0] * 5,
        "geo_precision": [1, 1, 1, 1, 3],
    }).to_csv(csv, index=False)
    events = load_acled_events(csv, ["Battles"], 2, bounds=(30, 45, 40, 55))
    assert sorted(events["event_id_cnty"]) == ["a", "b", "c"]          # protest and imprecise dropped
    p = events.to_crs("EPSG:3035").geometry.iloc[0]
    cells = gpd.GeoDataFrame({"cell_id": ["near", "far"]},
                             geometry=[box(p.x + 3000, p.y, p.x + 8000, p.y + 5000),     # 3 km away
                                       box(p.x + 20000, p.y, p.x + 25000, p.y + 5000)], crs="EPSG:3035")
    exp = season_exposure(events, cells, 5000, [2022], "2022-02-24", "10-31").set_index("cell_id")
    assert exp.loc["near", "events"] == 1      # Feb (pre-war) and Nov (after season) excluded
    assert exp.loc["far", "events"] == 0
    assert list(exposure_group(pd.Series([0, 3, 10]), 0, 10)) == ["low", "some", "high"]


def test_exposure_history_labels():
    from agridisrupt.conflict import exposure_history
    exp = pd.DataFrame({
        "cell_id": ["e", "e", "e", "p", "p", "p", "r", "r", "r", "o", "o", "o"],
        "year": [2022, 2023, 2024] * 4,
        "events": [50, 3, 9,   20, 15, 10,   0, 0, 0,   12, 2, 30],
    })
    label = exposure_history(exp, 2022, [2023, 2024], high_min=10)
    assert label.to_dict() == {"e": "ended", "o": "other", "p": "persistent", "r": "reference"}
