# CRASH Part D: GraphDB loading, verification and visualisation

Files needed: `crash_schema.ttl`, `crash_data.ttl` (folder `iteration2/`).
Prefixes used in every query (paste at the top of each one):

```sparql
PREFIX :    <https://crash.example.org/ontology#>
PREFIX res: <https://crash.example.org/resource/>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
```

## 1. Steps in GraphDB (Workbench, http://localhost:7200)

1. **Setup > Repositories > Create new repository > GraphDB Repository.**
   Repository ID: `crash`. Ruleset: **OWL2-RL (Optimized)**. Leave the rest as default. Click Create, then click the repository to connect it (top-right dropdown shows `crash`).
2. **Import > Upload RDF files.** Upload `crash_schema.ttl` first, click Import, accept the defaults (base IRI `https://crash.example.org/`, no named graph). Wait for "Imported successfully".
3. Upload `crash_data.ttl` the same way. Import it second so the schema is already there (order does not change the final result under OWL2-RL, but the guide keeps it as agreed).
4. **Triple count:** run Query 1 below. Also visible at the bottom of the Workbench ("Total statements"). The explicit file triples are 171 (schema) + 30,865 (data) = 31,036. GraphDB shows a larger total because it counts inferred triples too (see section 3).
5. **SPARQL tab:** paste each query, press Run, and screenshot the result table (screenshot every query).
6. **Run R7 once** (Query 9), then the check (Query 10). GraphDB has no SWRL, so R7 is a SPARQL INSERT. Run the INSERT only once; running it again is harmless (it adds nothing new).
7. **Visual graph:** run Query 8 (CONSTRUCT) in the SPARQL tab. In the result bar choose **Visual** (next to Table/Raw Response). Take a screenshot. Double-click a node to expand it, click a node to see its properties. Take a second screenshot after expanding the LSOA node.
   Alternative: **Explore > Visual graph**, type `https://crash.example.org/resource/Collision_202560C002220` in the "Easy graph" box, press Visualise, then expand `hasVehicle`, `occurredIn`.
8. Save the queries (Save button in the SPARQL tab) and export results (Download as CSV) for the submission folders `SPARQL_Queries`, `Results`, `Visualization`.

## 2. Queries

**Q1 Triple count**
```sparql
SELECT (COUNT(*) AS ?triples) WHERE { ?s ?p ?o }
```

**Q2 Instances per class**
```sparql
PREFIX : <https://crash.example.org/ontology#>
SELECT ?class (COUNT(DISTINCT ?x) AS ?n) WHERE {
  VALUES ?class { :Collision :Vehicle :Casualty :LSOA :LocalAuthority :PoliceForce }
  ?x a ?class .
} GROUP BY ?class
```

**Q3 Integrity checks (all four must be 0)**
```sparql
PREFIX : <https://crash.example.org/ontology#>
SELECT
  (SUM(IF(?k = "vehicle", 1, 0))   AS ?vehiclesWithoutCollision)
  (SUM(IF(?k = "casualty", 1, 0))  AS ?casualtiesWithoutVehicle)
  (SUM(IF(?k = "collision", 1, 0)) AS ?collisionsWithoutLSOA)
  (SUM(IF(?k = "lsoa", 1, 0))      AS ?lsoasWithoutPoliceForce)
WHERE {
  { ?x a :Vehicle . FILTER NOT EXISTS { ?c :hasVehicle ?x } BIND("vehicle" AS ?k) }
  UNION { ?x a :Casualty . FILTER NOT EXISTS { ?v :hasCasualty ?x } BIND("casualty" AS ?k) }
  UNION { ?x a :Collision . FILTER NOT EXISTS { ?x :occurredIn ?l } BIND("collision" AS ?k) }
  UNION { ?x a :LSOA . FILTER NOT EXISTS { ?x :partOf/:partOf ?f . ?f a :PoliceForce } BIND("lsoa" AS ?k) }
}
```
(The last line uses a property path and also shows that `partOf` links every LSOA to a police force.)

**Q4 Severity breakdown**
```sparql
PREFIX : <https://crash.example.org/ontology#>
SELECT ?severity (COUNT(?c) AS ?n) WHERE {
  ?c a :Collision .
  OPTIONAL { ?c a :FatalCollision . BIND("Fatal" AS ?f) }
  OPTIONAL { ?c a :SeriousCollision . BIND("Serious" AS ?s) }
  BIND(COALESCE(?f, ?s, "Slight") AS ?severity)
} GROUP BY ?severity ORDER BY ?severity
```

**Q5 Inferred classes (needs OWL2-RL, nothing stored directly)**
```sparql
PREFIX : <https://crash.example.org/ontology#>
SELECT ?class (COUNT(DISTINCT ?x) AS ?n) WHERE {
  VALUES ?class { :KSICollision :VRUCollision :VulnerableRoadUser }
  ?x a ?class .
} GROUP BY ?class
```

**Q6 Inferred shortcut `involvesCasualty` (property chain, R6)**
```sparql
PREFIX : <https://crash.example.org/ontology#>
SELECT (COUNT(*) AS ?n) WHERE { ?c :involvesCasualty ?x }
```

