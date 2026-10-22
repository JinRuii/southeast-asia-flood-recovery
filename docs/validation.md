# Validation record

Validation date: 22 October 2026.

- Seven synthetic Python tests passed using `python -m unittest discover -s tests -v`.
- Checks cover zero exclusion in the baseline, first threshold crossing, onset exclusion, the 90-day boundary, missing baselines and crossings, repeated events, unmatched grids, leading-zero IDs, the inherited matrix filter, relative configuration paths, QA screening, clipping across different declared coordinate systems, grid means, nonoverlapping grids and duplicate daily rasters.
- The command-line help entry point and Python syntax were checked.
- Repository text was checked for remaining Chinese content and personal source paths.
- The archive was checked for integrity and excluded content before delivery.

## Test environment

- Python: 3.12.14
- numpy: 2.3.5
- pandas: 2.2.3
- scipy: 1.17.0
- rasterio: 1.5.2
- geopandas: 1.2.0

## Limits

R was not installed in the packaging environment. The R scripts were reviewed, but parsing in R, package installation, GAMM fitting and marginal-effect extraction were not executed. Observed input data and the original software environment were unavailable, so neither the numerical study results nor agreement with a historical model fit could be validated. The minimum dependency specifications are not a lockfile.
