import logging
from pathlib import Path
from typing import Literal, Optional, Union

import geoutils as gu
import pyproj
import xdem

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger()


def transform_ln02_to_ellipsoid(
    dem: Union[Path, gu.Raster, xdem.DEM],
    chgeo2004_geoid_path: Path,
    target_crs: Optional[Union[int, str]] = None,
    resampling: str = "cubic",
    **kwarg,
) -> xdem.DEM:
    """
    Transforms the DEM from the Swiss LN02 vertical reference system (using CHGeo2004 geoid) to an ellipsoidal height reference. Optionally reprojects the DEM to a specified CRS.

    Parameters:
        dem (Union[Path, gu.Raster, xdem.DEM]): Input DEM, either as a file path, gu.Raster, or xdem.DEM object.
        chgeo2004_geoid_path (Path): Path to the CHGeo2004 geoid file for LN02 to ellipsoid conversion.
        target_crs (Optional[Union[int, str]], optional): EPSG code or PROJ string for the target CRS. If provided, the DEM will be reprojected to this CRS. Defaults to None.
        resampling (str, optional): Resampling method to use for reprojection. Any Rasterio resampling method can be used. Options include 'nearest', 'bilinear', 'cubic', etc. Defaults to "cubic".
        **kwarg: Additional keyword arguments to pass to the xdem.DEM.reproject() method.

    Returns:
        xdem.DEM: The DEM transformed to ellipsoidal heights and reprojected to the target CRS if specified.

    Raises:
        TypeError: If the input DEM is not of type Path, gu.Raster, or xdem.DEM.
        FileNotFoundError: If the specified CHGeo2004 geoid file is not found.
        ValueError: If an invalid resampling method is provided.
    """
    # Validate and load DEM if input is a path
    if isinstance(dem, Path):
        dem = xdem.DEM(dem)
    elif isinstance(dem, gu.Raster):
        dem = xdem.DEM(dem)
    elif not isinstance(dem, xdem.DEM):
        raise TypeError("Input DEM must be a file path, gu.Raster, or xdem.DEM object.")

    # Check that the geoid file exists
    if not chgeo2004_geoid_path.exists():
        raise FileNotFoundError(f"Geoid file not found at {chgeo2004_geoid_path}")

    # Load and reproject the geoid to match the DEM's grid and resolution
    logger.info("Reprojecting CHGeo2004 geoid to match DEM grid...")
    geoid = xdem.DEM(chgeo2004_geoid_path)
    geoid_warped = geoid.reproject(dem, resampling="bilinear")

    # Convert to ellipsoidal height by adding geoid values
    logger.info("Adding geoid height to DEM for conversion to ellipsoidal height...")
    dem += geoid_warped
    dem.set_vcrs("Ellipsoid")

    # Optional: reproject to the target CRS if specified
    if target_crs is not None:
        # Convert target CRS to EPSG code if it's a strings
        if not isinstance(target_crs, int):
            target_crs = pyproj.CRS.from_user_input(target_crs).to_epsg()

        logger.info(
            f"Reprojecting DEM to target CRS {target_crs} using {resampling} resampling..."
        )
        dem.reproject(crs=target_crs, resampling=resampling, inplace=True, **kwarg)

    return dem


