"""Kharkiv cropland & conflict — Streamlit dashboard (Stage 10).

Shows only historical, 5 km, per-season aggregates (ethics: no front-line tracking). Exposure appears as a group
(low / some / high), never as event counts or points. Run from the repo root:
    streamlit run dashboard/app.py
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")   # draw off-screen: the macOS GUI backend crashes outside the main thread
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import pydeck as pdk  # noqa: E402
import streamlit as st  # noqa: E402
import yaml  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load((ROOT / "configs" / "kharkiv_v1.yaml").read_text())
ASSETS = ROOT / CONFIG["dashboard"]["assets_dir"]
FIGS = ROOT / CONFIG["paths"]["reports_figures"]
PARTS = {"spring": "spring (1 Apr – 9 Jun)", "peak": "summer peak (10 Jun – 4 Aug)", "late": "late season (5 Aug – Oct)"}
GROUP_COLOURS = {"low": [207, 227, 207], "some": [246, 213, 142], "high": [192, 80, 77]}
HISTORY_COLOURS = {"reference": [207, 227, 207], "ended": [46, 117, 182], "persistent": [192, 80, 77],
                   "other": [220, 220, 220]}

st.set_page_config(page_title="Kharkiv cropland & conflict", page_icon="🌾", layout="wide")


# cache_resource shares the loaded tables (the app never modifies them). cache_data hands out pickled copies,
# and those crashed pandas 3 / pyarrow text columns on reruns in Streamlit's script thread.
@st.cache_resource
def load():
    cells = json.loads((ASSETS / "cells.geojson").read_text())
    seasons = pd.read_csv(ASSETS / "cell_seasons.csv")
    curves = pd.read_csv(ASSETS / "cell_curves.csv")
    oblast = pd.read_csv(ASSETS / "curves.csv")
    # season curve per year, one column per year
    order = oblast.sort_values("period")["start"].unique()
    wide = oblast.pivot(index="start", columns="year", values="all_cells").loc[order]
    wide.columns = [str(c) for c in wide.columns]
    return cells, seasons, curves, wide


def figure(name: str, caption: str):
    path = FIGS / name
    if path.exists():
        st.image(str(path), caption=caption, use_container_width=True)


def colour_scale(values: pd.Series, limit: float, cmap: str = "RdYlGn") -> list:
    cm = matplotlib.colormaps[cmap]
    scaled = ((values.clip(-limit, limit) + limit) / (2 * limit)).fillna(-1)
    return [[230, 230, 230] if v < 0 else [int(255 * c) for c in cm(v)[:3]] for v in scaled]


cells, seasons, curves, season_curves = load()

st.title("🌾 Cropland and conflict in Kharkiv oblast, 2018–2024")
st.caption("Sentinel-2 greenness (NDVI) for 1,192 cropland squares of 5 × 5 km, adjusted for weather with a model "
           "trained on pre-war years, compared with nearby conflict events. Historical and aggregated only.")

tab_story, tab_map, tab_method = st.tabs(["📖 Findings", "🗺️ Map explorer", "🔬 Method & limits"])

with tab_story:
    st.header("What the data show")
    st.markdown(
        "**In short:** cropland close to conflict had a **lower summer peak in 2022** and was **greener than "
        "expected in the springs of 2023 and 2024** — a pattern consistent with disrupted sowing followed by weedy or "
        "fallow fields. Where fighting ended after 2022, spring greenness was back to normal by 2024. The association "
        "survives three robustness checks, but it is **an association, not proof of cause**.")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("2022 summer peak, near vs far from fighting", "−0.05 NDVI", help="High-exposure (10+ events ≤ 5 km) "
              "minus low-exposure (0 events) squares, weather-adjusted. 95% interval −0.073 to −0.028.")
    c2.metric("2023 spring, near vs far", "+0.08 NDVI", help="95% interval +0.059 to +0.101.")
    c3.metric("Weather model vs simple baseline", "−4% to −8% error", help="Mean absolute error on held-out pre-war "
              "years 2020 and 2021 (gradient boosting vs seasonal average).")
    c4.metric("Robustness checks passed", "31 / 32", help="Nearby comparison squares, 10 km distance, no weather "
              "adjustment. Only the greener 2024 summer peak failed (with nearby squares).")

    st.subheader("1 · Near vs far from fighting, every year")
    figure("exposure_event_study.png", "Weather-adjusted greenness of squares with 10+ conflict events within 5 km in "
           "2022 minus squares with none. Before the war (2018–21) the gap should be near zero; bars = 95% intervals.")
    st.subheader("2 · Where fighting ended: back to normal?")
    figure("recovery_gaps.png", "Squares where fighting ended after 2022 (blue) and where it continued (red), compared "
           "with squares never near fighting. Shaded band = the pre-war range.")
    st.subheader("3 · Does it hold under other reasonable choices?")
    figure("robustness_forest.png", "Each main result under the main setting and three checks (95% intervals).")
    st.subheader("4 · The season, year by year")
    st.line_chart(season_curves, x_label="14-day period starting", y_label="median NDVI over cropland squares")
    st.caption("2022 and 2023 stay green unusually late, but autumn 2022 was also very wet — the weather model and "
               "the near/far comparison are needed to separate the two.")

with tab_map:
    left, right = st.columns([1, 3])
    with left:
        layer = st.radio("Show", ["Weather-adjusted anomaly", "Anomaly vs pre-war average (no weather)",
                                  "Conflict exposure group", "Exposure history 2022–24", "Peak greenness",
                                  "Cropland share"])
        year = st.select_slider("Season", options=sorted(seasons["year"].unique()), value=2022,
                                disabled=layer in ("Exposure history 2022–24", "Cropland share"))
        part = st.radio("Part of the season", list(PARTS), format_func=PARTS.get, index=1,
                        disabled=not layer.startswith(("Weather", "Anomaly")))
    d = seasons[seasons["year"] == year].set_index("cell_id")
    props = {}
    if layer.startswith("Weather"):
        values, colours, legend = d[f"adj_{part}"], colour_scale(d[f"adj_{part}"], 0.2), \
            "green = greener than the weather predicts, red = browner (±0.2 NDVI)"
    elif layer.startswith("Anomaly"):
        values, colours, legend = d[f"raw_{part}"], colour_scale(d[f"raw_{part}"], 0.2), \
            "green = greener than the 2018–21 average for that square, red = browner (±0.2 NDVI)"
    elif layer.startswith("Conflict"):
        values = d["exposure"]
        colours = [GROUP_COLOURS[g] for g in values]
        legend = "conflict events within 5 km this season (ACLED): grey-green = none, yellow = 1–9, red = 10+"
    elif layer.startswith("Exposure history"):
        values = seasons.drop_duplicates("cell_id").set_index("cell_id")["history"]
        colours = [HISTORY_COLOURS[h] for h in values]
        legend = "blue = heavy fighting in 2022 that ended; red = heavy in 2022–24; green = never near fighting"
    elif layer == "Peak greenness":
        values = d["peak_ndvi"]
        colours = colour_scale(values - 0.7, 0.2, "YlGn")
        legend = "highest 14-day NDVI of the season (light = 0.5 or less, dark = 0.9)"
    else:
        values = pd.Series({f["properties"]["cell_id"]: f["properties"]["cropland_fraction"] for f in cells["features"]})
        colours = colour_scale(values - 0.65, 0.35, "YlOrBr")
        legend = "share of the square that is cropland (WorldCereal 2021)"
    colour_of = dict(zip(values.index, colours))
    features = []
    for f in cells["features"]:
        cid = f["properties"]["cell_id"]
        v = values.get(cid)
        features.append({**f, "properties": {**f["properties"], "fill": colour_of.get(cid, [230, 230, 230]),
                                             "value": v if isinstance(v, str) else
                                             ("–" if pd.isna(v) else f"{v:+.3f}" if layer.startswith(("W", "A"))
                                              else f"{v:.2f}")}})
    deck = pdk.Deck(
        layers=[pdk.Layer("GeoJsonLayer", {"type": "FeatureCollection", "features": features}, id="cells",
                          get_fill_color="properties.fill", get_line_color=[255, 255, 255], line_width_min_pixels=0.3,
                          pickable=True, auto_highlight=True)],
        initial_view_state=pdk.ViewState(latitude=49.6, longitude=36.6, zoom=6.6),
        map_style=None, tooltip={"text": "{cell_id}\n{value}"})
    with right:
        st.caption(legend + ". Click a square to see its season curves.")
        event = st.pydeck_chart(deck, on_select="rerun", selection_mode="single-object", key="map", height=520)
    picked = event.selection.objects.get("cells", []) if event and event.selection else []
    cell = picked[0]["properties"]["cell_id"] if picked else None
    if cell:
        c = curves[curves["cell_id"] == cell]
        st.subheader(f"Square {cell}: observed greenness vs what the weather predicts")
        fig, axes = plt.subplots(1, 7, figsize=(16, 2.6), sharey=True)
        for ax, (y, g) in zip(axes, c.groupby("year")):
            ax.plot(g["period"], g["ndvi"], "o-", ms=3, color="#2e7d32", label="observed")
            ax.plot(g["period"], g["predicted"], "--", color="grey", label="predicted normal")
            ax.set_title(str(y), fontsize=9)
            ax.set_xticks([0, 7, 14], ["Apr", "Jul", "Oct"], fontsize=7)
            ax.grid(alpha=0.3)
        axes[0].legend(fontsize=7)
        axes[0].set_ylabel("NDVI")
        fig.tight_layout()
        st.pyplot(fig)
        st.dataframe(seasons[seasons["cell_id"] == cell].set_index("year").drop(columns=["cell_id"]),
                     use_container_width=True)

with tab_method:
    st.header("How this was done")
    st.markdown("""
