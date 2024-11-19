import json
import logging
import os
from pathlib import Path
from typing import Dict, List

import rasterio
from joblib import Parallel, delayed
from rasterio.merge import merge
from tqdm import tqdm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger()
logger.setLevel(logging.INFO)


# Extract the third number from the filename
def get_chunk_id(file_path: Path) -> int:
    return int(file_path.stem.split("_")[2].split("-")[0])


def create_chunks(
    tiles_paths: List[Path], approach: str = "filename", max_tiles: int = 100
) -> Dict[int, List[Path]]:
    """
    Create chunks of tiles based on a maximum number of tiles per chunk.

    Parameters:
        tiles_paths (List[Path]): List of paths to raster tiles.
        approach (str): Approach to use for creating chunks. Options are "sequential" or "filename".
        max_tiles (int): Maximum number of tiles per chunk.

    Returns:
        Dict[int, List[Path]]: Dictionary with chunk numbers as keys and list of tile paths as values.
    """
    logger.info(f"Creating chunks of maximum {max_tiles} tiles each...")

    if approach == "sequential":
        # Divide the tiles into chunks based on the maximum number of tiles per chunk
        chunks = {
            i: tiles_paths[i : i + max_tiles]
            for i in range(0, len(tiles_paths), max_tiles)
        }

    elif approach == "filename":
        # Each file is named with this pattern:
        # "swissalti3d_2019_2654-1137_2_2056_5728"
        # subdide time images in chunks based on the third number in the filename ("2654" in the example above)

        # Sort the files based on the third number in the filename
        sorted_tiles = sorted(tiles_paths, key=get_chunk_id)
        chunks = {}
        for i, tile in enumerate(sorted_tiles):
            chunk_id = get_chunk_id(tile)
            if chunk_id not in chunks:
                chunks[chunk_id] = []
            chunks[chunk_id].append(tile)

    return chunks


def merge_rasters(rasters: List[Path], ouput_path: Path) -> Path:
    # Open all the rasters using rasterio
    logger.info("Opening raster tiles...")

    datasets = []
    for raster in rasters:
        try:
            datasets.append(rasterio.open(raster))
        except Exception as e:
            logger.error(f"Error opening raster {raster}: {e}")
            return None

    # Merge the datasets
    logger.info("Merging raster tiles...")

    merged, out_transform = merge(datasets)

    # Extract metadata from the first raster to use as the base for the output
    logger.info("Saving merged raster...")
    out_meta = datasets[0].meta.copy()
    out_meta.update(
        {
            "driver": "GTiff",
            "height": merged.shape[1],
            "width": merged.shape[2],
            "transform": out_transform,
        }
    )
    with rasterio.open(ouput_path, "w", **out_meta) as dest:
        dest.write(merged)

    # Close all datasets
    for dataset in datasets:
        dataset.close()

    return ouput_path


def merge_tiles_chunk(tiles_paths: List[Path], chunk_id: int, out_dir: Path) -> Path:
    """
    Merge a chunk of raster tiles into a single raster and save it as a temporary file.

    Parameters:
        tiles_paths (List[Path]): List of paths to raster tiles in the chunk.
        chunk_id (int): Identifier for the chunk.
        out_dir (Path): Directory to save the intermediate merged chunk file.

    Returns:
        Path: Path to the saved intermediate merged chunk file.
    """
    chunk_output_path = out_dir / f"merged_chunk_{chunk_id}.tif"
    logger.info(f"Merging chunk {chunk_id} with {len(tiles_paths)} tiles...")

    chunk_output_path = merge_rasters(tiles_paths, chunk_output_path)

    logger.info(f"Finished merging chunk {chunk_id}. Saved to {chunk_output_path}")

    return chunk_output_path