def convert_dem_vertical_datum(
    dem: xdem.DEM,
    geoid: Union[Literal["Ellipsoid", "EGM08", "EGM96"], str, Path, xdem.DEM],
    output_path: Path = None,
) -> xdem.DEM:
    """
    Convert DEM vertical height datum to/from ellipsoidal height or geoid-based vertical datum.

    Parameters:
        dem (xdem.DEM): DEM object to be converted.
        output_path (Path): Path to save the converted DEM.
        geoid (Literal["Ellipsoid", "EGM08", "EGM96"] | str | Path | xdem.DEM): Geoid model name, path, or DEM object.

    Returns:
        xdem.DEM: DEM converted to the specified vertical coordinate system.
    """
    # Validate and load the geoid
    if isinstance(geoid, (str, Path)):
        geoid = Path(geoid)  # Ensure it's a Path if it's a string

        if not geoid.exists():
            raise FileNotFoundError(f"Geoid file not found at {geoid}")

        # Load and reproject the provided geoid file to match DEM
        logger.info(f"Loading geoid file from {geoid}")
        geoid_dem = xdem.DEM(geoid)
        geoid_warped = geoid_dem.reproject(dem, resampling="bilinear")
        logger.info("Adjusting DEM based on provided geoid file...")
        dem -= geoid_warped

    elif isinstance(geoid, xdem.DEM):
        # If a geoid DEM object is provided, reproject it and apply
        logger.info("Using provided geoid DEM object for conversion.")
        geoid_warped = geoid.reproject(dem, resampling="bilinear")
        dem -= geoid_warped

    elif isinstance(geoid, Literal) or geoid in ["Ellipsoid", "EGM08", "EGM96"]:
        # For known literal geoids, attempt automatic download
        if not dem.vcrs:
            raise ValueError(
                "The DEM must have a vertical coordinate system set before converting."
            )

        logger.info(
            f"Converting DEM to {geoid} vertical coordinate system using automatic data."
        )
        dem.to_vcrs(geoid, inplace=True)

    else:
        raise TypeError(
            "Geoid must be a known geoid name ('Ellipsoid', 'EGM08', 'EGM96'), file path, or xdem.DEM object."
        )

    if output_path is not None:
        # Save the output DEM
        output_path = Path(output_path)
        output_path.parent.mkdir(exist_ok=True, parents=True)
        dem.save(output_path, co_opts={"BIGTIFF": "YES"})
        logger.info(f"Saved converted DEM to {output_path}")

    return dem


def compute_difference(
    dem: xdem.DEM | Path, reference_dem: xdem.DEM | Path, output_diff_path: Path
) -> xdem.DEM:
    """
    Compute the difference between the DEM and a reference DEM.

    Parameters:
        dem (xdem.DEM | Path): The main DEM object or path to a DEM file.
        reference_dem (xdem.DEM | Path): The reference DEM object or path to a DEM file for comparison.
        output_diff_path (Path): Path to save the difference raster.

    Returns:
        xdem.DEM: Difference raster object.
    """
    # Load DEM from path if not already an xdem.DEM object
    if isinstance(dem, Path):
        logger.info(f"Loading main DEM from {dem}")
        dem = xdem.DEM(dem)
    elif not isinstance(dem, xdem.DEM):
        raise TypeError(
            "The 'dem' parameter must be either a Path or an xdem.DEM object."
        )

    # Load reference DEM from path if not already an xdem.DEM object
    if isinstance(reference_dem, Path):
        logger.info(f"Loading reference DEM from {reference_dem}")
        reference_dem = xdem.DEM(reference_dem)
    elif not isinstance(reference_dem, xdem.DEM):
        raise TypeError(
            "The 'reference_dem' parameter must be either a Path or an xdem.DEM object."
        )

    logger.info("Reprojecting reference DEM to match main DEM...")
    reference_dem_warped = reference_dem.reproject(dem, resampling="bilinear")

    logger.info("Computing difference between DEMs...")
    diff = dem - reference_dem_warped

    diff.save(output_diff_path)
    logger.info(f"Saved difference raster to {output_diff_path}")
    return diff


if __name__ == "__main__":
    dem_path = Path("outputs/swissalti3d_aletsch_2056_LV95_2m.tif.tif")
    chgeo2004_geoid_path = Path("geoid/Geoid_OGD/chgeo2004_htrans_ETRS.tif")
    egm08_geoid_path = Path("geoid/us_nga_egm2008_1.tif")
    target_crs = "32632"
    final_resolution = 5

    output_dir = Path("outputs")
    output_path = output_dir / f"swissalti3d_aletsch_{target_crs}_EGM08.tif"
    output_dir.mkdir(exist_ok=True, parents=True)

    # Step 1: Reproject DEM to ellipsoid and optionally to target CRS
    dem_ETRS89 = transform_ln02_to_ellipsoid(
        dem=dem_path,
        chgeo2004_geoid_path=chgeo2004_geoid_path,
        target_crs=target_crs,
    )

    # Step 2: Convert the vertical datum to EGM08
    dem_EGM08 = convert_dem_vertical_datum(
        dem=dem_ETRS89,
        geoid=egm08_geoid_path,
    )

    # Downsample and save the final DEM
    dem_EGM08 = dem_EGM08.reproject(res=final_resolution, resampling="bilinear")
    dem_EGM08.save(
        output_dir / f"swissalti3d_aletsch_{target_crs}_EGM08_{final_resolution}m.tif"
    )

    logger.info("Processing completed successfully.")
