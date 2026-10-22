#!/usr/bin/env python3
"""Prepare daily nighttime lights and estimate flood recovery metrics.

The QA thresholds, zero exclusions and optional matrix filter follow the
supplied analysis code. See docs/methods.md before using these choices.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.ndimage import uniform_filter

LOGGER = logging.getLogger(__name__)


def read_config(path: Path) -> dict:
    """Resolve relative paths against the configuration file directory."""
    cfg = json.loads(path.read_text(encoding="utf-8"))
    for key, value in cfg["paths"].items():
        p = Path(value).expanduser()
        cfg["paths"][key] = str(p if p.is_absolute() else (path.parent / p).resolve())
    settings = cfg["settings"]
    if settings["before_days"] < 1 or settings["max_recovery_days"] < 1:
        raise ValueError("Recovery windows must be positive integers.")
    if not 0 < settings["recovery_threshold"] <= 1:
        raise ValueError("recovery_threshold must be in (0, 1].")
    return cfg


def require_columns(df: pd.DataFrame, columns: list[str], label: str) -> None:
    missing = sorted(set(columns) - set(df.columns))
    if missing:
        raise ValueError(f"{label}: missing columns: {', '.join(missing)}")


def write_csv(df: pd.DataFrame, path: str) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(destination, index=False, encoding="utf-8")
    LOGGER.info("Saved %s (%d rows)", destination, len(df))


def input_rasters(folder: str, pattern: str) -> list[Path]:
    paths = sorted(Path(folder).glob(pattern))
    if not paths:
        raise FileNotFoundError(f"No rasters matching {pattern!r} in {folder}")
    return paths


def preprocess(cfg: dict) -> None:
    """Keep source band values where quality/cloud thresholds are satisfied."""
    import rasterio

    settings = cfg["settings"]
    output = Path(cfg["paths"]["preprocessed_dir"])
    output.mkdir(parents=True, exist_ok=True)
    for path in input_rasters(cfg["paths"]["raw_dir"], settings["raster_glob"]):
        with rasterio.open(path) as src:
            bands = settings["bands"]
            if src.count < max(bands.values()):
                raise ValueError(f"{path.name}: insufficient raster bands.")
            light = src.read(bands["light"])
            quality = src.read(bands["quality"])
            cloud = np.nan_to_num(src.read(bands["cloud"]), nan=999)
            valid = (cloud < settings["cloud_upper_bound"]) & np.isin(
                quality, settings["valid_quality_values"]
            )
            clean = np.where(valid, light, 0)
            profile = src.profile.copy()
            profile.update(count=1, nodata=0)
            with rasterio.open(output / f"{path.stem}_clean.tif", "w", **profile) as dst:
                dst.write(clean, 1)
        LOGGER.info("Preprocessed %s", path.name)


def read_grid(cfg: dict):
    import geopandas as gpd

    grid = gpd.read_file(cfg["paths"]["grid_file"])
    if grid.crs is None:
        raise ValueError("The grid file must declare its coordinate reference system.")
    column = cfg["settings"]["grid_id_column"]
    if column not in grid.columns:
        raise ValueError(f"The grid file must contain the stable identifier {column!r}.")
    if grid[column].isna().any() or grid[column].duplicated().any():
        raise ValueError("Grid identifiers must be nonmissing and unique.")
    if grid.geometry.isna().any() or grid.geometry.is_empty.any() or not grid.geometry.is_valid.all():
        raise ValueError("The grid file contains missing, empty or invalid geometries.")
    grid[column] = grid[column].astype(str)
    return grid


def clip(cfg: dict) -> None:
    """Clip to the combined study area, reprojecting geometries as needed."""
    import rasterio
    from rasterio.mask import mask

    grid = read_grid(cfg)
    output = Path(cfg["paths"]["clipped_dir"])
    output.mkdir(parents=True, exist_ok=True)
    for path in input_rasters(cfg["paths"]["preprocessed_dir"], "*_clean.tif"):
        with rasterio.open(path) as src:
            if src.crs is None:
                raise ValueError(f"{path.name}: missing raster CRS.")
            geoms = list(grid.to_crs(src.crs).geometry)
            image, transform = mask(src, geoms, crop=True, nodata=0, all_touched=True)
            profile = src.profile.copy()
            profile.update(height=image.shape[1], width=image.shape[2], transform=transform, nodata=0)
            with rasterio.open(output / f"{path.stem}_clip.tif", "w", **profile) as dst:
                dst.write(image)
        LOGGER.info("Clipped %s", path.name)


def build_panel(cfg: dict) -> None:
    """Calculate grid means from nonzero pixels, preserving the source rule."""
    import rasterio
    from rasterio.mask import mask

    grid = read_grid(cfg)
    settings = cfg["settings"]
    date_map = {}
    for path in input_rasters(cfg["paths"]["clipped_dir"], "*_clip.tif"):
        match = re.search(settings["date_regex"], path.name)
        if match is None:
            raise ValueError(f"No date matched in {path.name}; update date_regex.")
        date = pd.to_datetime(match.group(1), format="%Y%m%d").strftime("%Y-%m-%d")
        if date in date_map:
            raise ValueError(f"Multiple rasters for {date}. Mosaic daily tiles before processing.")
        date_map[date] = path
    records = []
    for date, path in sorted(date_map.items()):
        with rasterio.open(path) as src:
            projected = grid.to_crs(src.crs)
            for gid, geom in zip(projected[settings["grid_id_column"]], projected.geometry):
                try:
                    image, _ = mask(src, [geom], crop=True, nodata=0)
                except ValueError as exc:
                    if "do not overlap" not in str(exc):
                        raise
                    records.append({"grid_id": gid, "date": date, "light_mean": np.nan})
                    continue
                values = image[0][image[0] != 0]
                mean = float(np.round(np.mean(values), 2)) if values.size else np.nan
                records.append({"grid_id": gid, "date": date, "light_mean": mean})
    write_csv(pd.DataFrame(records), cfg["paths"]["panel_csv"])


def read_panel(path: str) -> pd.DataFrame:
    panel = pd.read_csv(path, dtype={"grid_id": str})
    require_columns(panel, ["grid_id", "date", "light_mean"], "Light panel")
    if panel["grid_id"].isna().any():
        raise ValueError("Light panel contains missing grid identifiers.")
    # Handle compact dates, ISO dates and slash-separated dates consistently.
    panel["date"] = pd.to_datetime(
        panel["date"].astype(str), format="mixed", errors="raise"
    ).dt.normalize()
    panel["light_mean"] = pd.to_numeric(panel["light_mean"], errors="raise")
    if np.isinf(panel["light_mean"]).any():
        raise ValueError("Infinite light values are not supported.")
    if panel.duplicated(["grid_id", "date"]).any():
        raise ValueError("Light panel contains duplicate grid/date pairs.")
    return panel


def filter_panel(cfg: dict) -> None:
    """Apply the supplied 3x3 grid-by-date matrix filter without redefining it."""
    LOGGER.warning(
        "Applying the source matrix filter: this smooths all entries across grid-ID "
        "order and date order; it is not a geographic neighborhood filter. "
        "NaN propagation is retained and remaining NaNs become zero."
    )
    panel = read_panel(cfg["paths"]["panel_csv"])
    # Use numeric grid ordering when possible, as in the source CSV workflow.
    ids = panel["grid_id"].unique().tolist()
    try:
        ids.sort(key=lambda value: int(value))
    except ValueError:
        ids.sort()
    matrix = panel.pivot(index="grid_id", columns="date", values="light_mean").reindex(ids)
    filtered = np.nan_to_num(uniform_filter(matrix.to_numpy(dtype=float), size=3, mode="nearest"))
    result = pd.DataFrame(filtered, index=matrix.index, columns=matrix.columns)
    result = result.reset_index().melt(id_vars="grid_id", var_name="date", value_name="light_mean")
    result["date"] = pd.to_datetime(result["date"]).dt.strftime("%Y-%m-%d")
    write_csv(result, cfg["paths"]["filtered_panel_csv"])


def event_metrics(series: pd.Series, onset: pd.Timestamp, settings: dict) -> dict:
    """Estimate one event; use nonzero baseline and the first crossing after onset."""
    result = {
        "baseline_nonzero_mean": np.nan, "baseline_observations": 0,
        "minimum_during_recovery": np.nan, "light_loss": np.nan,
        "light_loss_rate": np.nan, "recovery_date": None,
        "recovery_days": np.nan, "recovery_speed": np.nan,
        "recovered": False, "status": "no_valid_baseline",
    }
    before_dates = pd.date_range(onset - pd.Timedelta(days=settings["before_days"]),
                                 onset - pd.Timedelta(days=1))
    values = series.reindex(before_dates).to_numpy(dtype=float)
    values = values[np.isfinite(values) & (values != 0)]
    result["baseline_observations"] = len(values)
    if not len(values):
        return result
    baseline = values.mean()
    result["baseline_nonzero_mean"] = round(float(baseline), 6)
    result["status"] = "no_threshold_crossing_observed"
    target = baseline * settings["recovery_threshold"]
    for day in range(1, settings["max_recovery_days"] + 1):
        current = onset + pd.Timedelta(days=day)
        value = series.get(current, np.nan)
        if np.isfinite(value) and value >= target:
            result.update(recovery_date=current.strftime("%Y-%m-%d"), recovery_days=day,
                          recovered=True, status="recovered")
            during = series.reindex(pd.date_range(onset, current)).dropna()
            minimum = during.min()
            loss = baseline - minimum
            rate = round(float(loss / baseline), 6) if baseline != 0 else np.nan
            result.update(minimum_during_recovery=round(float(minimum), 6),
                          light_loss=round(float(loss), 6), light_loss_rate=rate,
                          recovery_speed=round(rate / day, 8))
            break
    return result


def recover(cfg: dict) -> None:
    settings = cfg["settings"]
    source = "filtered_panel_csv" if settings["apply_matrix_filter"] else "panel_csv"
    panel = read_panel(cfg["paths"][source])
    events = pd.read_csv(cfg["paths"]["events_csv"], dtype={"grid_id": str},
                         encoding=settings["events_encoding"])
    require_columns(events, ["grid_id", "flood_start"], "Flood events")
    if events[["grid_id", "flood_start"]].isna().any().any():
        raise ValueError("Flood events contain missing grid identifiers or onset dates.")
    events["flood_start"] = pd.to_datetime(
        events["flood_start"].astype(str), format="mixed", errors="raise"
    ).dt.normalize()
    if "event_id" not in events:
        events["event_id"] = [f"event_{i + 1:06d}" for i in range(len(events))]
    if events["event_id"].isna().any() or events["event_id"].duplicated().any():
        raise ValueError("event_id must be nonmissing and unique.")
    if events.duplicated(["grid_id", "flood_start"]).any():
        raise ValueError("Duplicate grid/onset records: resolve event identity before running.")
    by_grid = {gid: frame.set_index("date")["light_mean"] for gid, frame in panel.groupby("grid_id")}
    records = []
    for event in events.itertuples(index=False):
        series = by_grid.get(event.grid_id, pd.Series(dtype=float))
        metrics = event_metrics(series, event.flood_start, settings)
        if event.grid_id not in by_grid:
            metrics["status"] = "grid_missing_from_panel"
        records.append({"event_id": event.event_id, "grid_id": event.grid_id,
                        "flood_start": event.flood_start.strftime("%Y-%m-%d"), **metrics})
    if not records:
        raise ValueError("The flood event table is empty.")
    result = pd.DataFrame(records)
    write_csv(result, cfg["paths"]["event_results_csv"])
    summary = result.groupby("grid_id", sort=False).agg(
        event_count=("event_id", "size"), recovered_event_count=("recovered", "sum"),
        mean_recovery_days=("recovery_days", "mean")
    ).reset_index()
    write_csv(summary, cfg["paths"]["grid_results_csv"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/ntl.example.json"))
    parser.add_argument("--stage", choices=["all", "preprocess", "clip", "panel", "filter", "recovery"], default="all")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    cfg = read_config(args.config.resolve())
    stages = {"preprocess": preprocess, "clip": clip, "panel": build_panel,
              "filter": filter_panel, "recovery": recover}
    if args.stage == "all":
        for name, function in stages.items():
            if name != "filter" or cfg["settings"]["apply_matrix_filter"]:
                function(cfg)
    else:
        stages[args.stage](cfg)


if __name__ == "__main__":
    main()
