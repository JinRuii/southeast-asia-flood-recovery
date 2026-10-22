# Release notes

## Source and packaging

- Converted the source Python and R code stored in text files into executable-language scripts.
- Translated comments, messages, documentation, configuration and output field names into English.
- Excluded reference manuscripts, supplementary documents, source text files, raw data and generated research outputs.
- Replaced personal Windows paths with configurable paths or command-line arguments.
- Reduced R dependencies to the two packages actually used by the delivered model code.
- Added setup instructions, input/output schemas and Git ignore rules.

## Execution fixes and explicit behavior

- Fixed the undefined final output variable in the NTL source.
- Separated the event-table path from the daily-panel path; removed the hidden configuration mutation and hard-coded event read.
- Normalized dates before baseline and recovery matching, including dates read from CSV as integers.
- Evaluated all unique grid/onset records instead of selecting the first onset per grid, and added grid summaries and event-status fields. This changes results for grids with repeated events relative to the supplied first-event behavior.
- Reprojected vector geometries to raster CRS, required stable grid IDs, and recorded missing observations for nonoverlapping grids.
- Rejected duplicate daily rasters, duplicate panel observations, duplicate event/onset pairs and missing required fields rather than silently overwriting or misaligning records.
- Preserved the source zero exclusions, QA thresholds, matrix-filter calculation, threshold crossing rule and GAMM formula. No upstream product-specific interpretation has been inferred.
- Made the model's missing-row handling explicit and recorded retained zero responses. Infinite numeric model inputs now fail the finite-row inclusion check; the supplied prepared data were unavailable for comparison.
- Renamed the internal response from `log_T` to `response`; neither source nor release applies a new response logarithm.

## Validation performed

See `validation.md` for the checks and runtime limitations recorded for this packaged release. Synthetic checks do not verify the scientific suitability of the inherited processing choices or reproduce the study's numerical results.
