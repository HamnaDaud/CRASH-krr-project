# CRASH Part E: SPARQL queries and symbolic reasoning

Data: crash_schema.ttl + crash_data.ttl, OWL2-RL inference (R1-R6) and the R7 HighRiskArea INSERT applied (30 LSOAs).
Every query below was run on the real files with rdflib + owlrl; the results are real. Not verified: GraphDB itself (same SPARQL 1.1, but row order of ties may differ).

Prefixes used in every query:
```sparql
PREFIX :    <https://crash.example.org/ontology#>
PREFIX res: <https://crash.example.org/resource/>
```
Turn "Include inferred" ON in GraphDB for Q2, Q3, Q4, Q6, Q7, Q8, Q10.

---
## Part 1: SPARQL queries

### Q1 (CQ12-style): fatal collisions on fast roads
Features: basic graph pattern, FILTER.
```sparql
SELECT ?c ?date ?roadClass ?speed WHERE {
  ?c a :FatalCollision ; :collisionDate ?date ; :roadClass ?roadClass ; :speedLimit ?speed .
  FILTER(?speed >= 60)
} ORDER BY ?date
```
Expected: 19 rows. First: Collision_202560C013816 (2025-01-30, A, 60), Collision_202560C015671 (2025-02-02, A, 60), Collision_202560C031158 (2025-03-06, A, 60).

### Q2 (CQ1): vehicle types in collisions with a vulnerable road user
Features: multi-hop (Collision to Vehicle), aggregation, inference (VRUCollision is never stored).
```sparql
SELECT ?vehicleType (COUNT(DISTINCT ?c) AS ?collisions) WHERE {
  ?c a :VRUCollision ; :hasVehicle ?v .
  ?v :vehicleType ?vehicleType .
} GROUP BY ?vehicleType ORDER BY DESC(?collisions)
```
Expected: 19 rows. Car 382, Pedal cycle 149, Motorcycle over 500cc 86, Motorcycle 125cc and under 63, Van / Goods 3.5 tonnes mgw or under 39, Motorcycle over 125cc and up to 500cc 26.

### Q3 (CQ2): top 5 local authorities, serious or fatal collisions on A roads, wet or icy
Features: FILTER, aggregation (GROUP BY, ORDER BY, LIMIT), multi-hop, inference (KSICollision).
```sparql
SELECT ?localAuthority (COUNT(DISTINCT ?c) AS ?ksi) WHERE {
  ?c a :KSICollision ; :roadClass "A" ; :surfaceCondition ?s ; :occurredIn ?l .
  FILTER(?s IN ("Wet or damp", "Frost or ice"))
  ?l :partOf ?la . ?la a :LocalAuthority ; :areaName ?localAuthority .
} GROUP BY ?localAuthority ORDER BY DESC(?ksi) LIMIT 5
```
Expected: 5 rows. Denbighshire 9, Flintshire 8, Wrexham 7, Conwy 6, Caerphilly 5.

### Q4 (CQ3): HighRiskArea LSOAs with local authority and police force
Features: property path (partOf+), multi-hop, aggregation, inference (HighRiskArea via R7, partOf transitive).
```sparql
SELECT ?lsoa ?localAuthority ?force (COUNT(DISTINCT ?c) AS ?ksi) WHERE {
  ?l a :HighRiskArea ; :areaCode ?lsoa ; :partOf+ ?pf .
  ?pf a :PoliceForce ; :areaName ?force .
  ?l :partOf ?la . ?la a :LocalAuthority ; :areaName ?localAuthority .
  ?c a :KSICollision ; :occurredIn ?l .
} GROUP BY ?lsoa ?localAuthority ?force ORDER BY DESC(?ksi) ?lsoa
```
Expected: 30 rows. W01000121 Conwy North Wales 5; W01000208 Denbighshire North Wales 5; W01000403 Wrexham North Wales 5; W01001971 Wrexham North Wales 5; W01000105 Gwynedd North Wales 4; W01000203 Denbighshire North Wales 4.