def merge_tiles(
    tiles_paths: List[Path],
    output_path: Path = None,
    max_chunk_tiles: int = 100,
    parallel: bool = False,
    processes: int = -1,
    keep_temp_files: bool = True,
) -> Path:
    """
    Merge multiple raster tiles into a single raster.

    Parameters:
        tiles_paths (List[Path]): List of paths to raster tiles.
        output_path (Path, optional): Path to save the merged raster.
        max_tiles (int, optional): Maximum number of tiles to process in a single chunk.

    Returns:
        Path: Path to the saved merged raster.
    """
    if not tiles_paths:
        raise ValueError("No tiles found for merging.")
    logger.info(f"Found {len(tiles_paths)} tiles to merge.")

    if len(tiles_paths) <= max_chunk_tiles:
        merged_raster = merge_rasters(tiles_paths, output_path)
        # merged_raster = gu.raster.merge_rasters(
        #     [gu.Raster(tile) for tile in tiles_paths], progress=True
        # )

        return merged_raster

    logger.info(
        f"The number of tiles exceeds the maximum chunk size of {max_chunk_tiles}. Splitting into chunks..."
    )

    # Create a temporary directory for storing intermediate merged chunks
    temp_dir_path = Path("tmp")
    temp_dir_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"Temporary directory for chunks: {temp_dir_path}")

    # Create chunks of tiles based on the max number of tiles per chunk
    chunks = create_chunks(tiles_paths, approach="filename")

    # Write the chunks to a JSON file
    with open(temp_dir_path / "chunks.json", "w") as f:
        file_names_dict = {
            chunk_id: [str(path.name) for path in chunk_paths]
            for chunk_id, chunk_paths in chunks.items()
        }
        json.dump(file_names_dict, f, indent=4)

    logger.info(f"Created {len(chunks)} chunks of tiles to merge.")

    # Merge each chunk
    if parallel:
        if processes == -1:
            processes = os.cpu_count()

        logger.info("Starting parallel merging of chunks...")
        with Parallel(n_jobs=processes, verbose=10) as parallel:
            chunk_files = parallel(
                delayed(merge_tiles_chunk)(chunk_paths, chunk_id, temp_dir_path)
                for chunk_id, chunk_paths in chunks.items()
            )
    else:
        chunk_files = []
        for chunk_id, chunk_paths in tqdm(chunks.items()):
            chunk_file = merge_tiles_chunk(chunk_paths, chunk_id, temp_dir_path)
            chunk_files.append(chunk_file)

    # Merge all temporary chunk files into the final output
    logger.info("Merging all chunks into the final raster...")
    merged_raster = merge_rasters(chunk_files, output_path)

    # Clean up temporary files if needed
    if not keep_temp_files:
        logger.info("Cleaning up temporary files...")
        for chunk_file in chunk_files:
            chunk_file.unlink()
        temp_dir_path.rmdir()

    logger.info("Merging process completed.")

    return merged_raster


if __name__ == "__main__":
    # tiles_dir = Path("./aletsch_tiles")
    # dem_ext = ".tif"
    # merged_dem_path = Path("aletsch_merged.tif")

    # # Get list of DEM tiles
    # tiles_paths = sorted(tiles_dir.glob(f"*{dem_ext}"), key=get_chunk_id)
    # if not tiles_paths:
    #     raise ValueError("No DEM tiles found.")

    # # find the index of the first tile that contains the number 2620 in the filename and exclude all tiles before that from the list
    # # start_index = 0
    # # for i, tile in enumerate(tiles_paths):
    # #     if "2620" in tile.name:
    # #         start_index = i
    # #         break
    # # tiles_paths2 = tiles_paths[start_index:]

    # # chunk_id = "2588"
    # # selected_tiles = [tile for tile in tiles_paths2 if chunk_id in tile.name]

    # # Merge tiles
    # merged_dem = merge_tiles(tiles_paths, merged_dem_path, parallel=True)

    tile0 = "aletsch_merged.tif"
    tile1 = "swissalti3d_2019_2620-1168_2_2056_5728.tif"
    merged_dem = merge_tiles([tile0, tile1], "aletsch_merged2.tif")
