#!/usr/bin/env python3
"""
Fetch Öresund bathymetry from EMODnet and save to data/.

Source : EMODnet Bathymetry WCS, coverage emodnet:mean
BBOX   : 12.30–13.00°E, 55.30–56.10°N  (EPSG:4326)
Outputs: data/oresund_bathymetry.tif   (GeoTIFF, depth in metres)
         data/oresund_bathymetry.csv   (longitude, latitude, depth_m)

Resolution: 3508 × 4009 px — A3 portrait at 300 dpi, preserving the
geographic degree aspect ratio (0.70° wide × 0.80° tall → w/h = 0.875).
EMODnet interpolates beyond its native 1/480° (~230 m) grid.
"""

import os
import sys

import numpy as np
import pandas as pd
import requests
import rasterio
import rasterio.transform

WCS_URL  = "https://ows.emodnet-bathymetry.eu/wcs"
COVERAGE = "emodnet:mean"
BBOX     = "12.30,55.30,13.00,56.10"   # minX,minY,maxX,maxY

# A3 portrait at 300 dpi, degree aspect ratio preserved (0.70°/0.80° = 0.875)
WIDTH, HEIGHT = 3508, 4009

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
TIFF_OUT = os.path.join(DATA_DIR, "oresund_bathymetry.tif")
CSV_OUT  = os.path.join(DATA_DIR, "oresund_bathymetry.csv")


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    # --- 1. Download GeoTIFF from EMODnet WCS ---
    params = {
        "service":       "WCS",
        "version":       "1.0.0",
        "request":       "GetCoverage",
        "coverage":      COVERAGE,
        "crs":           "EPSG:4326",
        "BBOX":          BBOX,
        "format":        "image/tiff",
        "interpolation": "bilinear",
        "width":         WIDTH,
        "height":        HEIGHT,
    }
    print(f"Fetching {COVERAGE} from EMODnet WCS  ({WIDTH} × {HEIGHT} px) …")
    r = requests.get(WCS_URL, params=params, timeout=180, stream=True)

    content_type = r.headers.get("Content-Type", "")
    if r.status_code != 200 or "xml" in content_type.lower():
        sys.exit(
            f"WCS error (HTTP {r.status_code}):\n{r.text[:500]}"
        )

    with open(TIFF_OUT, "wb") as f:
        for chunk in r.iter_content(65536):
            f.write(chunk)
    print(f"Saved GeoTIFF → {TIFF_OUT}  ({os.path.getsize(TIFF_OUT)//1024} KB)")

    # --- 2. Convert to CSV ---
    with rasterio.open(TIFF_OUT) as ds:
        depth = ds.read(1).astype(np.float64)
        nodata = ds.nodata
        h, w = depth.shape
        rows, cols = np.mgrid[0:h, 0:w]
        lons, lats = rasterio.transform.xy(ds.transform, rows.ravel(), cols.ravel())

    df = pd.DataFrame({"longitude": lons, "latitude": lats, "depth_m": depth.ravel()})
    if nodata is not None:
        df = df[~np.isclose(df["depth_m"], nodata)]
    else:
        df = df[df["depth_m"] > -1e10]

    df.to_csv(CSV_OUT, index=False, float_format="%.6f")
    print(f"Saved CSV     → {CSV_OUT}  ({len(df):,} points)")

    # --- 3. Summary ---
    print(f"\ndepth_m  min={df['depth_m'].min():.1f}  "
          f"max={df['depth_m'].max():.1f}  "
          f"mean={df['depth_m'].mean():.1f}")


if __name__ == "__main__":
    main()
