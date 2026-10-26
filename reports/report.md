# Detecting abnormal cropland behaviour in a conflict zone: weather-adjusted Sentinel-2 greenness in Kharkiv oblast, Ukraine, 2018–2024

*Muhammad Yahya — BSc Business Analytics, University of Amsterdam — portfolio research project, October 2026*

## Abstract

This project tests whether satellite imagery, weather data and machine learning can detect abnormal cropland
behaviour in a conflict zone once normal weather and seasonal variation are accounted for. For 1,192 cropland squares
of 5 × 5 km in Kharkiv oblast, 14-day Sentinel-2 NDVI composites (April–October 2018–2024; 4,684 scenes) were
combined with ERA5-Land weather. A gradient-boosting model trained only on pre-war seasons predicted "normal"
greenness. Forward in time, it beat a seasonal average by 4–8% (mean absolute error 0.089 vs 0.093 in 2020 and
0.088 vs 0.096 in 2021), explaining about 13% of year-to-year deviations. Conflict exposure was measured with ACLED
events within 5 km of each square per growing season. The exposure definition, the recovery rule and three
robustness checks were all fixed before any result was examined. Squares with 10 or more events had a lower summer
peak in 2022 than squares with none (−0.050 NDVI, 95% interval −0.073 to −0.028), with no pre-war difference. They
were greener than expected in spring 2023 (+0.080) and 2024 (+0.052). Where fighting ended after 2022, spring
greenness was back to normal by 2024, but peak and late-season greenness rose above that of never-exposed squares.
Of 32 tested results, 31 held across the robustness checks. The pattern is consistent with disrupted sowing in 2022
followed by weedy, fallow or differently cropped fields. It is an association, not a causal estimate: exposure is
geographically clustered, the 2022 peak result is not reproduced with UCDP data, and the model of normal is biased
region-wide in 2022–2023.

## 1. Questions

Satellite greenness is widely available, but greenness changes with weather, crop rotation and season timing. A
drop or rise in NDVI therefore says little about farming on its own. The project asks three questions:

- **RQ1 (measurement):** can a climate-aware model trained on pre-war years predict cropland NDVI well, with small
  and unbiased error where there was no conflict?
- **RQ2 (association):** after 24 February 2022, are climate-adjusted deviations larger in high-exposure cropland
  than in comparable low-exposure cropland?
- **RQ3 (recovery):** where exposure ended, how fast did deviations return to normal?

## 2. Study area and data

Kharkiv oblast (31,441 km²) was chosen among five candidate regions. It has rich data, a fixed pre-war cropland
mask, highly and barely exposed cropland under similar climate, and a clear change in exposure after September 2022.

| Data | Use | Detail |
|---|---|---|
| Sentinel-2 L2A (Copernicus, via Microsoft Planetary Computer) | greenness | bands B04, B08, SCL; read at 20 m (tested equal to 10 m for 5 km squares: median difference 0.001); 10 tiles; 4,684 scenes; 0 unreadable after re-runs |
| ESA WorldCereal 2021, temporary crops | cropland mask | fixed pre-war mask; squares kept if ≥ 30% cropland (1,192 of 1,392) |
| ERA5-Land (Copernicus Climate Change Service) | weather | 2 m temperature, top-layer soil moisture, precipitation, 2015–2024 |
| ACLED (event level) | conflict exposure | battles, explosions/remote violence, violence against civilians; located to a town or better |
| UCDP GED 26.1 | cross-check | fatal events only |

**Processing.** The scene classification layer keeps vegetation and bare-soil pixels. Scenes over 80% cloudy are
skipped. Reflectance from processing baseline 04.00 (from 25 January 2022) is corrected for its +1000 offset, which
is unit-tested; without it, NDVI would jump exactly at the start of the war. NDVI is the median per 14-day period over
each square's cropland pixels: 15 periods per season, giving 125,160 square-periods. A data-quality check showed
that composites with little clear cropland read too low (median −0.14 below 1% clear; −0.02 to −0.05 between 1% and
50%; about 0 above 50%), so values are used only if at least 50% of the square's cropland was clear. That leaves
7.8% of values empty. The summer peak is almost complete. Gaps cluster in a north–south strip that matches the area
seen by only one of the three satellite orbits.

## 3. Methods