**Q7 KSI collisions per local authority (multi-hop, aggregation, inference)**
```sparql
PREFIX : <https://crash.example.org/ontology#>
SELECT ?force ?localAuthority (COUNT(DISTINCT ?c) AS ?ksi) WHERE {
  ?c a :KSICollision ; :occurredIn ?l .
  ?l :partOf ?la .
  ?la a :LocalAuthority ; :areaName ?localAuthority ; :partOf ?pf .
  ?pf :areaName ?force .
} GROUP BY ?force ?localAuthority ORDER BY DESC(?ksi)
```

**Q8 One collision for the Visual graph (CONSTRUCT)**
Real collision: serious, one car, one pedestrian casualty, wet road, dark with lights lit, LSOA W01000105.
```sparql
PREFIX : <https://crash.example.org/ontology#>
PREFIX res: <https://crash.example.org/resource/>
CONSTRUCT {
  res:Collision_202560C002220 ?p ?o .
  ?v ?vp ?vo .
  ?x ?xp ?xo .
  ?l :partOf ?la . ?la :partOf ?pf .
} WHERE {
  res:Collision_202560C002220 ?p ?o .
  res:Collision_202560C002220 :hasVehicle ?v . ?v ?vp ?vo .
  OPTIONAL { ?v :hasCasualty ?x . ?x ?xp ?xo . }
  res:Collision_202560C002220 :occurredIn ?l . ?l :partOf ?la .
  ?la a :LocalAuthority ; :partOf ?pf .
}
```
If the picture is cluttered by inferred `owl:Thing` / `owl:sameAs` edges, hide them with the "Visual graph settings" (or untick "Include inferred" in the SPARQL tab toolbar).

**Q9 R7 HighRiskArea (SPARQL INSERT, exact text from the schema header)**
```sparql
PREFIX : <https://crash.example.org/ontology#>
INSERT { ?l a :HighRiskArea } WHERE {
  { SELECT ?l WHERE { ?c a :KSICollision ; :occurredIn ?l }
    GROUP BY ?l HAVING (COUNT(DISTINCT ?c) >= 3) }
}
```

**Q10 HighRiskArea check (run after Q9)**
```sparql
PREFIX : <https://crash.example.org/ontology#>
SELECT ?lsoa ?localAuthority ?force (COUNT(DISTINCT ?c) AS ?ksi) WHERE {
  ?l a :HighRiskArea ; :areaCode ?lsoa ; :partOf ?la .
  ?la a :LocalAuthority ; :areaName ?localAuthority ; :partOf ?pf .
  ?pf :areaName ?force .
  ?c a :KSICollision ; :occurredIn ?l .
} GROUP BY ?lsoa ?localAuthority ?force ORDER BY DESC(?ksi) ?lsoa
```
Quick count only: `SELECT (COUNT(DISTINCT ?l) AS ?n) WHERE { ?l a :HighRiskArea }`

## 3. Expected results

| Query | Expected result |
|---|---|
| Q1 | Explicit file triples: 171 + 30,865 = 31,036. GraphDB shows more (inferred triples too; the exact number depends on the GraphDB version, so just report what you see). |
| Q2 | Collision 1,115 · Vehicle 1,962 · Casualty 1,491 · LSOA 510 · LocalAuthority 11 · PoliceForce 2 |
| Q3 | 0, 0, 0, 0 |
| Q4 | Fatal 41 · Serious 391 · Slight 683 (total 1,115) |
| Q5 | KSICollision 432 · VRUCollision 520 · VulnerableRoadUser 546 |
| Q6 | 1,491 (every casualty reached through exactly one vehicle) |
| Q7 | Gwynedd 59, Newport 56, Wrexham 49, Flintshire 47, Denbighshire 42, Conwy 39, Caerphilly 35, Torfaen 34, Monmouthshire 31, Blaenau Gwent 23, Isle of Anglesey 17 (sum 432; Gwent = Newport, Caerphilly, Torfaen, Monmouthshire, Blaenau Gwent = 179; North Wales = 253) |
| Q8 | About 37 triples including a few inferred ones (owl:Thing, sameAs): the collision (Serious, KSI, VRU), 1 vehicle (Car, Turning left, driver 23), 1 pedestrian casualty (Serious), LSOA_W01000105 partOf LA partOf PoliceForce_60 (Gwynedd, North Wales) |
| Q9 | "Added 30 statements" (30 new `a :HighRiskArea` triples) |
| Q10 | 30 rows; top rows: W01000121 Conwy 5, W01000208 Denbighshire 5, W01000403 Wrexham 5, W01001971 Wrexham 5, then W01000105 Gwynedd 4 |

## 4. What was and was not verified

- Verified with rdflib 7 + owlrl (OWL-RL closure) on the real `crash_schema.ttl` + `crash_data.ttl`: Q2 to Q7, Q9 and Q10 gave exactly the numbers above; Q8 returned the collision with its vehicle, pedestrian casualty and LSOA/LA/force chain.
- Not verified: GraphDB itself. The total triple count (Q1 with inference), the look of the Visual graph, and whether GraphDB's OWL2-RL (Optimized) ruleset adds extra helper triples (e.g. `owl:sameAs`) were not tested. The inferred class counts (Q5, Q6) rely on GraphDB's OWL2-RL handling of `unionOf`, `someValuesFrom` and `propertyChainAxiom`; if Q5 shows 0 KSICollision, check that the repository ruleset is OWL2-RL and not RDFS, and re-import the data.
- In Q8 only the Serious collision `202560C002220` is used because it has exactly one vehicle and one pedestrian, so the picture is small and readable.