**Data.** Sentinel-2 L2A satellite images (Copernicus, via Microsoft Planetary Computer) → greenness (NDVI) per 5 km
cropland square and 14-day period, April–October 2018–2024, with a cloud mask and a rule that at least 50% of a
square's cropland must be cloud-free. Cropland from ESA WorldCereal 2021. Weather from ERA5-Land. Conflict events
from ACLED (cross-checked with UCDP GED).

**Normal greenness.** A gradient-boosting model learns, from the pre-war years only (2018–2021), how far greenness
deviates from each square's usual season given the weather. It was tested forward in time (train 2018–20 → test
2021) and beat a simple seasonal average by 4–8%; it explains about 13% of year-to-year deviations.

**Conflict exposure.** Battles, shelling, strikes and violence against civilians located to a town or better,
counted within 5 km of each square per growing season. Low = no events, high = 10 or more.

**Honesty rules.** All definitions for the conflict comparison, recovery and robustness checks were written down and
saved *before* any result was looked at. Results that did not hold are reported.

**Limits.**
- High- and low-exposure squares lie in different parts of the region; comparisons with nearby squares shrink the
  differences by a fifth to a third.
- The 2022 summer-peak result is not reproduced with UCDP data (fatal events only).
- The model of normal is off for the whole region in 2022–2023, even far from fighting, so only relative
  comparisons (near vs far) are used.
- Greener is not always better: abandoned fields can look greener because of weeds.
- **No causal claim** is made: the results are associations.

**Ethics.** Historical (2018–2024) and aggregated to 5 km squares and whole seasons. No event locations, no
front-line tracking.

**Sources & licences.** Copernicus Sentinel-2 data (2018–2024); ERA5-Land, Copernicus Climate Change Service
(CC BY 4.0); ESA WorldCereal 2021 (CC BY 4.0); Armed Conflict Location & Event Data (ACLED), acleddata.com;
UCDP Georeferenced Event Dataset 26.1.
""")
    st.caption("Portfolio research project · BSc Business Analytics, University of Amsterdam · code and full write-up "
               "in the project repository.")
