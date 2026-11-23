"""Hybrid rule + embedding reasoning (Option D).

Symbolic part  : rules R1-R8 decide VERIFIED/INFERRED facts (KSI, VRU, HighRiskArea ...).
Embedding part : TransE finds PREDICTED facts: (a) collisions similar to a given one, (b) a missing attribute value.
Combination    : similar collisions are searched only inside the pool the rules select (e.g. KSICollision), so the
                 embedding supplies a ranking and the rules supply a guarantee about every candidate. Output is labelled.
"""
from pathlib import Path
import numpy as np
from .kg import KG, PFX, RES
from .embed import TransE

RESULTS = Path(__file__).resolve().parent.parent / "results"


class Hybrid:
    def __init__(self, kg: KG, model_path=None):
        self.kg = kg
        z = np.load(model_path or RESULTS / "embedding_model_seed0.npz")
        m = TransE.__new__(TransE)
        m.ents = [str(e) for e in z["ents"]]
        m.rels = [str(r) for r in z["rels"]]
        m.e2i = {e: i for i, e in enumerate(m.ents)}
        m.r2i = {r: i for i, r in enumerate(m.rels)}
        m.E, m.R = z["E"], z["R"]
        self.m = m

    def pool(self, cls):
        q = PFX + f"SELECT ?c WHERE {{ ?c a :{cls} }}"
        return sorted(str(r[0]).split("/")[-1] for r in self.kg.full.query(q))

    def attrs(self, cid):
        q = PFX + f"""SELECT ?p ?v WHERE {{ res:{cid} ?p ?v . FILTER(isLiteral(?v) && ?p != :collisionIndex) }}"""
        return {str(p).split("#")[-1]: str(v) for p, v in self.kg.stored.query(q)}

    def similar_collisions(self, cid, k=5, rule_class="KSICollision"):
        """Predicted-similar collisions, restricted to the pool the rules certify (default KSICollision)."""
        pool = self.pool(rule_class)
        base = self.attrs(cid)
        out = []
        for other, sim in self.m.similar(cid, pool, k):
            a = self.attrs(other)
            shared = {p: v for p, v in base.items() if a.get(p) == v}
            out.append({"collision": other, "cosine": round(sim, 3), "label": "predicted-similar",
                        "rule_guarantee": f"{rule_class} [{'/'.join(sorted({t for t, _ in self.kg.types_of(RES[other]) if t in ('KSICollision','VRUCollision')}))}]",
                        "shared_attributes": shared})
        return {"query_collision": cid, "query_types": self.kg.types_of(RES[cid]), "neighbours": out}

    def predict_attribute(self, cid, relation, k=3):
        cands = sorted({t for h, r, t in self._tails(relation)})
        return [{"value": v.split("=", 1)[-1], "score": round(s, 3), "label": "predicted (not a stored fact)"}
                for v, s in self.m.predict_tail(cid, relation, cands, k)]

    def _tails(self, relation):
        if not hasattr(self, "_cache"):
            self._cache = {}
        if relation not in self._cache:
            prop = {"collisionSeverity": None}.get(relation, relation)
            self._cache[relation] = [(None, relation, e) for e in self.m.ents if e.startswith(f"{relation}=") or
                                     (relation == "collisionSeverity" and e.startswith("severity="))]
        return self._cache[relation]
