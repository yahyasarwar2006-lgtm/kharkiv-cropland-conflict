# Experiment log

One entry per experiment. Never fabricate results — if something wasn't run, it isn't here.

Template for each entry:

```
## Experiment N — <short title>
Date:
Hypothesis:
Data used:
Method:
Result:
Interpretation:
Limits / caveats:
```

## Experiment 1 — Pilot NDVI time series (feasibility)
Date started: 25 Sep 2026 · Run 29 Sep 2026 · Status: **done — 3 of 4 checks PASS, check 3 FAIL (by the
pre-set rule). Decision (29 Sep 2026): GO to Stage 3.** Check 3 stays recorded as FAIL; future offset
checks compare bare-soil (early-April) levels instead of whole-season medians.

Hypothesis:
Clean, believable 14-day cropland NDVI curves can be built cheaply for a 20×20 km block,
Apr–Oct 2019–2023, on an 8 GB laptop.

Data used:
- Sentinel-2 L2A (B04, B08, SCL), Microsoft Planetary Computer.
- ESA WorldCereal 2021 v100 temporary-crops map (Zenodo 7875105, CC BY 4.0), zones 22096/22190/22194.
- UCDP GED 26.1 (CC BY 4.0), used only to choose a low-exposure pilot block.

Pilot block selection (rule fixed in `configs/kharkiv_v1.yaml` before counting events or seeing NDVI):
- Cropland share per 5 km cell computed for all 1,392 cells (median 69%; 1,192 cells ≥ 30%).
  Sanity check: median 448,922 valid WorldCereal pixels per cell vs ~450,000 expected → no double counting.
- Block A = most cropland-dense 4×4 block in the grid-CRS south-west quadrant: 83% cropland,
  ~35.9–36.2°E, 49.2–49.4°N. 4 UCDP events (where_prec ≤ 2) within 10 km, 24 Feb 2022–31 Dec 2023 (2 exact).
- Block B = same rule restricted to the western half of that quadrant: 69% cropland (cells 43–85%),
  ~35.2–35.6°E, 49.6–49.9°N. 0 events within 10 km.
- Rule: fewer events wins → **Block B chosen**.
- Note: the "south-west quadrant" is defined in EPSG:3035 axes, rotated ~20° from true north at Kharkiv.

Checks (decided before looking at results, in the Stage-0 research design):
1. Share of 14-day composites with ≥ 50% valid cropland pixels in May–Aug (target: most of them).
2. Curves show a recognisable crop season (spring green-up, summer peak, harvest drop).
3. No step change at 1 Jan 2022 / 25 Jan 2022 (offset check).
4. Run time and data volume manageable on the laptop.

Scene inventory (29 Sep 2026, metadata only, no pixels): 547 scenes, all tile 36UXA, ~85 dates/season.
2022–2023 contain reprocessed duplicates (same date, baselines 04.00+05.10 / 05.09+05.10) → keep the
highest baseline per date. All pre-2022 scenes are baseline 02.12/03.00, all later ones ≥ 04.00, so the
date-based offset rule matches the baselines here (a guard stops the run if they ever disagree).

How the checks are scored (written 29 Sep 2026, before any composite was computed):
1. Valid data: a cell-composite is "valid" if ≥ 50% of its cropland pixels have a clear value. For
   composites starting May–Aug, PASS if more than half of cell-composites are valid in every year.
2. Crop season: PASS if, every year, the block-average curve peaks in a composite starting May–Aug and
   drops by ≥ 0.2 NDVI from that peak to the lowest Sep–Oct composite. Curves are also inspected visually.
3. Offset: 2022–23 are computed both with and without the offset correction. PASS if the corrected
   2022–23 seasonal medians fall within the 2019–21 range ± 0.05 NDVI; the uncorrected version is shown
   to demonstrate the size of the jump the correction removes. (Weather also moves these levels, so this
   check can flag a problem but cannot fully prove its absence.)
4. Resources: PASS if the full 5-season run takes < 2 h and peak memory < 4 GB (half of 8 GB).
("Block-average curve" in checks 2–3 = mean over the cells whose composite is valid under check 1.
Scoring code: `scripts/evaluate_pilot.py`, written before the first full run finished.)

Method (`scripts/run_pilot_timeseries.py`, `scripts/evaluate_pilot.py`):
- Per season Apr–Oct: all scenes over the block; drop scenes with whole-tile cloud > 80%; keep one scene per
  date (highest baseline); guard that date rule and baseline agree on the offset (never triggered).