### Q5 (CQ4/CQ7 style): fatal or serious pedestrian and cyclist casualties
Features: UNION, FILTER, aggregation, inference (Pedestrian/Cyclist are VulnerableRoadUser).
```sparql
SELECT ?type (COUNT(DISTINCT ?x) AS ?casualties) WHERE {
  { ?x a :Pedestrian . BIND("Pedestrian" AS ?type) }
  UNION
  { ?x a :Cyclist . BIND("Cyclist" AS ?type) }
  ?x :casualtySeverity ?sev .
  FILTER(?sev IN ("Fatal", "Serious"))
} GROUP BY ?type
```
Expected: 2 rows. Pedestrian 81, Cyclist 54.

### Q6: HighRiskArea LSOAs per local authority
Features: OPTIONAL, aggregation, inference (R7).
```sparql
SELECT ?localAuthority (COUNT(DISTINCT ?l) AS ?highRiskLSOAs) WHERE {
  ?la a :LocalAuthority ; :areaName ?localAuthority .
  OPTIONAL { ?l :partOf ?la ; a :HighRiskArea . }
} GROUP BY ?localAuthority ORDER BY DESC(?highRiskLSOAs) ?localAuthority
```
Expected: 11 rows (all 11 authorities, sum 30). Denbighshire 6, Gwynedd 6, Flintshire 3, Wrexham 3, Conwy 2, Isle of Anglesey 2, Monmouthshire 2, Newport 2, Torfaen 2, Blaenau Gwent 1, Caerphilly 1. (OPTIONAL keeps an authority with 0 high-risk LSOAs in the list; none has 0 in this sample.)

### Q7 (CQ6): Gwent serious or fatal collisions, and how many involved a vulnerable road user
Features: property path (occurredIn/partOf+), OPTIONAL, aggregation, inference (KSICollision, VRUCollision).
```sparql
SELECT (COUNT(DISTINCT ?c) AS ?ksi) (COUNT(DISTINCT ?vru) AS ?withVRU) WHERE {
  ?c a :KSICollision ; :occurredIn/:partOf+ ?pf .
  ?pf a :PoliceForce ; :areaName "Gwent" .
  OPTIONAL { ?c a :VRUCollision . BIND(?c AS ?vru) }
}
```
Expected: 1 row: ksi 179, withVRU 113.

### Q8 (CQ13): serious or fatal collisions with a vulnerable road user, per HighRiskArea
Features: multi-hop, aggregation, inference (three derived classes together).
```sparql
SELECT ?lsoa (COUNT(DISTINCT ?c) AS ?ksiVRU) WHERE {
  ?l a :HighRiskArea ; :areaCode ?lsoa .
  ?c a :KSICollision , :VRUCollision ; :occurredIn ?l .
} GROUP BY ?lsoa ORDER BY DESC(?ksiVRU) ?lsoa
```
Expected: 26 rows. W01001971 5, W01001662 4, W01000040 3, W01000208 3, W01001524 3, W01001980 3.

### Q9 (CQ12): full record of one collision
Features: multi-hop (3 hops), property path (occurredIn/partOf), basic pattern.
```sparql
SELECT ?c ?light ?weather ?vehicleType ?casualty ?severity ?la ?force WHERE {
  BIND(res:Collision_202560C002220 AS ?c)
  ?c :lightCondition ?light ; :weatherCondition ?weather ; :hasVehicle ?v ;
     :occurredIn/:partOf ?laIri .
  ?v :vehicleType ?vehicleType .
  ?v :hasCasualty ?x . ?x :casualtySeverity ?severity .
  ?laIri :areaName ?la ; :partOf ?pf . ?pf :areaName ?force .
  BIND(STRAFTER(STR(?x), "resource/") AS ?casualty)
}
```
Expected: 1 row: Collision_202560C002220, Darkness - lights lit, Raining no high winds, Car, Casualty_202560C002220_1, Serious, Gwynedd, North Wales.

