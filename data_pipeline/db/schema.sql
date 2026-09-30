-- =====================================================================
-- Cyclone Early Warning System — PostGIS Schema
-- Owner: Person 1 (Geospatial & Data Engineer)
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_raster;

-- ---------------------------------------------------------------------
-- 1. Pilot regions (scope control — don't claim Bay-of-Bengal coverage)
-- ---------------------------------------------------------------------
CREATE TABLE pilot_regions (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,               -- e.g. 'Odisha Coast (Puri-Paradip)'
    bbox            GEOMETRY(POLYGON, 4326) NOT NULL,
    coastline       GEOMETRY(MULTILINESTRING, 4326),
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- ---------------------------------------------------------------------
-- 2. Historical cyclone tracks (IBTrACS)
-- ---------------------------------------------------------------------
CREATE TABLE cyclone_events (
    id              SERIAL PRIMARY KEY,
    sid             TEXT UNIQUE NOT NULL,         -- IBTrACS storm id, e.g. '2019129N10088' (Fani)
    name            TEXT,
    season          INT,
    basin           TEXT,                         -- 'NI' = North Indian Ocean
    source          TEXT DEFAULT 'IBTrACS'
);

CREATE TABLE cyclone_track_points (
    id              SERIAL PRIMARY KEY,
    event_id        INT REFERENCES cyclone_events(id) ON DELETE CASCADE,
    iso_time        TIMESTAMPTZ NOT NULL,
    geom            GEOMETRY(POINT, 4326) NOT NULL,
    wind_kt         NUMERIC,                       -- max sustained wind (knots)
    pressure_mb     NUMERIC,                       -- central pressure (millibars)
    storm_speed_kt  NUMERIC,
    storm_dir_deg   NUMERIC,
    rmw_nm          NUMERIC,                        -- radius of max winds (nautical miles), if available
    category        TEXT                            -- e.g. 'TS', 'HU', 'VSCS' depending on agency
);
CREATE INDEX idx_track_points_geom ON cyclone_track_points USING GIST (geom);
CREATE INDEX idx_track_points_event ON cyclone_track_points (event_id);

-- ---------------------------------------------------------------------
-- 3. Live/forecast met bulletins (IMD, JTWC, Open-Meteo, GFS)
-- ---------------------------------------------------------------------
CREATE TABLE met_bulletins (
    id              SERIAL PRIMARY KEY,
    source          TEXT NOT NULL,                 -- 'IMD' | 'JTWC' | 'OPEN_METEO' | 'GFS'
    storm_name      TEXT,
    issued_at       TIMESTAMPTZ,
    fetched_at      TIMESTAMPTZ DEFAULT now(),
    raw_text        TEXT,                          -- raw bulletin text (for Gemini layer to consume)
    raw_json        JSONB,                         -- structured payload where available
    geom            GEOMETRY(POINT, 4326)           -- current/forecast position if parsed
);
CREATE INDEX idx_bulletins_geom ON met_bulletins USING GIST (geom);
CREATE INDEX idx_bulletins_source_time ON met_bulletins (source, issued_at);

-- ---------------------------------------------------------------------
-- 4. Elevation / bathymetry (SRTM) — stored as raster tiles per region
-- ---------------------------------------------------------------------
CREATE TABLE elevation_tiles (
    id              SERIAL PRIMARY KEY,
    region_id       INT REFERENCES pilot_regions(id),
    rast            RASTER,
    source          TEXT DEFAULT 'SRTM',
    resolution_m    NUMERIC,
    fetched_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_elevation_rast ON elevation_tiles USING GIST (ST_ConvexHull(rast));

-- ---------------------------------------------------------------------
-- 5. Satellite scene metadata (Sentinel-1/2) — actual imagery stays in
--    GEE / cloud storage; we just index what's been pulled for reproducibility
-- ---------------------------------------------------------------------
CREATE TABLE satellite_scenes (
    id              SERIAL PRIMARY KEY,
    region_id       INT REFERENCES pilot_regions(id),
    collection      TEXT NOT NULL,                 -- e.g. 'COPERNICUS/S1_GRD'
    scene_id        TEXT NOT NULL,
    acquisition_time TIMESTAMPTZ,
    cloud_cover_pct NUMERIC,                        -- null for SAR (S1)
    footprint       GEOMETRY(POLYGON, 4326),
    gee_asset_path  TEXT,                            -- reference back to GEE asset/export
    export_path     TEXT,                            -- GCS/local path if exported
    fetched_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE(collection, scene_id)
);
CREATE INDEX idx_scenes_footprint ON satellite_scenes USING GIST (footprint);

-- ---------------------------------------------------------------------
-- 6. OSM infrastructure (power lines, roads, hospitals, shelters)
-- ---------------------------------------------------------------------
CREATE TABLE infrastructure (
    id              SERIAL PRIMARY KEY,
    region_id       INT REFERENCES pilot_regions(id),
    osm_id          BIGINT,
    osm_type        TEXT,                           -- 'node' | 'way' | 'relation'
    category        TEXT NOT NULL,                  -- 'hospital' | 'shelter' | 'power_line' | 'road' | ...
    subcategory     TEXT,                            -- e.g. highway=primary, power=line
    name            TEXT,
    tags            JSONB,
    geom            GEOMETRY(GEOMETRY, 4326) NOT NULL, -- point/line/polygon depending on category
    fetched_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_infra_geom ON infrastructure USING GIST (geom);
CREATE INDEX idx_infra_category ON infrastructure (category);

-- ---------------------------------------------------------------------
-- 7. Downstream tables (owned by Person 2/3, referenced here for FK completeness)
-- ---------------------------------------------------------------------
CREATE TABLE surge_estimates (
    id              SERIAL PRIMARY KEY,
    event_id        INT REFERENCES cyclone_events(id),
    region_id       INT REFERENCES pilot_regions(id),
    valid_time      TIMESTAMPTZ,
    surge_height_m  NUMERIC,
    method          TEXT,                            -- 'empirical' | 'ml_surrogate'
    geom            GEOMETRY(POLYGON, 4326),          -- inundation extent
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_surge_geom ON surge_estimates USING GIST (geom);

CREATE TABLE exposure_scores (
    id                  SERIAL PRIMARY KEY,
    surge_estimate_id   INT REFERENCES surge_estimates(id),
    infrastructure_id   INT REFERENCES infrastructure(id),
    exposure_level      TEXT,                         -- 'low' | 'medium' | 'high' | 'critical'
    score               NUMERIC,
    created_at          TIMESTAMPTZ DEFAULT now()
);

-- ---------------------------------------------------------------------
-- Seed the pilot region (Odisha coast) — adjust bbox as needed
-- ---------------------------------------------------------------------
INSERT INTO pilot_regions (name, bbox, coastline) VALUES (
    'Odisha Coast (Puri-Paradip)',
    ST_GeomFromText('POLYGON((85.5 19.5, 86.8 19.5, 86.8 20.6, 85.5 20.6, 85.5 19.5))', 4326),
    -- Simplified 3-point coastline approximation for the Puri stretch. This is
    -- a placeholder good enough for surge/flood modeling to run against --
    -- replace with a real digitized coastline (e.g. traced from OSM's
    -- natural=coastline ways, or a GEE-derived shoreline) before treating
    -- surge extents as anything more than illustrative.
    ST_GeomFromText('LINESTRING(85.70 19.70, 85.95 19.90, 86.20 20.20)', 4326)
);