- Per scene: read only the block window of B04/B08/SCL (native UTM 10 m grid, tile 36UXA; SCL nearest-resampled
  to 10 m), correct the offset, NDVI, keep SCL classes 4/5 only.
- Cropland: WorldCereal 2021 nearest-resampled onto the same 10 m grid; only crop pixels are used.
- 14-day periods from 1 Apr (15 per season, last one 14–31 Oct); per-pixel median over the period's scenes;
  per cell: median NDVI of clear crop pixels and the clear share. 2022–23 also computed without the offset fix.
- 307 scenes used: 63 / 65 / 68 / 53 / 58 (2019–2023).

Result (29 Sep 2026):
1. Valid data — PASS. Share of May–Aug cell-composites with ≥ 50% clear cropland: 1.000 / 0.992 / 0.945 /
   0.977 / 0.984. Only a handful of composites fall below 50% all season (mid-Apr 2020/21, early Apr 2023,
   mid-Sep 2019/22).
2. Crop season — PASS. Block-average peak 0.73–0.81 (Jun 2019, Jul 2020–23); drop to the Sep–Oct minimum
   0.52–0.59 every year. Curves show a clear spring green-up, summer peak and late-summer decline.
3. Offset — **FAIL by the pre-set rule.** Seasonal median of the block-average curve: 0.332 / 0.323 / 0.320 for
   2019–21 → allowed 0.270–0.382; 2022 = 0.389 (outside by 0.007), 2023 = 0.343 (inside). Without the offset fix
   2022–23 would be 0.228 / 0.190, far outside.
4. Resources — PASS. 31.2 min in total, peak memory 1.78 GB. (A first attempt with dask `chunks=True` took
   ~98 s per scene instead of ~7 s and was stopped; one run hung on a stalled download → HTTP timeouts added.)
Figures: `reports/figures/pilot_ndvi_curves.png`, `reports/figures/pilot_valid_share.png`.

Post-hoc diagnostic for check 3 (NOT pre-registered; added after seeing the FAIL):
- Early April (1–14 Apr, before green-up, mostly bare soil — where a leftover offset step would show most
  directly): 0.181 / 0.182 / 0.184 in 2019–21 vs 0.175 corrected in 2022 (0.088 uncorrected). 2023 early April
  was too cloudy to compare.
- Late October (14–31 Oct): 0.207 / 0.179 / 0.241 in 2019–21 vs 0.263 (2022) and 0.214 (2023) corrected
  (0.120 / 0.102 uncorrected).
- 2022's higher seasonal median comes from the second half of the season: the 2022–23 curves stay high later
  into August–September. 2022 also lacks its mid-September composite (clouds), which likely removed a low value.

Interpretation:
- The pipeline produces clean, believable cropland NDVI curves on the laptop, fast enough to scale up.
- The offset correction is necessary (uncorrected 2022–23 values are roughly halved) and, on the post-hoc
  bare-soil comparison, shows no sign of a leftover step. Check 3 failed because the seasonal median is
  sensitive to season *shape*: 2022–23 had later/longer green seasons. Lesson: the pre-set check 3 mixed an
  offset test with real between-year variation; a better offset test uses bare-soil periods.
- The later/longer 2022–23 seasons in this low-exposure block are an observation only. Candidate explanations
  include weather, a different crop mix (rotation), or country-wide disruptions after Feb 2022 (fuel, labour,
  logistics). This experiment cannot tell them apart; ERA5-Land (Stage 3) and the climate-adjusted model
  (Stages 5–6) are meant to.

Limits / caveats (so far):
- UCDP GED records only events with ≥ 1 death → exposure counts are a lower bound; ACLED check pending.
- UCDP where_prec 2 locations can be off by up to 25 km, more than the 10 km buffer.
- WorldCereal is a single-year (2021) map; crop rotation means the mask is approximate for other years.
- One 20×20 km block (16 cells), one Sentinel-2 tile; results may not hold for the whole oblast.
- Seasonal medians use only valid composites, and which periods are missing differs by year.
- The whole-tile 80% cloud filter and SCL classes 4/5 are processing choices, not tested alternatives.

## Experiment 1b — 10 m vs 20 m Sentinel-2 reading (Stage 3 set-up)
Date: 2 Oct 2026 · Status: **done — all 4 criteria PASS. Decision (2 Oct 2026): use 20 m for the
whole oblast.** (Criteria written before any 20 m result existed.)

Question: for 5 km cell composites, does reading Sentinel-2 at 20 m (the files' built-in half-resolution
"overview" of B04/B08; SCL is natively 20 m) give practically the same NDVI as 10 m, at much lower cost?
Why: the whole-oblast run is ~75x the pilot area over 7 seasons; at 10 m that is an estimated 50–60 h.

