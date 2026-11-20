"""CRASH Part C: clean the STATS19 2025 CSVs and convert them to RDF instance data (A-Box).

Input : the three STATS19 2025 CSVs + the DfT data guide (xlsx), in DATA_DIR.
Output: crash_data.ttl (instance data that conforms to crash_schema.ttl), then
        validation checks printed to the console.

Run   : python -I crash_build_abox.py [DATA_DIR] [OUT_TTL]
        DATA_DIR defaults to the folder this script is in; OUT_TTL defaults to DATA_DIR/crash_data.ttl.
Needs : pip install pandas openpyxl rdflib
"""
import sys
from pathlib import Path

import pandas as pd
from rdflib import Graph, Literal, Namespace, RDF, XSD

DATA_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
OUT_TTL = Path(sys.argv[2]) if len(sys.argv) > 2 else DATA_DIR / "crash_data.ttl"

ONT = Namespace("https://crash.example.org/ontology#")
RES = Namespace("https://crash.example.org/resource/")
FORCES = {"60": "North Wales", "61": "Gwent"}
MOTORCYCLE = {"2", "3", "4", "5", "23", "97"}

# ---------------------------------------------------------------- 1. load
def read(name):
    return pd.read_csv(DATA_DIR / f"dft-road-casualty-statistics-{name}-2025.csv", dtype=str).apply(
        lambda s: s.str.strip())

col = read("collision")
veh = read("vehicle")
cas = read("casualty")

# ---------------------------------------------------------------- 2. clean
# 2a. sample: all collisions of North Wales (60) and Gwent (61) police
col = col[col.police_force.isin(FORCES)]
ids = set(col.collision_index)
veh = veh[veh.collision_index.isin(ids)]
cas = cas[cas.collision_index.isin(ids)]

# 2b. keep only the columns the schema uses (drops *_historic, flags, adjusted severity, IMD, etc.)
col = col[["collision_index", "police_force", "collision_severity", "date", "local_authority_ons_district",
           "first_road_class", "road_type", "speed_limit", "junction_detail", "light_conditions",
           "weather_conditions", "road_surface_conditions", "lsoa_of_accident_location"]]
veh = veh[["collision_index", "vehicle_reference", "vehicle_type", "vehicle_manoeuvre", "age_of_driver"]]
cas = cas[["collision_index", "vehicle_reference", "casualty_reference", "casualty_class",
           "casualty_severity", "casualty_type", "age_band_of_casualty"]]

# 2c. duplicates and referential integrity
assert col.collision_index.is_unique
assert not veh.duplicated(["collision_index", "vehicle_reference"]).any()
assert not cas.duplicated(["collision_index", "casualty_reference"]).any()
veh_keys = set(zip(veh.collision_index, veh.vehicle_reference))
assert all(k in veh_keys for k in zip(cas.collision_index, cas.vehicle_reference)), "casualty without vehicle"

# 2d. ISO dates (dd/mm/yyyy -> yyyy-mm-dd)
col["date"] = pd.to_datetime(col["date"], format="%d/%m/%Y").dt.strftime("%Y-%m-%d")

# 2e. code -> label lookup from the data guide (sheet 2024_code_list)
guide = pd.read_excel(DATA_DIR / "dft-road-casualty-statistics-road-safety-open-dataset-data-guide-2025.xlsx",
                      sheet_name="2024_code_list", dtype=str).dropna(subset=["code/format"])
LOOKUP = {}
for _, r in guide.iterrows():
    LOOKUP.setdefault(r["field name"], {}).setdefault(r["code/format"].strip(), str(r["label"]).strip())

def label(field, code):
    lab = LOOKUP[field].get(code)
    if code in {"-1", "99"} or lab is None or lab.lower().startswith("unknown"):
        return "Unknown"
    return lab

def number(code):
    """Integer value, or None when missing (-1) or self-reported unknown (99)."""
    return None if code in {"-1", "99"} else int(code)

# ---------------------------------------------------------------- 3. transform
g = Graph()
g.bind("", ONT)
g.bind("res", RES)
g.bind("xsd", XSD)