**Seasonal baseline (Version 1).** Normal NDVI for a square and period is its mean over 2018–2021. Each pre-war year
is compared with the other three years only (leave-one-year-out), so that ordinary-year deviations are measured out
of sample. Three season-shape measures are tracked per square and year: peak NDVI, peak timing, and late-season NDVI
(5 August–end October). Level alone can miss abandoned fields, which often turn weedy and green.

**Weather-aware model of normal (RQ1).** The target is the deviation from the square's baseline. The model predicts
it from the time of year, location, the baseline level and the weather: temperature and its anomaly, season-to-date
growing degree days above 5 °C, rain over 14, 30 and 60 days, season-to-date rain, and soil moisture. Past NDVI is
never an input, because after 2022 it would carry war effects into "normal". Three models were compared with
forward-in-time validation (train 2018–19 → test 2020; train 2018–20 → test 2021): the seasonal baseline, ridge
regression with weather × period terms, and gradient boosting (scikit-learn HistGradientBoosting, fixed conservative
settings). The chosen model was refitted on 2018–2021 to predict normal NDVI for 2022–2024. The weather-adjusted
anomaly is observed minus predicted NDVI.

**Exposure and comparisons (RQ2, RQ3).** Exposure is the number of ACLED events inside a square or within 5 km of it,
per growing season (1 January, or 24 February in 2022, to 31 October). Low exposure means 0 events; high means 10
or more. The analyses were the following:
- high − low differences per season, with 95% intervals from a bootstrap over 25 km spatial blocks;
- an event study, with squares grouped by their 2022 exposure and compared in every year 2018–2024;
- a two-way fixed-effects regression of the anomaly on log(1 + events), with square and year effects and errors
  clustered by blocks;
- a bias check in low-exposure squares, Moran's I on residuals, and a UCDP cross-check.

For recovery, "ended" squares (high in 2022, fewer than 10 events in both 2023 and 2024) are compared with squares
that had no events in any war season. A square counts as recovered when the gap is back within its pre-war range
and the interval includes 0.

**Pre-registration.** The definitions, outcomes and rules for RQ2, RQ3 and the robustness checks were written into
the project and committed before the analyses were run. Only the spatial spread of events, or the number of squares
per group, had been looked at. All results are reported, including those that did not hold.

## 4. Results

### 4.1 RQ1: a model of normal greenness

| Test year | Seasonal baseline | Ridge | Gradient boosting |
|---|---|---|---|
| 2020 (MAE) | 0.0929 | 0.0932 | **0.0892** |
| 2021 (MAE) | 0.0955 | **0.0880** | 0.0883 |

Gradient boosting was the only model that improved in both test years. Its errors are unbiased on average (bias
+0.005 in 2021), and it explains 13–14% of the deviation from normal. It removes the baseline's systematic error at
the summer peak (bias −0.058 → −0.005) and in the late season (−0.031 → −0.004), but not in spring. Its remaining
errors are spatially clustered, and it over-reacts slightly at the extremes: a predicted +0.16 corresponds to an
observed +0.12. Temperature-related inputs carry most of the gain. Rain alone did not help in 2021, the wettest
spring, which was outside the training range. Soil moisture added nothing. The model explains the 2024 drought:
2024's weak peaks (−0.039 against the seasonal baseline) are what the weather predicts (+0.007 after adjustment).

The bias check failed for 2022–2023. Even in squares with no nearby events, the weather-adjusted late-season anomaly
was +0.062 in both years. Possible reasons are weather outside the training range (autumn 2022 had 212 mm of rain,
against 54–79 mm before the war, and tree models do not extrapolate) and region-wide effects of the war on markets,
inputs and labour. Absolute anomalies are therefore not interpreted as conflict effects. Only relative comparisons
(near vs far, with year effects) are used.

### 4.2 RQ2: greenness near and far from conflict

In 2022, 420 squares were highly exposed and 435 had no events. High exposure lies in the north and east, low
exposure in the south-west.

| Weather-adjusted, high − low | 2022 | 2023 | 2024 |
|---|---|---|---|
| Spring | +0.040 [0.021, 0.061] | **+0.080** [0.059, 0.101] | +0.052 [0.029, 0.076] |
| Summer peak | **−0.050** [−0.073, −0.028] | +0.007 [−0.010, 0.025] | +0.045 [0.019, 0.070] |
| Late season | +0.032 [0.011, 0.053] | +0.007 [−0.004, 0.017] | +0.037 [0.023, 0.050] |