Data: pilot block B, seasons 2021 and 2022 (both sides of the 25 Jan 2022 offset change).
10 m results = existing Experiment 1 output; 2021 is also re-run at 10 m today for a same-day timing.

Pass criteria (decided before seeing results), on cell-composites valid (≥ 50% clear cropland) at both resolutions:
1. Agreement: median |NDVI(20 m) − NDVI(10 m)| ≤ 0.02 and 95th percentile ≤ 0.05.
2. Curves: block-average NDVI differs by ≤ 0.02 in every period.
3. Valid data: share of valid cell-composites differs by ≤ 5 percentage points.
4. Speed: 20 m run time ≤ 50% of the same-day 10 m run time for 2021.
Decision rule: all four pass → propose 20 m for the whole oblast; otherwise stay at 10 m.

Result (2 Oct 2026, `scripts/compare_resolutions.py`; 430 of 480 cell-composites valid at both resolutions):
1. Agreement — PASS. Median |diff| 0.0013, 95th percentile 0.0100; mean signed difference 0.0000 (no bias).
2. Curves — PASS, narrowly. Largest block-average gap 0.018 (limit 0.02), in one partly cloudy composite
   (13–26 May 2022, ~74% clear: the cloud mask cuts slightly different pixels at 20 m). All other periods ≤ 0.006.
3. Valid data — PASS. 89.6% valid cell-composites at both resolutions.
4. Speed — PASS. 2021 season: 4.7 min at 10 m vs 1.7 min at 20 m (ratio 0.36, ~2.8x faster, not the ~4x
   I had estimated); peak memory 1.6 → 0.9 GB.
Figure: `reports/figures/resolution_test_10m_vs_20m.png`.

Interpretation: at 5 km cells, 20 m reading gives practically the same NDVI as 10 m, with no bias, at about a
third of the time. Differences concentrate in partly cloudy composites.
Limits: one 20×20 km block and two seasons; the files do not record how their 20 m overviews were computed;
field-level detail (e.g. narrow strips, field edges) is coarser at 20 m — irrelevant for 5 km cell
medians, but would matter for any later field-level work.