def add(s, p, o):
    if o is not None:
        g.add((s, p, o))

def text(v):
    return Literal(v)  # plain literal = xsd:string in RDF 1.1

def integer(v):
    return None if v is None else Literal(v, datatype=XSD.integer)

# areas: police force -> local authority -> LSOA
for code, name in FORCES.items():
    pf = RES[f"PoliceForce_{code}"]
    g.add((pf, RDF.type, ONT.PoliceForce))
    g.add((pf, ONT.areaCode, text(code)))
    g.add((pf, ONT.areaName, text(name)))

for la_code, force in col.groupby("local_authority_ons_district").police_force.first().items():
    la = RES[f"LA_{la_code}"]
    g.add((la, RDF.type, ONT.LocalAuthority))
    g.add((la, ONT.areaCode, text(la_code)))
    g.add((la, ONT.areaName, text(LOOKUP["local_authority_ons_district"][la_code])))
    g.add((la, ONT.partOf, RES[f"PoliceForce_{force}"]))

for lsoa_code, la_code in col.groupby("lsoa_of_accident_location").local_authority_ons_district.first().items():
    lsoa = RES[f"LSOA_{lsoa_code}"]
    g.add((lsoa, RDF.type, ONT.LSOA))
    g.add((lsoa, ONT.areaCode, text(lsoa_code)))
    g.add((lsoa, ONT.partOf, RES[f"LA_{la_code}"]))

# collisions
SEVERITY_CLASS = {"1": ONT.FatalCollision, "2": ONT.SeriousCollision, "3": ONT.Collision}
for r in col.itertuples(index=False):
    c = RES[f"Collision_{r.collision_index}"]
    g.add((c, RDF.type, SEVERITY_CLASS[r.collision_severity]))
    g.add((c, ONT.collisionIndex, text(r.collision_index)))
    g.add((c, ONT.collisionDate, Literal(r.date, datatype=XSD.date)))
    add(c, ONT.speedLimit, integer(number(r.speed_limit)))
    g.add((c, ONT.roadClass, text(label("first_road_class", r.first_road_class))))
    g.add((c, ONT.roadType, text(label("road_type", r.road_type))))
    g.add((c, ONT.junctionType, text(label("junction_detail", r.junction_detail))))
    g.add((c, ONT.lightCondition, text(label("light_conditions", r.light_conditions))))
    g.add((c, ONT.weatherCondition, text(label("weather_conditions", r.weather_conditions))))
    g.add((c, ONT.surfaceCondition, text(label("road_surface_conditions", r.road_surface_conditions))))
    g.add((c, ONT.occurredIn, RES[f"LSOA_{r.lsoa_of_accident_location}"]))

# vehicles
for r in veh.itertuples(index=False):
    v = RES[f"Vehicle_{r.collision_index}_{r.vehicle_reference}"]
    g.add((v, RDF.type, ONT.Vehicle))
    g.add((RES[f"Collision_{r.collision_index}"], ONT.hasVehicle, v))
    g.add((v, ONT.vehicleType, text(label("vehicle_type", r.vehicle_type))))
    g.add((v, ONT.vehicleManoeuvre, text(label("vehicle_manoeuvre", r.vehicle_manoeuvre))))
    add(v, ONT.driverAge, integer(number(r.age_of_driver)))

# casualties (asserted as the most specific road-user class)
def casualty_class(t):
    if t == "0":
        return ONT.Pedestrian
    if t == "1":
        return ONT.Cyclist
    if t in MOTORCYCLE:
        return ONT.Motorcyclist
    return ONT.Casualty

for r in cas.itertuples(index=False):
    k = RES[f"Casualty_{r.collision_index}_{r.casualty_reference}"]
    g.add((k, RDF.type, casualty_class(r.casualty_type)))
    g.add((RES[f"Vehicle_{r.collision_index}_{r.vehicle_reference}"], ONT.hasCasualty, k))
    g.add((k, ONT.casualtySeverity, text(label("casualty_severity", r.casualty_severity))))
    g.add((k, ONT.casualtyClass, text(label("casualty_class", r.casualty_class))))
    add(k, ONT.casualtyAgeBand, integer(number(r.age_band_of_casualty)))

