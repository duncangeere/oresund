#!/usr/bin/env python3
"""
Fetch Öresund bathymetry from EMODnet and save to data/.

Source : EMODnet Bathymetry WCS, coverage emodnet:mean
BBOX   : 11.95–13.35°E, 54.90–56.50°N  (EPSG:4326)
Outputs: data/oresund_bathymetry.tif          (GeoTIFF, raw depth in metres)
         data/oresund_bathymetry_sea.tif      (GeoTIFF, land masked out)
         data/oresund_land.geojson            (GSHHG full-resolution land polygons)
         data/oresund_populated_places.geojson (NE point features with population)

Resolution: 3508 × 4009 px — A3 portrait at 150 dpi, preserving the
geographic degree aspect ratio (1.40° wide × 1.60° tall → w/h = 0.875).
Download is at EMODnet's native 1/480° (~230 m) grid (~672 × 768 px),
then upsampled client-side to the output size with Lanczos resampling
to avoid the staircase artefacts that server-side interpolation produces
on narrow diagonal channels.
"""

import io
import json
import os
import sys
import zipfile

import fiona
import numpy as np
import requests
import rasterio
from rasterio.io import MemoryFile
from rasterio.mask import mask as rio_mask
from rasterio.transform import from_bounds
from rasterio.warp import reproject, Resampling
from shapely.geometry import shape  # mapping unused while urban areas are commented out
# from shapely.ops import unary_union

WCS_URL    = "https://ows.emodnet-bathymetry.eu/wcs"
COVERAGE   = "emodnet:mean"
BBOX       = "11.95,54.90,13.35,56.50"   # minX,minY,maxX,maxY  (2× original extent)
NATIVE_RES = 1 / 480                      # EMODnet native grid spacing in degrees (~230 m)

# A3 portrait at 150 dpi, degree aspect ratio preserved (1.40°/1.60° = 0.875)
WIDTH, HEIGHT = 3508, 4009

NODATA = -9999.0

# GSHHG full-resolution shoreline data (NOAA/SOEST)
# https://www.ngdc.noaa.gov/mgg/shorelines/gshhs.html
# Level 1 = ocean boundary (land polygons); "f" = full resolution
GSHHG_ZIP_URL = (
    "https://www.ngdc.noaa.gov/mgg/shorelines/data/gshhg/latest/"
    "gshhg-shp-2.3.7.zip"
)

# Natural Earth 1:10m cultural vectors
# https://www.naturalearthdata.com/downloads/10m-cultural-vectors/
NE_POPULATED_PLACES_URL = (
    "https://naciscdn.org/naturalearth/10m/cultural/"
    "ne_10m_populated_places.zip"
)
# OVERPASS_URL = "https://overpass-api.de/api/interpreter"

DATA_DIR     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
TIFF_OUT     = os.path.join(DATA_DIR, "oresund_bathymetry.tif")
TIFF_SEA_OUT = os.path.join(DATA_DIR, "oresund_bathymetry_sea.tif")
LAND_OUT     = os.path.join(DATA_DIR, "oresund_land.geojson")
GSHHG_SHP    = os.path.join(DATA_DIR, "GSHHS_f_L1.shp")
NE_PP_SHP    = os.path.join(DATA_DIR, "ne_10m_populated_places.shp")
# OSM_URBAN_CACHE = os.path.join(DATA_DIR, "osm_urban_boundaries.geojson")
PLACES_OUT   = os.path.join(DATA_DIR, "oresund_populated_places.geojson")
# URBAN_OUT    = os.path.join(DATA_DIR, "oresund_urban_areas.geojson")


def _bbox_tuple():
    parts = BBOX.split(",")
    return tuple(float(x) for x in parts)   # (min_lon, min_lat, max_lon, max_lat)


def _overlaps_bbox(geom, min_lon, min_lat, max_lon, max_lat):
    """True if a GeoJSON geometry dict's bounding box overlaps the target bbox."""
    coords = []
    if geom["type"] == "Polygon":
        for ring in geom["coordinates"]:
            coords.extend(ring)
    elif geom["type"] == "MultiPolygon":
        for polygon in geom["coordinates"]:
            for ring in polygon:
                coords.extend(ring)
    if not coords:
        return False
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return (
        max(lons) >= min_lon and min(lons) <= max_lon
        and max(lats) >= min_lat and min(lats) <= max_lat
    )


def _ensure_ne(zip_url, shp_path, label, size_hint):
    """Download and extract a Natural Earth shapefile zip to DATA_DIR if not cached."""
    if os.path.exists(shp_path):
        print(f"Using cached {label}: {shp_path}")
        return
    print(f"Downloading {label} ({size_hint}) …")
    r = requests.get(zip_url, timeout=120, stream=True)
    r.raise_for_status()
    zip_data = io.BytesIO()
    for chunk in r.iter_content(65536):
        zip_data.write(chunk)
    zip_data.seek(0)
    stem = os.path.splitext(os.path.basename(shp_path))[0]
    with zipfile.ZipFile(zip_data) as zf:
        for member in zf.namelist():
            basename = os.path.basename(member)
            if basename.startswith(stem + "."):
                target = os.path.join(DATA_DIR, basename)
                with zf.open(member) as src, open(target, "wb") as dst:
                    dst.write(src.read())
    print(f"Extracted {stem} files → {DATA_DIR}")