## Data notes — Stage 3 (not an experiment; recorded for the write-up)
- ERA5-Land (2015–2024) downloaded 6 Oct 2026: temperature + soil moisture as hourly half-year chunks (daily
  means computed locally), rain as 00 UTC values (= previous day's total). `data/processed/climate_features.csv`:
  1192 cells x 2018–2024 x 15 periods = 125,160 rows, no missing values. Medians: 18.1 °C, soil moisture 0.24,
  17 mm rain per 14 days.
- Caveat: averaged over the box, ERA5-Land gives ~736 mm of rain in 2016, above the ~500–600 mm/year the author
  expected for Kharkiv (from memory, not verified). Reanalysis rainfall amounts can be biased; the models use
  relative variation (wetter/drier than usual), which is less affected. Each 5 km cell takes the nearest
  0.1° (~11 x 7 km) ERA5-Land point, so neighbouring cells often share weather values.
- Temperature anomaly baseline = all years 2015–2024 (decided 1 Oct 2026).
- Whole-oblast Sentinel-2 NDVI at 20 m finished 9 Oct 2026: 70 pieces (10 tiles x 7 years), 4,684 scenes,
  125,160 composites = 1192 cells x 7 years x 15 periods, no duplicate keys. 1.8% of composites have no NDVI
  (no clear scene in that 14-day period); median usable cropland share per composite 100%.
- The first pass skipped 4 unreadable scenes (3 pieces). Re-running those 3 pieces on 9 Oct read all 4, so 0
  scenes are skipped. Effect of the missing scenes (old vs new composites): 2019_36UYA 12 of 2,460 changed
  (max |diff| 0.009); 2020_37UCR 394 of 3,060 (max 0.069, median of changed 0.005); 2020_37UDR 56 of 840
  (max 0.051, median of changed 0.014). Lesson: one missing scene can move some 14-day medians by up to ~0.07
  NDVI, so skipped scenes are worth re-fetching rather than ignoring.
- Panel built 23 Oct 2026 (`scripts/build_panel.py`): NDVI composites + climate features joined on
  (cell_id, year, period), validated one-to-one → `data/processed/panel.csv`, 125,160 rows x 14 columns.
  1.8% of rows have no NDVI; climate has no missing values. NDVI median 0.33, IQR 0.22–0.57, max 0.92.
- 249 composites have NDVI < 0 (min −0.52), all with valid_share ≈ 0, i.e. computed from a handful of leftover
  pixels that the cloud mask missed (cloud edges/shadows).

## Data quality + minimum clear-share rule (Stage 3, 23 Oct 2026)
- **Question:** below what share of clear cropland is a 14-day NDVI value unreliable?
- **Method:** for every composite, deviation = NDVI − median NDVI of well-observed cells (≥ 90% clear) in the same
  tile, year and period (same weather, same dates). Summarised by bins of valid_share. Note: the reference is
  other cells, so the typical |deviation| also contains real field-to-field differences (0.037 for well-observed
  cells); the *median* deviation is the bias signal.
- **Result:**

  | clear share | values | median deviation | typical abs. deviation | negative |
  |---|---|---|---|---|
  | < 1% | 758 | −0.138 | 0.178 | 233 |
  | 1–5% | 811 | −0.049 | 0.086 | 16 |
  | 5–10% | 769 | −0.041 | 0.071 | 0 |
  | 10–20% | 1,352 | −0.032 | 0.058 | 0 |
  | 20–30% | 1,181 | −0.022 | 0.054 | 0 |
  | 30–50% | 2,608 | −0.021 | 0.058 | 0 |
  | 50–70% | 3,567 | −0.008 | 0.053 | 0 |
  | 70–90% | 6,536 | −0.006 | 0.046 | 0 |
  | ≥ 90% | 105,327 | 0.000 | 0.037 | 0 |

  Values below the 50% line are concentrated in cloudy years (2019 9.2%, 2021 8.5% vs 2024 2.0%).
- **Decision (23 Oct 2026):** trust NDVI only if ≥ 50% of the cell's cropland was clear
  (config `panel.min_valid_share`). Cost: empty values 1.8% → 7.8%. `ndvi_raw` keeps all values.
- **Interpretation:** partly-clouded composites read too low (likely thin haze at cloud edges that the SCL mask
  misses). Because cloudiness differs by year, keeping them could produce fake year-to-year "anomalies".
- **Data-quality report** (`reports/data_quality.md`): 7.8% empty overall; worst periods mid-September (18.5%) and
  April (≈ 15%); the summer peak (10 Jun–4 Aug) is nearly complete (no season without a clear peak value);
  gaps of 3+ consecutive periods in 0.7% of cell-seasons. Per tile 1.3%–15.4% empty.
- **Spatial pattern:** empty values form a north–south strip with straight edges. Three relative orbits cover the
  oblast (107, 64, 21); the strip is most likely the zone seen by only one orbit, so fewer clear looks per period.
  Not verified per cell (scene footprints were not stored).
- **Limits / follow-up:** the 50% rule is a judgement on this evidence, not a tuned optimum → robustness check
  with 30% (and `ndvi_raw`). Because gaps are spatially clustered, Stage 7 must check that high- and
  low-exposure cells have similar gap rates.

## Exploration — whole-oblast overview (Stage 4, 23 Oct 2026; descriptive, no hypothesis tested)
- **Data:** `data/processed/panel.csv` with the 50% clear-share rule; season peak per cell-year =
  highest usable NDVI (`features.season_peaks`). Figures: `reports/figures/overview_{maps,seasonal_curves,ndvi_vs_rain}.png`
  (`scripts/plot_overview.py`). Curves = median over cells with a usable value in that period (the set of cells
  differs slightly per period because of cloud gaps).
- **Pre-war (2018–2021):** median peak NDVI 0.73, typical peak period 6 (~24 Jun). Peak NDVI is higher in the west;
  peaks come earlier in the east and south.
- **Season shape by year:** 2022 and 2023 stay green late. Median NDVI on 19 Aug: 0.28–0.33 pre-war vs 0.46 (2022),
  0.54 (2023). Cells with a late-season (16 Sep–Oct) median NDVI > 0.30: 0.1–4.1% pre-war, 59.6% in 2022, 15.2% in
  2023, 0.4% in 2024. 2023 also greened up late (27 May: 0.37 vs 0.49–0.62 in other years).
- **Weather at the same time:** Aug–Oct rain (median per cell) 54–79 mm pre-war, **212 mm in 2022**, 106 mm in 2023,
  42 mm in 2024; mean top-soil moisture 0.30 in 2022 vs 0.19–0.23 pre-war. The late greenness of 2022 coincides
  with an unusually wet autumn, so weather is a plausible part of the explanation. Other candidates (not yet
  separable): delayed or missed harvest, weeds on unharvested/abandoned fields (rule 4), a shift in crop mix,
  early emergence of winter crops. This is the reason for a climate-adjusted baseline; no conclusion drawn here.
- **Rain vs peak NDVI:** pooled pre-war correlation (spring rain 1 Apr–7 Jul vs peak) r = 0.45, but most of it is
  between years: within single years r = 0.44, −0.17, 0.42, 0.12 (2018–21). 2024 had the driest spring (96 mm) and
  the lowest median peak (0.65); 2021 the wettest (276 mm) and the highest pre-war peak (0.77).
- **Limits:** with only 4 pre-war seasons, the weather response is learned from 4 "year situations" (design risk 1).
  Oblast-wide medians mix high- and low-exposure areas; no comparison by exposure has been made yet.

## Experiment 2 — Seasonal baseline (Version 1, Stage 4, 23 Oct 2026)
- **Question:** how far does each cell's NDVI stray from its own pre-war normal, and how large is that in an
  ordinary (pre-war) year? This is the naive benchmark for RQ1; it does NOT adjust for weather.
- **Data:** `panel.csv` (50% clear-share rule). 1192 cells x 15 periods x 2018–2024.
- **Method:** expected NDVI(cell, period) = mean NDVI over 2018–2021 years with a usable value (needs ≥ 2 years,
  config `analysis.baseline_min_years`). For a pre-war year the mean of the OTHER pre-war years is used
  (leave-one-year-out), so pre-war anomalies are out-of-sample. Anomaly = observed − expected. Summaries per
  year and per part of the season: spring (periods 0–4, 1 Apr–9 Jun), peak (5–8, 10 Jun–4 Aug), late (9–14).
  Code: `src/agridisrupt/models/baseline.py`, `scripts/run_baseline.py` → `data/processed/baseline_anomalies.csv`.
- **Result:** anomaly available for 90.5% of rows.
  - Per 14-day value: MAE 0.074 / 0.096 / 0.092 / 0.096 (2018–21, out-of-sample), 0.112 (2022), 0.121 (2023),
    0.079 (2024). Mean anomaly −0.010 to +0.023 pre-war; +0.041 (2022), +0.065 (2023), −0.021 (2024).
  - Median over cells of mean anomaly, spring / peak / late:
    pre-war years between −0.028 and +0.034 / −0.038 and +0.052 / −0.026 and +0.031;
    2022: −0.018 / −0.001 / **+0.116**; 2023: −0.060 / +0.076 / **+0.121**; 2024: −0.003 / −0.039 / −0.023.
  - Ordinary-year range (5th–95th percentile of pre-war cell-years): spring −0.17 to +0.21, peak −0.24 to +0.19,
    late −0.10 to +0.10. The 2022 and 2023 late-season medians lie above the pre-war 95th percentile.
  - Maps: 2022 late-season positive anomalies are widespread, strongest in the east and south-east; 2022
    peak-season negative anomalies form clusters in the north-east and east.
- **Interpretation:** the naive baseline is noisy (ordinary years stray ±0.2 at peak), so small changes cannot be
  seen with it. The clearest departure is the late-season "staying green" of 2022 and 2023, which coincides with
  wet autumns (2022 strongly). Possible explanations stay open (weather, delayed/missed harvest, weeds, crop mix).
- **Limits:** not climate-adjusted; only 4 baseline years (leave-one-out uses 3, so pre-war MAE is slightly
  pessimistic); crop rotation inside a 5 km cell adds year-to-year noise; spatial clusters are not yet compared with
  conflict exposure. Next: Stage 5 ML model must beat pre-war MAE ≈ 0.09 using weather.
- **Season shape (added 23 Oct 2026):** per cell-season, peak NDVI, peak
  period and late-season NDVI (mean of periods 9–14 = 5 Aug–end Oct, ≥ 3 usable values), each compared with the
  cell's own pre-war mean (leave-one-year-out) → `data/processed/season_shape.csv`.
  - Median anomaly per year — peak NDVI: −0.041, −0.021, +0.015, +0.058 (2018–21), −0.013 (2022), +0.048 (2023),
    −0.078 (2024). Late-season NDVI: +0.004, −0.011, −0.023, +0.034, **+0.118**, **+0.117**, −0.029.
  - Share of cells beyond the pre-war 95th percentile of late-season anomaly (+0.094): 1.8, 1.8, 1.0, 15.4% in
    2018–21; **62.5% (2022), 69.3% (2023)**; 0.8% (2024). Peak NDVI below the pre-war 5th percentile: 28.4% in 2024.
  - Peak timing: pre-war spread ±2.7 periods (5th–95th pct), medians within ±1.3 → too noisy to be useful alone.
  - Note: autumn rain in 2023 (106 mm) was only moderately above pre-war (54–79 mm), unlike 2022 (212 mm), yet the
    late-season anomaly is as large. Descriptive only; weather adjustment comes in Stage 5.

## Experiment 3 — Weather-aware models of normal NDVI (Stage 5, 23 Oct 2026)
- **Hypothesis (RQ1):** a model using season, place and weather predicts pre-war NDVI better than the seasonal
  baseline on a held-out later year.
- **Data:** `panel.csv` (50% clear-share rule) + cell centroid (x, y, EPSG:3035 km) and cropland share; derived
  growing degree days (> 5 °C, season-to-date) and season-to-date rain. 2018–2021 only.
- **Method:** target = NDVI anomaly vs the cell's seasonal baseline from the training years (leave-one-year-out
  inside training, so training targets resemble test targets); prediction = baseline + predicted anomaly. Models:
  A seasonal baseline (anomaly 0); B ridge on standardised features incl. weather × period interactions, alpha by
  leave-one-training-year-out (grid 1–1e6); C scikit-learn HistGradientBoosting with fixed conservative settings
  (300 trees, lr 0.05, 15 leaves, ≥ 200 rows per leaf, no early stopping). Forward folds only: train 2018–19 →
  test 2020; train 2018–20 → test 2021 (main). No past NDVI as input. Code: `models/ml.py`, `scripts/run_models.py`.
