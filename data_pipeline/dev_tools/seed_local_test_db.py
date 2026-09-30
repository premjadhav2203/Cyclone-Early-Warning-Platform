
import psycopg2

conn = psycopg2.connect(host="localhost", dbname="cyclone_db", user="cyclone", password="cyclone_dev_pw")
cur = conn.cursor()

cur.execute("""
    INSERT INTO cyclone_events (sid, name, season, basin, source)
    VALUES ('2019129N10088', 'FANI', 2019, 'NI', 'IBTrACS')
    ON CONFLICT (sid) DO UPDATE SET name = EXCLUDED.name
    RETURNING id
""")
event_id = cur.fetchone()[0]

track_points = [
    ("2019-05-02T18:00:00Z", 86.60, 18.90, 100, 938, 11, 25),
    ("2019-05-03T00:00:00Z", 86.30, 19.30, 105, 932, 10, 25),
    ("2019-05-03T06:00:00Z", 85.90, 19.80, 100, 938, 12, 28),
]
for iso_time, lon, lat, wind_kt, pressure_mb, storm_speed_kt, rmw_nm in track_points:
    cur.execute("""
        INSERT INTO cyclone_track_points
            (event_id, iso_time, geom, wind_kt, pressure_mb, storm_speed_kt, rmw_nm, category)
        VALUES (%s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s, %s, %s, 'VSCS')
    """, (event_id, iso_time, lon, lat, wind_kt, pressure_mb, storm_speed_kt, rmw_nm))


cur.execute("SELECT id FROM pilot_regions WHERE name = 'Odisha Coast (Puri-Paradip)'")
region_id = cur.fetchone()[0]

infra = [
    ("hospital", "Puri District Hospital", "POINT(85.815 19.803)"),
    ("shelter", "Cyclone Shelter 4", "POINT(85.79 19.79)"),
    ("power_line", "132kV feeder", "LINESTRING(85.78 19.77, 85.83 19.81)"),
    ("road", "NH-16 stretch", "LINESTRING(86.0 19.9, 86.2 20.0)"),
]
for category, name, wkt in infra:
    cur.execute("""
        INSERT INTO infrastructure (region_id, category, name, geom)
        VALUES (%s, %s, %s, ST_SetSRID(ST_GeomFromText(%s), 4326))
    """, (region_id, category, name, wkt))

conn.commit()
cur.close()
conn.close()
print("Seed complete: coastline set, Fani track (3 points) + 4 infrastructure features inserted.")
