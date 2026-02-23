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
| `oresund_land.geojson` | Clipped land polygons |
| `GSHHS_f_L1.*` | Cached GSHHG shapefile files |

## Dependencies

```
numpy>=1.24
requests>=2.31
rasterio>=1.3
fiona>=1.9
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

## Planned additions

### Urban area overlay

The goal is to add either polygon outlines or population-scaled circles for
major urban areas on the land portions of the map. Data options under
consideration:

**For population-scaled circles (recommended starting point)**
- **Natural Earth `ne_10m_populated_places`** — point layer with `POP_MAX`
  attribute; ~8 MB; fiona-compatible; covers all cities/towns in the bbox.
  <https://www.naturalearthdata.com/downloads/10m-cultural-vectors/10m-populated-places/>

**For polygon outlines**
- **Natural Earth `ne_10m_urban_areas`** — pre-clipped urban footprint polygons;
  ~3 MB; fiona-compatible; no population attribute.
  <https://www.naturalearthdata.com/downloads/10m-cultural-vectors/10m-urban-area/>
- **OpenStreetMap via Overpass API** — more detailed/current; requires `osmnx`.
- **Eurostat Urban Audit** — official EU Functional Urban Areas for
  Copenhagen/Malmö; authoritative but heavier download.

Both Natural Earth files can be downloaded and cached in `data/` using the same
pattern as GSHHG.