- **Result:**

  | test year | model | MAE | RMSE | bias | R² NDVI | R² anomaly |
  |---|---|---|---|---|---|---|
  | 2020 | A baseline | 0.0929 | 0.1326 | −0.003 | 0.60 | 0.00 |
  | 2020 | B ridge | 0.0932 | 0.1327 | −0.004 | 0.60 | 0.00 |
  | 2020 | C boosting | **0.0892** | **0.1226** | −0.001 | 0.66 | 0.14 |
  | 2021 | A baseline | 0.0955 | 0.1332 | −0.023 | 0.62 | −0.03 |
  | 2021 | B ridge | **0.0880** | 0.1232 | +0.008 | 0.67 | 0.12 |
  | 2021 | C boosting | 0.0883 | **0.1226** | +0.005 | 0.68 | 0.13 |

  Ablation 2021, MAE (B / C), inputs added cumulatively: season + place 0.0971 / 0.0929; + rain 0.0953 / 0.0971;
  + temperature 0.0881 / 0.0886; + soil moisture 0.0880 / 0.0883. Per period (2021), the models gain most around the
  peak (24 Jun: A 0.128 → C 0.075) and early August; late-May errors stay ≈ 0.16 for all models.
- **Interpretation:** supported, but modestly: gradient boosting is the only model that improves in both test years
  (MAE −4% and −8%, RMSE −8%, bias ≈ 0); it explains ~13–14% of the deviation from normal. Ridge matches it in
  2021 but chooses near-zero weather effects in 2020 (only 2 training seasons). Temperature-related inputs carry the
  gain; rain alone does not help in 2021, the wettest spring, which lies outside the training range. Most
  year-to-year deviation (crop rotation inside a 5 km cell, sowing dates, management) is not explained by weather.
