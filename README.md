# Öresund Bathymetry

Fetches and processes open data to produce print-ready GeoTIFFs and GeoJSONs
for the Öresund strait between Sweden and Denmark.

## Outputs

All files are written to `data/` (git-ignored).

| File | Description |
|------|-------------|
| `oresund_bathymetry.tif` | Raw depth raster in metres (A3 @ 150 dpi) |
| `oresund_bathymetry_sea.tif` | Depth raster with land cells masked out |
| `oresund_land.geojson` | Full-resolution land polygons (GSHHG) |
| `oresund_populated_places.geojson` | Urban centres as points with population data |
| `oresund_urban_areas.geojson` | Urban footprint polygons clipped to coastline |

## Data sources

- **[EMODnet Bathymetry](https://emodnet.ec.europa.eu/en/bathymetry)** — depth
  raster at ~230 m native resolution, Lanczos resampled to output size
- **[GSHHG](https://www.ngdc.noaa.gov/mgg/shorelines/gshhs.html)** — NOAA
  full-resolution shoreline data (v2.3.7, Level 1), used for land masking and
  as the reference coastline for clipping
- **[Natural Earth](https://www.naturalearthdata.com/)** 1:10m cultural vectors:
  - `ne_10m_populated_places` — point layer with `POP_MAX` population estimates
  - `ne_10m_urban_areas` — urban footprint polygons

## Coverage

`11.95–13.35°E, 54.90–56.50°N` — centred on the strait, extending from
Falsterbo/Trelleborg in the south to Helsingborg/Helsingør in the north.

## Usage

```bash
pip install -r requirements.txt
python fetch_bathymetry.py
```

The first run downloads ~150 MB of GSHHG shoreline data and ~11 MB of Natural
Earth data. Subsequent runs use the cached copies in `data/`.
