# Oresund — Project Notes for Claude

## What this project does

Fetches bathymetric (ocean depth) data for the Öresund strait (between Sweden
and Denmark) and produces print-ready GeoTIFFs.

Single script: `fetch_bathymetry.py`

### Pipeline

1. **Bathymetry raster** — downloaded from EMODnet WCS (`emodnet:mean` coverage)
   at native resolution (~672 × 768 px at 1/480°), then **Lanczos resampled**
   client-side to A3/150 dpi output size (3508 × 4009 px). Lanczos is used
   instead of server-side interpolation to avoid staircase artefacts on narrow
   diagonal channels.
2. **Land polygons** — GSHHG full-resolution Level 1 shapefile (`GSHHS_f_L1`)
   downloaded from NOAA (~150 MB zip), extracted and **cached** in `data/`.
   Re-runs use the cached copy.
3. **Masked raster** — land cells set to NODATA so only sea depths remain.

### Bounding box

`11.95–13.35°E, 54.90–56.50°N` (EPSG:4326) — 2× the original extent.

### Outputs (all written to `data/`, git-ignored)

| File | Description |
|------|-------------|
| `oresund_bathymetry.tif` | Raw depth raster (metres) |
| `oresund_bathymetry_sea.tif` | Land-masked depth raster |
| `oresund_land.geojson` | Clipped land polygons (GSHHG) |
| `oresund_populated_places.geojson` | Point features: name, pop_max, pop_min, adm0_a3, featurecla, scalerank |
| `oresund_tatort_points.geojson` | GeoNames SE+DK populated place points; properties: name, population, country_code, feature_code |
| `GSHHS_f_L1.*` | Cached GSHHG shapefile files |
| `ne_10m_populated_places.*` | Cached Natural Earth populated places shapefile |
| `SE.txt` / `DK.txt` | Cached GeoNames country TSV dumps |

## Dependencies

```
numpy>=1.24
requests>=2.31
rasterio>=1.3
fiona>=1.9
shapely>=2.0
```

Note: `pandas>=2.0` is listed in `requirements.txt` but is not used by the
current script.

Install: `pip install -r requirements.txt`

## Running

```bash
python fetch_bathymetry.py
```

First run downloads ~150 MB GSHHG zip. Subsequent runs skip that step.

## Key constants (fetch_bathymetry.py)

| Constant | Value | Notes |
|----------|-------|-------|
| `BBOX` | `11.95,54.90,13.35,56.50` | minX,minY,maxX,maxY |
| `WIDTH, HEIGHT` | `3508, 4009` | A3 portrait @ 150 dpi |
| `NODATA` | `-9999.0` | Sentinel for masked/missing cells |
| `GSHHG_ZIP_URL` | NOAA v2.3.7 | Update if NOAA moves the file |

## Data sources

- **EMODnet Bathymetry WCS**: `https://ows.emodnet-bathymetry.eu/wcs`
  Native resolution ~1/480° (~230 m); Lanczos resampled to output size.
- **GSHHG**: `https://www.ngdc.noaa.gov/mgg/shorelines/gshhs.html`
  Version 2.3.7, full resolution, Level 1 (ocean/land boundary).
  Previously used Natural Earth 1:10m land polygons.
- **Natural Earth `ne_10m_populated_places`**: point layer, `POP_MAX` attribute
  used for population-scaled circles. Cached in `data/`.
  <https://www.naturalearthdata.com/downloads/10m-cultural-vectors/10m-populated-places/>
- **GeoNames** (`https://download.geonames.org/export/dump/`): country TSV dumps
  for SE and DK. Feature class P, excluding PPLX (section of place), population > 0.
  Properties: name, population, country_code, feature_code. Cached as `SE.txt` / `DK.txt`.
- **OpenStreetMap via Overpass API** (commented out — approach not working):
  `boundary=administrative` + `place~"^(city|town)$"` relations within the bbox.
