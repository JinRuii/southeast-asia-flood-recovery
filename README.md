# Southeast Asia Flood Recovery

Python and R research code for nighttime-light flood recovery analysis and a spatial generalized additive mixed model (GAMM).

The repository contains two workflows recovered from the supplied analysis scripts: a VIIRS VNP46A2 nighttime-light pipeline and a spatial GAMM with average marginal effects. Reference manuscripts, supplementary documents, observed data, and fitted results are excluded.

## Repository contents

| Path | Purpose |
| --- | --- |
| `scripts/ntl_pipeline.py` | Quality screening, clipping, daily grid means, optional matrix filtering, and recovery metrics |
| `scripts/fit_gamm.R` | Spatial GAMM and global/regime-specific average marginal effects |
| `scripts/install_r_packages.R` | Install the two required R packages |
| `config/ntl.example.json` | Portable paths and explicit processing settings |
| `docs/data_schema.md` | Required inputs, units, and output fields |
| `docs/methods.md` | Implemented rules and interpretation limits |
| `docs/release_notes.md` | Changes from the supplied scripts and validation scope |
| `tests/test_ntl_pipeline.py` | Small synthetic checks for recovery, filtering and raster processing |

## Installation

Use Python 3.11 or later. From the repository root:

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

For model fitting, install R and then run:

```bash
Rscript scripts/install_r_packages.R
```

Dependencies are minimum requirements, not a reconstruction of the original computing environment. A historical lockfile was not supplied.

## Nighttime-light workflow

1. Prepare one seven-band GeoTIFF mosaic per day, a study grid with stable IDs, and an event table. Read [the input schema](docs/data_schema.md).
2. Copy `config/ntl.example.json` to `config/ntl.local.json` and set the paths. Relative paths resolve against the configuration directory.
3. Verify the TIFF band layout and filename date pattern. Defaults follow the supplied scripts, rather than defining a universal VNP46A2 band order.
4. Review [the processing rules](docs/methods.md), particularly zero handling and the matrix filter.
5. Run:

```bash
python scripts/ntl_pipeline.py --config config/ntl.local.json --stage all
```

Individual stages can be run with `--stage preprocess`, `clip`, `panel`, `filter`, or `recovery`, provided their inputs already exist. The default configuration applies the source matrix filter. Setting `apply_matrix_filter` to `false` changes the recovery input to the unfiltered panel and should be treated as a separate analysis choice.

## Spatial GAMM

Prepare an independent, already transformed and standardized model table with the English columns in [the schema](docs/data_schema.md), then run:

```bash
Rscript scripts/fit_gamm.R data/processed/model_input.csv outputs/gamm 4
```

The Python recovery output is not directly a GAMM input. Covariates, hazard regimes, province identifiers and coordinates must be prepared and joined separately. Code for those preparation steps was not supplied. The model script does not apply logarithms or standardization; it uses the supplied response values as-is.

## Validation

```bash
python -m unittest discover -s tests -v
```

Tests generate tiny synthetic inputs in temporary directories. No observed study data or paper results are bundled. See [release notes](docs/release_notes.md) for the actual checks performed on this release and untested components.

## Upload to GitHub

Create an empty GitHub repository, extract this archive, and upload the **contents** of this project folder, including `.gitignore`. Alternatively, from this folder:

```bash
git init
git add .
git commit -m "Add flood recovery analysis code"
```

Connect the local repository using the remote URL shown by GitHub, then push. This archive does not publish anything automatically. The ignore rules keep local inputs, generated outputs, local configuration and reference documents out of ordinary `git add` operations.

No license or publication identifier has been inferred. Add the authors' chosen license and final citation details when they are available. Until a license is added, this repository does not grant a separate reuse license.