def _ensure_gshhg():
    """Download and extract the GSHHG full-res L1 shapefile to DATA_DIR if not cached."""
    if os.path.exists(GSHHG_SHP):
        print(f"Using cached GSHHG shapefile: {GSHHG_SHP}")
        return
    print("Downloading GSHHG full-resolution shapefile (~150 MB) …")
    r = requests.get(GSHHG_ZIP_URL, timeout=300, stream=True)
    r.raise_for_status()
    zip_data = io.BytesIO()
    for chunk in r.iter_content(65536):
        zip_data.write(chunk)
    zip_data.seek(0)
    with zipfile.ZipFile(zip_data) as zf:
        for member in zf.namelist():
            basename = os.path.basename(member)
            if basename.startswith("GSHHS_f_L1."):
                target = os.path.join(DATA_DIR, basename)
                with zf.open(member) as src, open(target, "wb") as dst:
                    dst.write(src.read())
    print(f"Extracted GSHHS_f_L1 files → {DATA_DIR}")


# def _fetch_osm_urban():
#     """Fetch OSM administrative city/town boundaries via Overpass API.
#
#     Uses [out:geojson] so Overpass returns a ready-made FeatureCollection.
#     Result is cached to DATA_DIR as osm_urban_boundaries.geojson.
#     """
#     if os.path.exists(OSM_URBAN_CACHE):
#         print(f"Using cached OSM urban boundaries: {OSM_URBAN_CACHE}")
#         with open(OSM_URBAN_CACHE) as f:
#             return json.load(f)
#
#     min_lon, min_lat, max_lon, max_lat = _bbox_tuple()
#     # Overpass bbox order: south,west,north,east
#     bbox_str = f"{min_lat},{min_lon},{max_lat},{max_lon}"
#     query = (
#         f"[out:geojson][timeout:60][bbox:{bbox_str}];\n"
#         "(\n"
#         '  relation[boundary=administrative][place~"^(city|town)$"];\n'
#         ");\n"
#         "out geom;"
#     )
#     print("Fetching OSM administrative boundaries from Overpass API …")
#     r = requests.post(OVERPASS_URL, data={"data": query}, timeout=90)
#     r.raise_for_status()
#     data = r.json()
#     with open(OSM_URBAN_CACHE, "w") as f:
#         json.dump(data, f)
#     print(f"Cached OSM urban boundaries → {OSM_URBAN_CACHE}")
#     return data


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    min_lon, min_lat, max_lon, max_lat = _bbox_tuple()

    # --- 1. Download GeoTIFF from EMODnet WCS at native resolution ---
    native_w = round((max_lon - min_lon) / NATIVE_RES)
    native_h = round((max_lat - min_lat) / NATIVE_RES)
    params = {
        "service":  "WCS",
        "version":  "1.0.0",
        "request":  "GetCoverage",
        "coverage": COVERAGE,
        "crs":      "EPSG:4326",
        "BBOX":     BBOX,
        "format":   "image/tiff",
        "width":    native_w,
        "height":   native_h,
    }
    print(f"Fetching {COVERAGE} from EMODnet WCS at native res  ({native_w} × {native_h} px) …")
    r = requests.get(WCS_URL, params=params, timeout=180, stream=True)

    content_type = r.headers.get("Content-Type", "")
    if r.status_code != 200 or "xml" in content_type.lower():
        sys.exit(f"WCS error (HTTP {r.status_code}):\n{r.text[:500]}")

    raw_bytes = io.BytesIO()
    for chunk in r.iter_content(65536):
        raw_bytes.write(chunk)
    raw_bytes.seek(0)

    # --- 1b. Upsample to output resolution using Lanczos ---
    print(f"Resampling to {WIDTH} × {HEIGHT} px with Lanczos …")
    dst_transform = from_bounds(min_lon, min_lat, max_lon, max_lat, WIDTH, HEIGHT)
    with MemoryFile(raw_bytes) as memfile:
        with memfile.open() as src:
            src_meta = src.meta.copy()
            native_arr = src.read(1)

    dst_arr = np.empty((HEIGHT, WIDTH), dtype=src_meta["dtype"])
    reproject(
        source=native_arr,
        destination=dst_arr,
        src_transform=src_meta["transform"],
        src_crs=src_meta["crs"],
        dst_transform=dst_transform,
        dst_crs=src_meta["crs"],
        src_nodata=src_meta.get("nodata"),
        dst_nodata=src_meta.get("nodata"),
        resampling=Resampling.lanczos,
    )

    out_meta = src_meta.copy()
    out_meta.update({"width": WIDTH, "height": HEIGHT, "transform": dst_transform})
    with rasterio.open(TIFF_OUT, "w", **out_meta) as ds:
        ds.write(dst_arr, 1)
    print(f"Saved GeoTIFF → {TIFF_OUT}  ({os.path.getsize(TIFF_OUT)//1024} KB)")

    # --- 2. Fetch/cache GSHHG full-resolution land polygons and clip to bbox ---
    _ensure_gshhg()
    print("Reading and clipping GSHHG land polygons …")
    land_shapes = []
    land_geojson_features = []
    with fiona.open(GSHHG_SHP) as src:
        for feat in src:
            geom = feat.geometry.__geo_interface__
            if _overlaps_bbox(geom, min_lon, min_lat, max_lon, max_lat):
                land_shapes.append(geom)
                land_geojson_features.append(
                    {"type": "Feature", "geometry": geom, "properties": {}}
                )

    clipped_land = {"type": "FeatureCollection", "features": land_geojson_features}
    with open(LAND_OUT, "w") as f:
        json.dump(clipped_land, f)
    print(f"Saved land polygons → {LAND_OUT}  ({len(land_shapes)} features)")

    # --- 3. Mask land out of the raster (keep sea only) ---
    print("Masking land cells …")

    with rasterio.open(TIFF_OUT) as ds:
        sea_image, sea_transform = rio_mask(
            ds, land_shapes, invert=True, nodata=NODATA, filled=True
        )
        meta = ds.meta.copy()

    meta.update({"nodata": NODATA, "transform": sea_transform,
                 "width": sea_image.shape[2], "height": sea_image.shape[1]})

    with rasterio.open(TIFF_SEA_OUT, "w", **meta) as ds:
        ds.write(sea_image)
    print(f"Saved masked GeoTIFF → {TIFF_SEA_OUT}  ({os.path.getsize(TIFF_SEA_OUT)//1024} KB)")

    # --- 4. Natural Earth populated places (point GeoJSON with attributes) ---
    _ensure_ne(
        NE_POPULATED_PLACES_URL, NE_PP_SHP,
        "Natural Earth populated places", "~8 MB",
    )
    print("Reading and filtering populated places …")
    place_features = []
    with fiona.open(NE_PP_SHP) as src:
        for feat in src:
            geom = feat.geometry.__geo_interface__
            lon, lat = geom["coordinates"]
            if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat:
                p = feat.properties
                place_features.append({
                    "type": "Feature",
                    "geometry": geom,
                    "properties": {
                        "name":       p.get("NAME"),
                        "pop_max":    p.get("POP_MAX"),
                        "pop_min":    p.get("POP_MIN"),
                        "adm0_a3":    p.get("ADM0_A3"),
                        "featurecla": p.get("FEATURECLA"),
                        "scalerank":  p.get("SCALERANK"),
                    },
                })
    with open(PLACES_OUT, "w") as f:
        json.dump({"type": "FeatureCollection", "features": place_features}, f)
    print(f"Saved populated places → {PLACES_OUT}  ({len(place_features)} features)")

    # --- 5. OSM administrative city/town boundaries (clipped to GSHHG land) ---
    # Commented out: approach not working. Replace with tätorter point data.
    # osm_urban = _fetch_osm_urban()
    # print("Intersecting OSM urban boundaries with GSHHG land …")
    # land_union = unary_union([shape(g) for g in land_shapes])
    # urban_features = []
    # for feat in osm_urban.get("features", []):
    #     geom = feat.get("geometry")
    #     if geom is None:
    #         continue
    #     try:
    #         clipped = shape(geom).intersection(land_union)
    #     except Exception:
    #         continue
    #     if clipped.is_empty:
    #         continue
    #     props = feat.get("properties") or {}
    #     urban_features.append({
    #         "type": "Feature",
    #         "geometry": mapping(clipped),
    #         "properties": {
    #             "name":        props.get("name"),
    #             "place":       props.get("place"),
    #             "admin_level": props.get("admin_level"),
    #         },
    #     })
    # with open(URBAN_OUT, "w") as f:
    #     json.dump({"type": "FeatureCollection", "features": urban_features}, f)
    # print(f"Saved urban areas → {URBAN_OUT}  ({len(urban_features)} features)")

    # --- 6. Summary ---
    with rasterio.open(TIFF_SEA_OUT) as ds:
        depth = ds.read(1).astype(np.float64)
    sea = depth[~np.isclose(depth, NODATA) & ~np.isnan(depth)]
    print(f"\ndepth_m  min={sea.min():.1f}  max={sea.max():.1f}  mean={sea.mean():.1f}")


if __name__ == "__main__":
    main()
