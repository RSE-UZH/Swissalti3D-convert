# SwissALTI3D Processing Tools

Tools for processing SwissALTI3D digital elevation model (DEM) data, including merging tiles and converting coordinate reference systems.

## Overview

This repository contains Python scripts for:
1. Merging SwissALTI3D DEM tiles downloaded from Swisstopo
2. Converting the merged DEM from Swiss local coordinates (LV95 LN02) to global coordinate systems

## Data Download

SwissALTI3D data can be downloaded from the [Swisstopo website](https://www.swisstopo.admin.ch/it/modello-altimetrico-swissalti3d).

Key points:
- Data is delivered in 1 km² tiles
- Available resolutions: 0.5m or 2m grid spacing
- Large areas are subdivided into downloadable units
- For >50 units, a CSV file with download links is provided

Download commands:
```bash
# Linux
wget -i download_links.csv

# Windows PowerShell
gc .\download_links.csv | % {iwr $_ -outf $(split-path $_ -leaf)}
```

## Merging Tiles

The `merge_tiles.py` script merges multiple DEM tiles into a single raster.

```python
from pathlib import Path
from merge_tiles import merge_tiles

# Example usage
tiles_dir = Path("./data/aletsch_tiles")
output_path = Path("outputs/swissalti3d_aletsch_2056_LV95_2m.tif")

merged_dem = merge_tiles(
    tiles_paths=list(tiles_dir.glob("*.tif")),
    output_path=output_path,
    parallel=True  # Enable parallel processing
)
```

## Coordinate System Conversion

The `convert_swissalti.py` script converts DEMs from Swiss coordinates to global reference systems.

Key features:

- Transforms from LN02 height datum to ellipsoidal heights
- Supports conversion to common vertical datums (EGM08, EGM96)
- Handles coordinate system reprojection

```python
from pathlib import Path
from convert_swissalti import transform_ln02_to_ellipsoid, convert_dem_vertical_datum

# Convert to UTM32N with EGM08 heights
dem_path = Path("outputs/swissalti3d_aletsch_2056_LV95_2m.tif")
chgeo2004_path = Path("geoid/Geoid_OGD/chgeo2004_htrans_ETRS.tif")
egm08_path = Path("geoid/us_nga_egm2008_1.tif")

# Step 1: Convert to ellipsoid heights
dem_ellipsoid = transform_ln02_to_ellipsoid(
    dem=dem_path,
    chgeo2004_geoid_path=chgeo2004_path,
    target_crs="32632"  # UTM32N
)

# Step 2: Convert to EGM08
dem_egm08 = convert_dem_vertical_datum(
    dem=dem_ellipsoid,
    geoid=egm08_path
)
```

## Installation 

```bash
pip install -r requirements.txt
```