# Data schema

## Raster inputs

Provide daily mosaics named `VNP46A2_YYYYMMDD.tif` (suffixes after the date are allowed). Multiple rasters for the same date must be mosaicked upstream; the panel stage rejects duplicates instead of silently overwriting them. The default extracted TIFF layout is light in band 1, quality in band 5, and cloud information in band 7. Confirm these indices against the actual upstream export. No automatic band discovery, scaling, fill-value decoding or product download is implemented. Radiance units and scaling therefore follow the prepared TIFFs.

Raster files and grids must declare their CRS. Grid geometries are reprojected to each raster CRS. Provide a vector file readable by GeoPandas (for example, GeoPackage or a complete shapefile set), with a unique, nonmissing `grid_id`. The source script's fallback of generating IDs from row order has been removed to prevent incorrect event matching.

## Daily light panel

| Column | Type | Meaning |
| --- | --- | --- |
| `grid_id` | String | Stable identifier shared with the grid/event table |
| `date` | Date | Prefer `YYYY-MM-DD`; compact `YYYYMMDD` is also accepted |
| `light_mean` | Number or blank | Daily mean of retained nonzero raster pixels |

One row per grid/date is required. Missing values remain blank in the raw panel. Grid IDs are read as strings to preserve leading zeros. For shapefile inputs, store IDs as text if leading zeros matter.

## Flood event table

| Column | Type | Meaning |
| --- | --- | --- |
| `event_id` | String, optional | Unique event/grid record ID; generated if absent |
| `grid_id` | String | Identifier matching the daily panel |
| `flood_start` | Date | Flood onset; prefer `YYYY-MM-DD` |

Use UTF-8 CSV by default; a different encoding may be set in the configuration. Repeated floods in one grid are supported. Duplicate grid/onset pairs are rejected so event identity is resolved explicitly. A physical flood affecting multiple grids needs a unique record ID for each event/grid pair.

The supplied event export used a non-English onset-column heading. Rename that column to `flood_start` before running. Only the code has been translated; external datasets have not been included or modified.

## Model table

Provide a UTF-8 CSV. All required fields must be present.

| Columns | Meaning and preparation |
| --- | --- |
| `gridid`, `province_id` | Grid and province identifiers, modeled as factors |
| `hazard_regime` | Categorical intensity-frequency regime; becomes `HazardRegime` internally |
| `recovery_time` | Prepared response on the intended model scale; used without transformation |
| `ECO`, `PD`, `EVI`, `KS` | Ecosystem cover, patch density, vegetation index, soil hydraulic conductivity |
| `ISA`, `ROAD`, `Dam` | Impervious surface, roads and reservoir capacity indicators |
| `SLOPE`, `RAIN`, `RIVER`, `GDP`, `POP` | Environmental and socioeconomic controls |
| `X`, `Y` | Finite coordinates in the consistent coordinate system used by the analysis |

The model expects already prepared predictors: the study reference describes logarithmic transformations for `ISA`, `ROAD`, `Dam`, `POP`, and `GDP`, followed by standardization of continuous predictors/controls. The original transformation scripts, constants, and prepared table were not supplied, so this release does not recreate them. Do not apply another transformation without checking the input provenance. Coordinates are passed through unchanged.

Rename the source model table's non-English hazard-regime and recovery-time headings to `hazard_regime` and `recovery_time`. The original `gridid` model field differs from the NTL `grid_id`; join and rename explicitly. Model rows with missing required fields or nonfinite numeric values are excluded and counted in `input_audit.csv`. Zero response values are retained by the R script. This does not establish what the upstream prepared dataset contained.

## Outputs

The Python workflow writes daily panels, an event table, and a grid summary. Event fields include `baseline_nonzero_mean`, `baseline_observations`, `minimum_during_recovery`, `light_loss`, `light_loss_rate`, `recovery_date`, `recovery_days`, `recovery_speed`, `recovered`, and `status`. Light units match the input rasters, rates are fractions, and recovery duration is in days. `status` distinguishes recovered events, missing baselines, unmatched grids, and an absence of an observed threshold crossing. Nonrecovered durations remain missing; they are not assigned zero or 90 days. Grid mean recovery time averages available recovered-event estimates only, with event counts also reported.

The R workflow writes the fitted model (`gam_main.rds`), a model summary, fit statistics, row audit, regime counts, session information and two CSVs of average marginal effects. These derivatives describe associations on the fitted response/predictor scales, not causal effects. Global averaging includes all fitted observations; regime-specific averaging uses observations in each regime.