### Q10 (CQ10): motorcyclists seriously or fatally hurt on roads with limit 50+
Features: FILTER with && and IN, multi-hop via the inferred involvesCasualty shortcut, inference.
```sparql
SELECT ?c ?speed ?severity WHERE {
  ?c a :KSICollision ; :speedLimit ?speed ; :involvesCasualty ?x .
  ?x a :Motorcyclist ; :casualtySeverity ?severity .
  FILTER(?speed >= 50 && ?severity IN ("Fatal","Serious"))
} ORDER BY DESC(?speed) ?c
```
Expected: 62 rows. First: Collision_202560C024981 70 Serious; Collision_202560C158594 70 Fatal; Collision_202560C172985 70 Serious; Collision_202560C182186 70 Serious; Collision_2025610009325 70 Fatal.

Feature coverage: basic pattern Q1,Q9 | FILTER Q1,Q3,Q5,Q10 | OPTIONAL Q6,Q7 | UNION Q5 | aggregation Q2-Q8 | multi-hop Q2,Q3,Q4,Q8,Q9,Q10 | property path Q4,Q7,Q9 | inference Q2-Q8,Q10.

---
## Part 2: Inference examples (Explicit facts -> Rule -> Inferred fact)

### Example 1: SeriousCollision becomes KSICollision (R1, defined class)
Explicit facts: `res:Collision_202560C000676 a :SeriousCollision`.
Rule (schema): `:KSICollision owl:equivalentClass [ owl:unionOf (:FatalCollision :SeriousCollision) ]`.
Inferred: `res:Collision_202560C000676 a :KSICollision` (also `a :Collision` via subClassOf).
```sparql
SELECT ?type WHERE { res:Collision_202560C000676 a ?type . FILTER(STRSTARTS(STR(?type), "https://crash.example.org/ontology#")) }
```
Expected: Collision, SeriousCollision, KSICollision. With "Include inferred" OFF only the first two appear (KSICollision appears only with inference).

### Example 2: pedestrian casualty makes the collision a VRUCollision (R3, R4, R6)
Explicit facts: `res:Collision_2025610052425 :hasVehicle res:Vehicle_2025610052425_1`; `res:Vehicle_2025610052425_1 :hasCasualty res:Casualty_2025610052425_1`; `res:Casualty_2025610052425_1 a :Pedestrian` (severity Serious).
Rules (schema): `:Pedestrian rdfs:subClassOf :VulnerableRoadUser`; `:involvesCasualty owl:propertyChainAxiom (:hasVehicle :hasCasualty)`; `:VRUCollision owl:equivalentClass [ owl:someValuesFrom :VulnerableRoadUser on :involvesCasualty ]`.
Inferred: `Casualty_2025610052425_1 a :VulnerableRoadUser`; `Collision_2025610052425 :involvesCasualty Casualty_2025610052425_1`; `Collision_2025610052425 a :VRUCollision` (and, being Serious, also `:KSICollision`).
```sparql
SELECT ?c ?x WHERE {
  VALUES ?c { res:Collision_2025610052425 }
  ?c a :VRUCollision , :KSICollision ; :involvesCasualty ?x . ?x a :VulnerableRoadUser .
}
```
Expected: 1 row: Collision_2025610052425, Casualty_2025610052425_1.

### Example 3: LSOA partOf chain to the police force (R5, transitive) and HighRiskArea (R7)
Explicit facts: `res:LSOA_W01001662 :partOf res:LA_W06000022`; `res:LA_W06000022 :partOf res:PoliceForce_61` (Gwent); at least 4 KSI collisions with `:occurredIn res:LSOA_W01001662`.
Rules: `:partOf a owl:TransitiveProperty` (R5); R7 INSERT: LSOA with at least 3 KSICollisions becomes `:HighRiskArea`.
Inferred: `res:LSOA_W01001662 :partOf res:PoliceForce_61` (never stored); `res:LSOA_W01001662 a :HighRiskArea` (and so a :LSOA).
```sparql
SELECT ?l ?pf WHERE { res:LSOA_W01001662 a :HighRiskArea ; :partOf ?pf . ?pf a :PoliceForce }
```
Expected: 1 row: LSOA_W01001662, PoliceForce_61. Also LSOA_W01000009 (Isle of Anglesey, 3 KSI, e.g. Collision_202560C025965) is a HighRiskArea under PoliceForce_60.