OUT_TTL.parent.mkdir(parents=True, exist_ok=True)
header = ("# CRASH instance data (A-Box): STATS19 2025, North Wales (60) + Gwent (61) police.\n"
          "# Built by crash_build_abox.py from the DfT Road Safety Open Data (OGL v3.0).\n"
          "# Schema: crash_schema.ttl (https://crash.example.org/ontology#).\n")
OUT_TTL.write_text(header + g.serialize(format="turtle"), encoding="utf-8")

# ---------------------------------------------------------------- 4. validate (re-parse the written file)
h = Graph().parse(OUT_TTL, format="turtle")
P = "PREFIX : <https://crash.example.org/ontology#> "

def ask_count(q):
    return int(next(iter(h.query(P + q)))[0])

print(f"Wrote {OUT_TTL}")
print(f"Triples: {len(h)}")
print("Instances per asserted class:")
for cls in ["Collision", "FatalCollision", "SeriousCollision", "Vehicle", "Casualty", "Pedestrian",
            "Cyclist", "Motorcyclist", "LSOA", "LocalAuthority", "PoliceForce"]:
    print(f"  {cls:18s} {ask_count(f'SELECT (COUNT(?x) AS ?n) WHERE {{ ?x a :{cls} }}')}")

checks = {
    "collisions = 1115": (ask_count("SELECT (COUNT(DISTINCT ?c) AS ?n) WHERE { ?c :collisionIndex ?i }"), 1115),
    "vehicles = 1962": (ask_count("SELECT (COUNT(DISTINCT ?v) AS ?n) WHERE { ?c :hasVehicle ?v }"), 1962),
    "casualties = 1491": (ask_count("SELECT (COUNT(DISTINCT ?k) AS ?n) WHERE { ?v :hasCasualty ?k }"), 1491),
    "KSI collisions (fatal + serious) = 432": (ask_count(
        "SELECT (COUNT(?c) AS ?n) WHERE { { ?c a :FatalCollision } UNION { ?c a :SeriousCollision } }"), 432),
    "LSOAs = 510": (ask_count("SELECT (COUNT(?l) AS ?n) WHERE { ?l a :LSOA }"), 510),
    "vehicles without a collision = 0": (ask_count(
        "SELECT (COUNT(?v) AS ?n) WHERE { ?v a :Vehicle FILTER NOT EXISTS { ?c :hasVehicle ?v } }"), 0),
    "casualties without a vehicle = 0": (ask_count(
        "SELECT (COUNT(?k) AS ?n) WHERE { ?k :casualtySeverity ?s FILTER NOT EXISTS { ?v :hasCasualty ?k } }"), 0),
    "collisions without an LSOA = 0": (ask_count(
        "SELECT (COUNT(?c) AS ?n) WHERE { ?c :collisionIndex ?i FILTER NOT EXISTS { ?c :occurredIn ?l } }"), 0),
    "LSOAs with full LSOA->LA->PoliceForce chain = 510": (ask_count(
        "SELECT (COUNT(?l) AS ?n) WHERE { ?l a :LSOA ; :partOf ?la . ?la a :LocalAuthority ; :partOf ?pf . "
        "?pf a :PoliceForce }"), 510),
    "HighRiskArea candidates (LSOA with >= 3 KSI) = 30": (ask_count(
        "SELECT (COUNT(?l) AS ?n) WHERE { SELECT ?l WHERE { { ?c a :FatalCollision } UNION "
        "{ ?c a :SeriousCollision } ?c :occurredIn ?l } GROUP BY ?l HAVING (COUNT(DISTINCT ?c) >= 3) }"), 30),
}
print("Validation checks:")
ok = True
for name, (got, want) in checks.items():
    ok &= got == want
    print(f"  [{'PASS' if got == want else 'FAIL'}] {name} (got {got})")
sys.exit(0 if ok else 1)
