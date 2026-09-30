
import argparse
import os
from datetime import datetime

import ee

from src.config import (
    GEE_SERVICE_ACCOUNT, GEE_PRIVATE_KEY_PATH, GEE_PROJECT_ID,
    PILOT_BBOX, PILOT_REGION_NAME, gee_bbox_ee_geometry,
)
from src.db import get_conn, get_pilot_region_id


def init_gee():
    """Initialize GEE using service account if configured, else fall back to
    interactive auth (useful for local testing)."""
    if GEE_SERVICE_ACCOUNT and os.path.exists(GEE_PRIVATE_KEY_PATH):
        credentials = ee.ServiceAccountCredentials(GEE_SERVICE_ACCOUNT, GEE_PRIVATE_KEY_PATH)
        ee.Initialize(credentials, project=GEE_PROJECT_ID)
        print(f"[gee] Initialized with service account {GEE_SERVICE_ACCOUNT}")
    else:
        
        try:
            ee.Initialize(project=GEE_PROJECT_ID)
        except Exception:
            ee.Authenticate()
            ee.Initialize(project=GEE_PROJECT_ID)
        print("[gee] Initialized with personal/cached credentials")


def get_sentinel1_scenes(region: ee.Geometry, start: str, end: str):
    """Sentinel-1 GRD (SAR) — works through cloud cover, critical during storms."""
    collection = (
        ee.ImageCollection("COPERNICUS/S1_GRD")
        .filterBounds(region)
        .filterDate(start, end)
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
    )
    return collection


def get_sentinel2_scenes(region: ee.Geometry, start: str, end: str, max_cloud_pct: float = 40):
    """Sentinel-2 optical, cloud-filtered (best-effort — cyclone weather means
    many scenes will still be heavily obscured; S1 is the primary source
    during active storms, S2 is for before/after comparison)."""
    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(region)
        .filterDate(start, end)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", max_cloud_pct))
    )
    return collection


def get_srtm_elevation(region: ee.Geometry):
    """SRTM 30m elevation/bathymetry proxy for the pilot region."""
    srtm = ee.Image("USGS/SRTMGL1_003").clip(region)
    return srtm


def scene_metadata_list(collection: ee.ImageCollection, collection_name: str):
    """Pull lightweight metadata (no pixel data) for indexing in PostGIS.
    Keeps actual imagery in GEE / exports it separately — see export_scene()."""
    def _extract(img):
        return ee.Feature(None, {
            "scene_id": img.get("system:index"),
            "acquisition_time": img.date().format("YYYY-MM-dd'T'HH:mm:ss'Z'"),
            "cloud_cover_pct": img.get("CLOUDY_PIXEL_PERCENTAGE"),  # null for S1, fine
            "footprint": img.geometry(),
        })

    features = collection.map(_extract)
    result = features.getInfo()  # client-side pull; fine for metadata-only, not pixels
    scenes = []
    for f in result["features"]:
        props = f["properties"]
        geom = f["geometry"]
        scenes.append({
            "collection": collection_name,
            "scene_id": props.get("scene_id"),
            "acquisition_time": props.get("acquisition_time"),
            "cloud_cover_pct": props.get("cloud_cover_pct"),
            "geojson": geom,
        })
    return scenes


def export_scene_to_drive(image: ee.Image, description: str, region: ee.Geometry, scale: int = 10):
    """Kick off an async export to Google Drive. GEE exports are batch jobs —
    check status at https://code.earthengine.google.com/tasks or via
    ee.batch.Task.list(). For a hackathon demo, exporting 1-2 key scenes per
    pilot region (pre-landfall + landfall) is enough; don't bulk-export
    everything, it's slow and mostly unnecessary for the dashboard."""
    task = ee.batch.Export.image.toDrive(
        image=image,
        description=description,
        folder="cyclone_pipeline_exports",
        region=region,
        scale=scale,
        maxPixels=1e9,
    )
    task.start()
    print(f"[gee] Export task started: {description} (task id: {task.id})")
    return task


def save_scenes_to_db(scenes: list, region_id: int):
    if not scenes:
        print("[gee] No scenes to save.")
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            for s in scenes:
                cur.execute(
                    """
                    INSERT INTO satellite_scenes
                        (region_id, collection, scene_id, acquisition_time,
                         cloud_cover_pct, footprint)
                    VALUES (%s, %s, %s, %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))
                    ON CONFLICT (collection, scene_id) DO NOTHING
                    """,
                    (
                        region_id, s["collection"], s["scene_id"], s["acquisition_time"],
                        s["cloud_cover_pct"], str(s["geojson"]).replace("'", '"'),
                    ),
                )
    print(f"[gee] Saved {len(scenes)} scene records to satellite_scenes.")


def main():
    parser = argparse.ArgumentParser(description="Pull Sentinel-1/2 + SRTM metadata for pilot region")
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    parser.add_argument("--tag", default="run", help="Label for this pull, e.g. cyclone name")
    parser.add_argument("--export-srtm", action="store_true", help="Also kick off an SRTM export job")
    args = parser.parse_args()

    init_gee()
    region = gee_bbox_ee_geometry()

    print(f"[gee] Pilot region bbox: {PILOT_BBOX}")
    print(f"[gee] Pulling Sentinel-1 scenes {args.start} -> {args.end} ...")
    s1 = get_sentinel1_scenes(region, args.start, args.end)
    s1_scenes = scene_metadata_list(s1, "COPERNICUS/S1_GRD")
    print(f"[gee] Found {len(s1_scenes)} Sentinel-1 scenes")

    print(f"[gee] Pulling Sentinel-2 scenes {args.start} -> {args.end} ...")
    s2 = get_sentinel2_scenes(region, args.start, args.end)
    s2_scenes = scene_metadata_list(s2, "COPERNICUS/S2_SR_HARMONIZED")
    print(f"[gee] Found {len(s2_scenes)} Sentinel-2 scenes")

    with get_conn() as conn:
        with conn.cursor() as cur:
            region_id = get_pilot_region_id(cur, PILOT_REGION_NAME)

    save_scenes_to_db(s1_scenes, region_id)
    save_scenes_to_db(s2_scenes, region_id)

    if args.export_srtm:
        srtm = get_srtm_elevation(region)
        export_scene_to_drive(srtm, f"srtm_{args.tag}", region, scale=30)

    print("[gee] Done.")


if __name__ == "__main__":
    main()
