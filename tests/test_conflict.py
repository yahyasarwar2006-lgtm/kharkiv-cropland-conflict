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