In the event study, the pre-war peak differences between the 2022 groups were small (−0.012 to +0.018, all
intervals including 0). The 2022 peak difference is therefore the result with the cleanest pre-trend. Spring and
late-season differences already existed before the war (spring 2020 +0.042; late 2021 −0.033). In the
fixed-effects regression, more events went with greener springs (+0.010 per unit of log(1 + events)) and late
seasons (+0.008), and with no change at the peak (+0.001, interval −0.002 to 0.004), because the negative 2022
and positive 2024 peak differences cancel out. With UCDP, the 2023 spring and 2024 differences point the same way,
but the 2022 peak difference does not reappear (+0.009, interval −0.028 to 0.044). Residuals remain spatially
autocorrelated (Moran's I 0.17–0.48); intervals barely change with 50 km or 100 km blocks.

### 4.3 RQ3: recovery where fighting ended

| Gap to never-exposed squares | 2022 | 2023 | 2024 | Recovered? |
|---|---|---|---|---|
| "Ended" squares (172), spring | +0.045 | +0.086 | +0.002 | yes, 2024 |
| peak | −0.033 | +0.048 | +0.051 | not by 2024 |
| late season | +0.071 | +0.024 | +0.041 | not by 2024 |

The ended squares had the largest late-season greenness in 2022 (+0.071), when much of that area was retaken only in
September. By 2024 their spring greenness matched never-exposed squares, but at the peak and late in the season they
were greener than those squares, like the squares where fighting continued. For the persistent group, the rule
labels the summer peak as "recovered in 2023", but this is a sign change (−0.076 in 2022, +0.068 in 2024), not a
return to normal. This weakness of the rule is reported as found.

### 4.4 Robustness

Three checks were fixed in advance: (R1) only low-exposure squares within 25 km of a high-exposure square;
(R2) exposure within 10 km; (R3) the seasonal baseline instead of the weather model. A result "holds" if it keeps
its sign and its interval still excludes 0. **31 of 32 results held.** The 2022 lower peak (R1 −0.041; R2 −0.060;
R3 −0.042), the greener spring of 2023 and 2024, and the regression pattern survive all checks. The greener 2024
peak does not survive R1 (+0.004), so it is most likely a regional difference. Using only nearby squares shrinks the
main differences by roughly a fifth to a third. The weather model hardly changes these relative comparisons,
because near and far squares share the same year's weather.

## 5. Discussion and limitations

The results point to a change in the *shape* of the season near conflict rather than a uniform loss of green: a
weaker 2022 peak, then early and persistent greenness. This fits disrupted sowing and management in the first war
year, followed by weedy or fallow fields, mine-contaminated land left out of normal rotation, or a different crop
mix. Satellite greenness alone cannot separate these explanations.

Limitations:
- **Only four pre-war seasons.** The weather response is learned from few distinct years, and 2022–2023 weather
  partly lies outside them.
- **Non-random exposure.** High- and low-exposure squares differ in place, soils and crop mix. Square fixed effects,
  the pre-trend check and nearby comparisons address this only partly.
- **Conflict data.** ACLED counts also reflect reporting intensity, and UCDP records only fatal events.
- **NDVI is not yield.** Greener does not mean more food. Weeds and unharvested crops can raise NDVI.
- **Resolution.** Recovery is measured per season over two post-exposure years, and 5 km squares mix fields and crops.
- **Spatial dependence.** Effective sample sizes are smaller than the number of squares.

## 6. Ethics

All outputs are historical (2018–2024) and aggregated to 5 km squares and whole seasons. No event locations are
shown, nothing tracks the front line, and the public dashboard shows exposure only as low/some/high groups. No causal
language is used beyond what the design supports.

## 7. Reproducibility

All settings live in one configuration file, and 53 automated tests cover the key steps (including the 2022 offset
correction). A re-run of the analysis from the merged table onwards reproduced every result table and figure
exactly. Code, figures and the experiment log (`reports/experiments.md`) are in the project repository. Raw and
processed data are not redistributed.

## Data sources

Copernicus Sentinel-2 data (2018–2024), accessed via Microsoft Planetary Computer · ERA5-Land, Copernicus Climate
Change Service (CC BY 4.0) · ESA WorldCereal 2021, temporary crops (CC BY 4.0) · Armed Conflict Location & Event Data
(ACLED), acleddata.com · UCDP Georeferenced Event Dataset (GED) 26.1 (CC BY 4.0) · geoBoundaries (administrative
boundaries).