- **Limits:** only 2–3 training seasons and 2 test years; hyperparameters for C fixed, not tuned; per-period errors
  are spatially correlated (n overstates independent information); ERA5-Land at ~9 km. Stage 6 must check whether the
  model is unbiased across space and seasons before its anomalies are used for RQ2.

## Experiment 4 — Model evaluation and weather-adjusted anomalies (Stage 6, 23 Oct 2026)
- **Question (RQ1):** where and when is the gradient-boosting model of normal NDVI trustworthy, and what remains
  unusual in 2022–2024 once weather is accounted for?
- **Method:** main fold (train 2018–20, test 2021): errors by part of season, satellite tile and cell; calibration by
  deciles of the predicted deviation; permutation importance (5 repeats, groups shuffled jointly). Final model C refit
  on 2018–2021 → predicted normal for 2022–24; for each pre-war year the model is trained on the other three
  (reference for "ordinary year"). Adjusted anomaly = observed − predicted normal. Code: `scripts/evaluate_models.py`.
- **Result (2021 test):** MAE A→C by part — spring 0.095→0.102, peak 0.138→0.116, late 0.065→0.058; bias A→C —
  spring +0.026/+0.027, peak −0.058/−0.005, late −0.031/−0.004. C better in 9 of 10 tiles; largest C bias +0.032
  (36UYA). Cells with |mean error| > 0.05: A 20.2%, C 10.6%; per-cell mean error std 0.032 vs 0.031; C's remaining
  errors are spatially clustered (over-prediction north/centre-west, under-prediction south). Calibration: predicted
  −0.102 / +0.091 / +0.158 → observed −0.075 / +0.051 / +0.123 (over-reacts at the extremes).
