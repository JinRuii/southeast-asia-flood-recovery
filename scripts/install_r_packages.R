#!/usr/bin/env Rscript
# Run once in the R environment used for model fitting.
packages <- c("mgcv", "marginaleffects")
missing <- packages[!vapply(packages, requireNamespace, logical(1), quietly = TRUE)]
if (length(missing)) install.packages(missing, repos = "https://cloud.r-project.org")
