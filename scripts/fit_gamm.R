#!/usr/bin/env Rscript
# Fit the supplied spatial GAMM and export average marginal effects.
# Input predictors must already be transformed and standardized.

args <- commandArgs(trailingOnly = TRUE)
if (length(args) == 1L && args[1] %in% c("--help", "-h")) {
  cat("Usage: Rscript scripts/fit_gamm.R INPUT_CSV OUTPUT_DIR [THREADS]\n")
  quit(status = 0)
}
if (length(args) < 2L || length(args) > 3L) {
  stop("Usage: Rscript scripts/fit_gamm.R INPUT_CSV OUTPUT_DIR [THREADS]")
}
packages <- c("mgcv", "marginaleffects")
missing <- packages[!vapply(packages, requireNamespace, logical(1), quietly = TRUE)]
if (length(missing)) {
  stop("Install required R packages: ", paste(missing, collapse = ", "))
}
library(mgcv)
library(marginaleffects)

input_path <- args[1]
output_dir <- args[2]
threads <- if (length(args) == 3L) suppressWarnings(as.integer(args[3])) else 4L
if (is.na(threads) || threads < 1L) stop("THREADS must be a positive integer.")
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

message("Reading prepared model data...")
data <- read.csv(input_path, stringsAsFactors = FALSE, check.names = FALSE,
                 fileEncoding = "UTF-8")
smooth_variables <- c("ECO", "PD", "EVI", "KS", "ISA", "ROAD", "Dam")
controls <- c("SLOPE", "RAIN", "RIVER", "GDP", "POP")
required <- c("gridid", "province_id", "hazard_regime", "recovery_time",
              smooth_variables, controls, "X", "Y")
missing_columns <- setdiff(required, names(data))
if (length(missing_columns)) stop("Missing columns: ", paste(missing_columns, collapse = ", "))
if (nrow(data) == 0L) stop("The model input is empty.")

numeric_columns <- c("recovery_time", smooth_variables, controls, "X", "Y")
for (column in numeric_columns) {
  if (!is.numeric(data[[column]])) stop("Expected a numeric column: ", column)
}
valid <- complete.cases(data[, required])
for (column in numeric_columns) valid <- valid & is.finite(data[[column]])
# Missingness is explicit; zero values are retained at this modeling stage.
data_clean <- data[valid, , drop = FALSE]
if (!nrow(data_clean)) stop("No complete finite observations remain.")
data_clean$gridid <- as.factor(data_clean$gridid)
data_clean$province_id <- as.factor(data_clean$province_id)
data_clean$HazardRegime <- as.factor(data_clean$hazard_regime)
# The original log_T name did not perform a log transformation.
# Keep the provided response scale and use an unambiguous internal name.
data_clean$response <- data_clean$recovery_time
if (nlevels(data_clean$HazardRegime) < 2L) stop("At least two hazard regimes are required.")
if (nlevels(data_clean$province_id) < 2L) stop("At least two provinces are required.")
for (column in smooth_variables) {
  counts <- tapply(data_clean[[column]], data_clean$HazardRegime,
                   function(x) length(unique(x)))
  if (any(counts < 5L)) stop("At least five distinct values per hazard regime required: ", column)
}
if (nrow(unique(data_clean[, c("X", "Y")])) < 50L) {
  stop("At least 50 distinct coordinate pairs are required for the spatial smooth.")
}
audit <- data.frame(
  input_rows = nrow(data), fitted_rows = nrow(data_clean),
  excluded_incomplete_or_nonfinite_rows = sum(!valid),
  zero_response_rows_retained = sum(data_clean$response == 0),
  threads = threads
)
write.csv(audit, file.path(output_dir, "input_audit.csv"), row.names = FALSE)
write.csv(as.data.frame(table(data_clean$HazardRegime)),
          file.path(output_dir, "hazard_regime_counts.csv"), row.names = FALSE)

message("Fitting the spatial GAMM...")
gam_main <- gam(
  response ~ 1 +
    s(ECO, k = 5, bs = "cr") +
    s(PD, k = 5, bs = "cr") +
    s(EVI, k = 5, bs = "cr") +
    s(KS, k = 5, bs = "cr") +
    s(ISA, k = 5, bs = "cr") +
    s(ROAD, k = 5, bs = "cr") +
    s(Dam, k = 5, bs = "cr") +
    SLOPE + RAIN + RIVER + GDP + POP +
    s(ECO, by = HazardRegime, k = 5, bs = "cr") +
    s(PD, by = HazardRegime, k = 5, bs = "cr") +
    s(EVI, by = HazardRegime, k = 5, bs = "cr") +
    s(KS, by = HazardRegime, k = 5, bs = "cr") +
    s(ISA, by = HazardRegime, k = 5, bs = "cr") +
    s(ROAD, by = HazardRegime, k = 5, bs = "cr") +
    s(Dam, by = HazardRegime, k = 5, bs = "cr") +
    s(province_id, bs = "re") +
    s(X, Y, bs = "tp", k = 50),
  data = data_clean,
  family = gaussian(link = "identity"),
  method = "REML",
  na.action = na.fail,
  control = gam.control(nthreads = threads, maxit = 200)
)
saveRDS(gam_main, file.path(output_dir, "gam_main.rds"))
capture.output(summary(gam_main), file = file.path(output_dir, "model_summary.txt"))
capture.output(sessionInfo(), file = file.path(output_dir, "session_info.txt"))
fit_summary <- summary(gam_main)
write.csv(data.frame(n = nobs(gam_main), adjusted_r_squared = fit_summary$r.sq,
                     deviance_explained = fit_summary$dev.expl),
          file.path(output_dir, "model_fit.csv"), row.names = FALSE)

message("Estimating global and regime-specific average marginal effects...")
# Explicit newdata keeps data recovery independent of the fitting call's scope.
ame_global <- avg_slopes(gam_main, variables = smooth_variables, newdata = data_clean)
ame_by_hazard <- avg_slopes(gam_main, variables = smooth_variables,
                             by = "HazardRegime", newdata = data_clean)
columns <- c("term", "estimate", "std.error", "statistic", "p.value", "conf.low", "conf.high")
write.csv(as.data.frame(ame_global)[, columns],
          file.path(output_dir, "global_average_marginal_effects.csv"), row.names = FALSE)
by_hazard <- as.data.frame(ame_by_hazard)[, c("HazardRegime", columns)]
by_hazard <- by_hazard[order(by_hazard$HazardRegime, by_hazard$term), ]
write.csv(by_hazard, file.path(output_dir, "hazard_average_marginal_effects.csv"),
          row.names = FALSE)
message("Completed. Outputs saved to: ", normalizePath(output_dir))