- **Importance (MAE increase):** expected 0.078; temperature group 0.046 (gdd_cum 0.021, t2m_mean 0.018, t2m_anom
  0.003); rain group 0.014 (rain_cum 0.009); period 0.013; x 0.006; y 0.001; soil moisture 0.000; cropland 0.000.
- **Weather-adjusted anomalies (median over cells, spring / peak / late):** 2022 −0.033 / +0.032 / +0.075;
  2023 −0.077 / +0.081 / +0.067; 2024 −0.003 / +0.007 / −0.007 (unadjusted 2024 peak −0.039). Pre-war adjusted
  range (5th–95th pct): spring −0.137 to +0.202, peak −0.206 to +0.150, late −0.117 to +0.087. Cells above the
  pre-war late-season 95th pct: 0.3–10.7% (2018–21), **42.1% (2022), 30.9% (2023)**, 2.3% (2024). Spring below the
  5th pct: 21.4% in 2023.
- **Interpretation:** the model removes the systematic peak/late bias of the baseline and explains the 2024 drought
  (its weak peaks are what the weather predicts). Late-season "staying green" in 2022 and 2023 shrinks by about a
  third after the adjustment but remains well outside the ordinary-year range. Final model = C.
- **Limits:** autumn 2022 rain (212 mm) lies far outside the training range and trees do not extrapolate, so the
  adjustment for that autumn may be too small; C over-reacts at extremes; residuals are spatially clustered (an
  RQ2 comparison must use like-for-like areas and spatially robust uncertainty); pre-war references come from
  3-year models (slightly noisier than the 4-year model used for 2022–24). Bias in low-exposure cells → Stage 7.

## Experiment 5 — Conflict exposure and weather-adjusted anomalies (RQ2) — PLAN, written before any result
Written and committed 23 Oct 2026, after looking only at the spatial spread of ACLED events (not at any anomaly by
exposure). Settings in config `exposure:`. Wording rule: "associated with", never "caused by".
- **Data:** ACLED export of 23 Oct 2026 (2018–2024; file covers all Europe, filtered in code to events in the
  study area). Weather-adjusted anomalies from Experiment 4 (`data/processed/adjusted_anomalies.csv`) and season-shape
  measures. UCDP GED 26.1 as cross-check.
- **Exposure:** ACLED political violence (battles, explosions/remote violence, violence against
  civilians); geo_precision 1–2; events inside the 5 km cell or within 5 km of it; per growing season = 1 Jan
  (2022: 24 Feb) to 31 Oct. Groups per season: low = 0 events, high = 10+, some = 1–9 (regression only).
  Spread seen beforehand (2022): 36% of cells 0 events, 35% 10+, 9% 100+.
- **Outcomes:** mean weather-adjusted anomaly per part of the season (spring, peak, late), each reported; plus the
  late-season greenness anomaly (shape). No single "best" outcome will be picked afterwards.
- **Analyses (all reported, whatever they show):**
  1. Group comparison per season 2022, 2023, 2024: median and mean adjusted anomaly, high vs low; difference with a
     95% interval from a cluster bootstrap over 25 km spatial blocks (errors are spatially clustered, Exp. 4).
  2. Pre-trend / placebo: cells grouped by their 2022 exposure, adjusted anomalies plotted 2018–2024 (event-study
     style). Pre-war differences between the groups should be ≈ 0; if not, the post-war difference is not credible.
  3. Regression: adjusted anomaly (cell x season x part) ~ log(1 + events) + cell effects + year effects, all years
     2018–2024 (pre-war exposure ≈ 0). Cell effects absorb each cell's persistent model error; year effects absorb
     oblast-wide misfits (e.g. the under-adjusted wet autumn of 2022). Standard errors clustered by 25 km blocks.
  4. Bias check (RQ1): mean adjusted anomaly in low-exposure cells 2022–24 should be ≈ 0.
  5. Moran's I on regression residuals (remaining spatial autocorrelation).
  6. Cross-check with UCDP GED (fatal events only) using the same buffer and season window.
