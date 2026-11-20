"""Load the CRASH knowledge graph and materialise the symbolic rules (R1-R8).

stored   = schema + instance data exactly as written by crash_build_abox.py
inferred = triples added by rules; every inferred triple remembers WHICH rule produced it.
"""
from pathlib import Path
from rdflib import Graph, Namespace, RDF

ONT = Namespace("https://crash.example.org/ontology#")
RES = Namespace("https://crash.example.org/resource/")
DATA = Path(__file__).resolve().parent.parent / "data"
PFX = "PREFIX : <https://crash.example.org/ontology#>\nPREFIX res: <https://crash.example.org/resource/>\n" \
      "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>\nPREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"

# id -> (description, SPARQL INSERT). Order matters (R4 before R3, R1 before R7).
RULES = {
 "R4": ("Pedestrian, Cyclist, Motorcyclist are VulnerableRoadUser (and Casualty)",
        "INSERT { ?x a :VulnerableRoadUser , :Casualty } WHERE { { ?x a :Pedestrian } UNION { ?x a :Cyclist } UNION { ?x a :Motorcyclist } }"),
 "R6": ("involvesCasualty = hasVehicle o hasCasualty (property chain)",
        "INSERT { ?c :involvesCasualty ?k } WHERE { ?c :hasVehicle/:hasCasualty ?k }"),
 "R1": ("KSICollision = FatalCollision or SeriousCollision (defined class)",
        "INSERT { ?c a :KSICollision , :Collision } WHERE { { ?c a :FatalCollision } UNION { ?c a :SeriousCollision } }"),
 "R3": ("VRUCollision = collision that involvesCasualty some VulnerableRoadUser",
        "INSERT { ?c a :VRUCollision } WHERE { ?c :involvesCasualty ?k . ?k a :VulnerableRoadUser }"),
 "R5": ("partOf is transitive (LSOA -> local authority -> police force)",
        "INSERT { ?a :partOf ?z } WHERE { ?a :partOf/:partOf ?z }"),
 "R8": ("ChildCasualty = casualty with age band 1-3 (0-15 years)",
        "INSERT { ?x a :ChildCasualty , :Casualty } WHERE { ?x :casualtyAgeBand ?b . FILTER(?b >= 1 && ?b <= 3) }"),
 "R7": ("HighRiskArea = LSOA with at least 3 distinct KSI collisions",
        "INSERT { ?l a :HighRiskArea , :LSOA } WHERE { { SELECT ?l WHERE { ?c a :KSICollision ; :occurredIn ?l } "
        "GROUP BY ?l HAVING (COUNT(DISTINCT ?c) >= 3) } }"),
}


def load_stored() -> Graph:
    g = Graph()
    g.parse(DATA / "crash_schema.ttl", format="turtle")
    g.parse(DATA / "crash_data.ttl", format="turtle")
    return g


def materialise(stored: Graph):
    """Return (full_graph, {triple: rule_id}). The stored graph is not modified."""
    full = Graph()
    for t in stored:
        full.add(t)
    for prefix, ns in stored.namespaces():
        full.bind(prefix, ns)
    origin = {}
    for rid, (_, upd) in RULES.items():
        before = set(full)
        full.update(PFX + upd)
        for t in set(full) - before:
            origin[t] = rid
    return full, origin


class KG:
    def __init__(self):
        self.stored = load_stored()
        self.full, self.origin = materialise(self.stored)

    def stats(self):
        return {"stored_triples": len(self.stored), "inferred_triples": len(self.origin),
                "inferred_by_rule": {r: sum(1 for v in self.origin.values() if v == r) for r in RULES}}

    def types_of(self, iri):
        """Return [(class, 'stored'|'inferred:R?')] for one resource."""
        out = []
        for t in self.full.objects(iri, RDF.type):
            if (iri, RDF.type, t) in self.stored:
                out.append((t.split("#")[-1], "stored"))
            else:
                out.append((t.split("#")[-1], "inferred:" + self.origin.get((iri, RDF.type, t), "?")))
        return sorted(out)

    def categorical_values(self):
        """Distinct values of the text properties, to show the planner the exact labels."""
        q = PFX + """SELECT ?p ?v (COUNT(?c) AS ?n) WHERE { VALUES ?p { :roadClass :roadType :junctionType :lightCondition
            :weatherCondition :surfaceCondition } ?c ?p ?v } GROUP BY ?p ?v"""
        vals = {}
        for p, v, n in self.stored.query(q):
            vals.setdefault(p.split("#")[-1], []).append((str(v), int(n)))
        for k in vals:
            vals[k].sort(key=lambda x: -x[1])
        return vals
