from dataclasses import dataclass
from typing import Optional


class ElevationGrid:
    def elevation_at(self, lon: float, lat: float) -> float:
        raise NotImplementedError


@dataclass
class SyntheticElevationGrid(ElevationGrid):
    """
    PLACEHOLDER MODEL -- flag this explicitly in the pitch if still in use by
    demo day. Approximates elevation as rising with distance from the
    coastline, capped at a max, with a small amount of deterministic
    "roughness" so the terrain isn't a perfectly flat ramp.

    coastline: shapely geometry (LineString/MultiLineString) in EPSG:4326.
    """
    coastline: object  # shapely LineString/MultiLineString
    meters_inland_per_meter_elevation: float = 800.0  # ~1m elevation gain per 800m inland, typical low delta gradient
    max_elevation_m: float = 25.0

    def elevation_at(self, lon: float, lat: float) -> float:
        from shapely.geometry import Point
        # crude degrees->meters conversion, fine at this scale/latitude (~20N)
        pt = Point(lon, lat)
        dist_deg = self.coastline.distance(pt)
        dist_m = dist_deg * 111_000
        # deterministic "roughness" so exposure scores aren't perfectly smooth
        roughness = ((hash((round(lon, 4), round(lat, 4))) % 100) / 100.0 - 0.5) * 0.6
        elev = dist_m / self.meters_inland_per_meter_elevation + roughness
        return max(0.0, min(elev, self.max_elevation_m))


@dataclass
class RasterElevationGrid(ElevationGrid):
    """Reads a real SRTM GeoTIFF exported by Person 1's gee_pipeline.py."""
    tif_path: str
    _dataset: Optional[object] = None

    def _ensure_open(self):
        if self._dataset is None:
            import rasterio
            self._dataset = rasterio.open(self.tif_path)

    def elevation_at(self, lon: float, lat: float) -> float:
        self._ensure_open()
        row, col = self._dataset.index(lon, lat)
        band = self._dataset.read(1)
        val = float(band[row, col])
        nodata = self._dataset.nodata
        if nodata is not None and val == nodata:
            return 0.0
        return val


def get_default_elevation_grid(coastline_geom=None, srtm_tif_path: Optional[str] = None) -> ElevationGrid:
    """
    Single switch point for the rest of the codebase. Pass `srtm_tif_path`
    once Person 1's real export is downloaded; until then this falls back to
    the synthetic model using the pilot region's coastline.
    """
    if srtm_tif_path:
        return RasterElevationGrid(tif_path=srtm_tif_path)
    if coastline_geom is None:
        raise ValueError(
            "No SRTM raster path given and no coastline geometry provided for "
            "the synthetic fallback -- pass one or the other."
        )
    return SyntheticElevationGrid(coastline=coastline_geom)