- **Known threats:** exposure is spatially clustered (front line in the east and north), so high and low cells
  differ in place, soil and crop mix — cell effects and the pre-trend check address this partly; occupied areas
  (spring–autumn 2022) may have been unfarmed for reasons of access; ACLED counts reflect reporting intensity;
  abandoned fields can look greener (rule 4), so the sign of an association is not assumed in advance.
- **RESULTS (run 23 Oct 2026, after the plan above was committed in b69b49a)** — `scripts/run_exposure_analysis.py`,
  `reports/exposure_results.csv`, `figures/exposure_{groups_map,event_study}.png`. 73,889 ACLED and 22,767 UCDP
  events in the study area. Cells per group (low / some / high): 2022 435 / 337 / 420; 2023 594 / 337 / 261;
  2024 582 / 301 / 309; pre-war seasons 0 high. High-exposure cells lie in the north and east, low ones in the
  south-west (strong spatial separation).
  1. **High − low, weather-adjusted (ACLED; 95% block-bootstrap interval):**
     2022 spring +0.040 [0.021, 0.061], **peak −0.050 [−0.073, −0.028]**, late +0.032 [0.011, 0.053];
     2023 spring **+0.080 [0.059, 0.101]**, peak +0.007 [−0.010, 0.025], late +0.007 [−0.004, 0.017];
     2024 spring +0.052, peak +0.045, late +0.037 (all intervals above 0). Late shape (not adjusted) follows "late".
     UCDP (fatal events; high groups only 61–116 cells): 2022 peak +0.009 [−0.028, 0.044] (does NOT replicate the
     ACLED peak result); 2023 spring +0.088; 2024 all parts +0.06–0.07 (same direction as ACLED).
  2. **Event study (cells grouped by 2022 exposure):** pre-war high − low differences are not all ≈ 0: spring 2020
     +0.042 [0.024, 0.059], late 2021 −0.033 [−0.047, −0.018]; peak pre-war −0.012 to +0.018 (all intervals include
     0). Post-war: peak −0.050 (2022) → +0.025 (2023) → +0.055 (2024); spring +0.040, +0.090, +0.028; late +0.032,
     +0.015, +0.046.
  3. **Two-way fixed effects (per unit of log(1+events); cell + year effects; 70 clusters):** spring +0.010
     [0.007, 0.013], peak +0.001 [−0.002, 0.004], late +0.008 [0.005, 0.011]; UCDP: +0.014, +0.008, +0.014 (all
     above 0). (0 → 100 events = 4.6 units → spring ≈ +0.046, late ≈ +0.035.)
  4. **Bias check (RQ1) FAILS for 2022–23:** mean adjusted anomaly in low-exposure cells — 2022 spring −0.032,
     peak +0.044, late +0.062; 2023 spring −0.090, peak +0.068, late +0.062; 2024 −0.005 / −0.025 / −0.018
     (intervals exclude 0 except 2024 spring). The model of normal is off by a common, year-level amount in 2022–23
     even where there was no fighting nearby (weather outside the training range, and/or oblast-wide war effects
     on markets, inputs and labour that "low exposure" does not exclude). Comparisons are therefore made RELATIVE
     (high − low, year effects), never as absolute anomalies.
  5. **Moran's I of regression residuals (2022):** spring 0.17, peak 0.34, late 0.48 (p = 0.005): strong remaining
     spatial autocorrelation. *Sensitivity (NOT in the plan, added after seeing it):* with 50 km blocks (23) and
     100 km blocks (9) the 2022 peak difference stays −0.050 [−0.075, −0.023] / [−0.062, −0.016]; the 2022 late
     difference becomes [0.007, 0.060] / [0.000, 0.078]; regression intervals widen slightly, same conclusions.
- **Interpretation:** exposure is associated with a different season SHAPE rather than a uniform loss of green:
  in 2022, high-exposure cells peaked lower than comparable-weather low-exposure cells (pre-war peak differences
  were ≈ 0), and in 2023–24 they were greener than expected, especially in spring. That pattern is consistent with
  disrupted sowing and management in 2022 followed by weedy or differently-cropped fields (rule 4) — but it is
  also consistent with differences between north/east and south-west that the model does not capture.
- **Limits:** high and low cells are geographically separated, and pre-war differences of up to ±0.04 occur in
  spring and late season, so only the peak result has a clean pre-trend; the 2022 peak result is not replicated
  with UCDP; the model of normal is biased in 2022–23 at oblast level; spatial autocorrelation leaves few effective
  clusters. ACLED counts also reflect reporting. Evidence: suggestive, not conclusive; no causal claim.
