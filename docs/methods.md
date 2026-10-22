# Implemented methods and limits

## Quality screening and zero handling

The default Python rule keeps pixels with quality values 0 or 1 and cloud-information values below 128, using extracted bands 1, 5 and 7. Failed pixels become zero. These are the supplied code's rules; this repository does not independently validate the upstream TIFF export, cloud bit interpretation, radiance scaling or native fill values.

Clipped rasters use zero as nodata. Daily grid means explicitly select `image[0] != 0`, and pre-flood baselines explicitly exclude zero. Therefore this implementation cannot distinguish genuine zero radiance from invalid observations encoded as zero. It must not be described as retaining all zero observations. The R model has no zero-removal rule, but its upstream input preparation is unavailable.

Clipping to the combined study footprint uses `all_touched=True`; individual grid extraction uses the raster-mask default, as in the supplied script. Grid means are rounded to two decimal places, also as in the source.

## Optional source matrix filter

The supplied filter is `uniform_filter(matrix, size=3, mode="nearest")` on the grid-by-date matrix, followed by `nan_to_num`. The default configuration preserves this operation. It smooths observed values as well as missing entries. Adjacent matrix rows are grid-ID neighbors, not necessarily geographic neighbors; adjacent columns are available dates, not necessarily consecutive days. This is not a spatial-neighbor imputation algorithm.

NaNs can propagate within the SciPy filtering operation before being converted to zero. As a result, missingness and grid ordering can affect recovery estimates. This historical behavior has been documented rather than silently replaced. Any alternative missing-data or geographic-neighbor method requires separate scientific validation.

## Recovery metrics

For each event, the default baseline is the mean of finite, nonzero observations in the 30 calendar days before onset. The recovery date is the first observation from day 1 through day 90 after onset reaching at least 90% of the baseline. Searches use actual calendar dates; missing dates are not interpolated at this stage.

For recovered events, the minimum is taken from onset through recovery, including zero values in that period. Light loss equals baseline minus that minimum; loss rate equals loss divided by baseline; recovery speed equals the rounded loss rate divided by recovery days. No nonnegativity clipping is applied, preserving the supplied calculation. For events without a baseline or an observed threshold crossing, the corresponding recovery metrics remain missing. An absent threshold crossing can reflect limited observations and is not proof that recovery never occurred.

Every unique grid/onset record is evaluated. The source script selected only the first onset within each grid; this release corrects that behavior and produces both event-level metrics and a grid mean over recovered events. Overlapping floods are not statistically disentangled, and grid means are descriptive summaries.

## Spatial GAMM

The R formula preserves seven global cubic-regression smooths (`k=5`), seven hazard-regime factor-by smooths (`k=5`), five linear controls, a province random-effect smooth, and a two-dimensional thin-plate coordinate smooth (`k=50`). Fitting uses a Gaussian identity link, REML and a maximum of 200 iterations. The source formula contains no separate parametric hazard-regime main effect; this release leaves that specification unchanged.

The source assigned the recovery-time column to an object called `log_T` but did not compute a logarithm. This release calls that internal response `response` and fits the supplied `recovery_time` values without changing their scale. Correct response-scale interpretation depends on the prepared input. Input identifiers are factors and continuous predictors must already be prepared. The model does not directly model unrecovered/censored event durations.

`marginaleffects::avg_slopes` extracts average derivatives for the seven smooth predictors, globally and by hazard regime. These estimates combine applicable global and regime-specific smooth contributions. No causal interpretation or exact reproduction of published estimates is claimed.

## Scope

The archive contains the supplied NTL and GAMM workflows only. It does not contain code for disaster-report ingestion, covariate construction, predictor transformations, hazard-regime classification, spatial aggregation of all indicators, figure generation, OLS sensitivity analyses, Moran's I, or high-gain configuration searches. Reference documents describe a wider study than the available code covers. Data, original package versions and execution logs were not supplied.
