"""TransE knowledge-graph embeddings in plain numpy (Bordes et al., 2013).

Score of a triple (h, r, t) = -|| h + r - t ||_2 ; a true triple should have h + r close to t.
Trained with a margin ranking loss against corrupted triples (head or tail replaced at random).
Only STORED triples are used (never inferred ones), so nothing derived by a rule leaks into training.
"""
import numpy as np
from rdflib import Literal, RDF, URIRef
from .kg import ONT

# categorical / numeric data properties become (collision, property, value-node) triples
ATTR_PROPS = ["roadClass", "roadType", "junctionType", "lightCondition", "weatherCondition", "surfaceCondition",
              "vehicleType", "vehicleManoeuvre", "casualtySeverity", "casualtyClass"]
OBJ_PROPS = ["hasVehicle", "hasCasualty", "occurredIn", "partOf"]


def build_triples(stored):
    """Return list of (head, relation, tail) strings from the stored graph."""
    T = []
    for p in OBJ_PROPS:
        for s, o in stored.subject_objects(ONT[p]):
            T.append((s.split("/")[-1], p, o.split("/")[-1]))
    for p in ATTR_PROPS:
        for s, o in stored.subject_objects(ONT[p]):
            T.append((s.split("/")[-1], p, f"{p}={o}"))
    for s, o in stored.subject_objects(ONT.speedLimit):
        T.append((s.split("/")[-1], "speedLimit", f"speedLimit={o}"))
    for s, o in stored.subject_objects(ONT.collisionDate):
        T.append((s.split("/")[-1], "collisionMonth", f"month={str(o)[:7]}"))
    for s, o in stored.subject_objects(ONT.driverAge):
        T.append((s.split("/")[-1], "driverAgeBand", f"driverAge={min(int(o) // 10, 8)}0s"))
    for s, o in stored.subject_objects(ONT.casualtyAgeBand):
        T.append((s.split("/")[-1], "casualtyAgeBand", f"ageBand={o}"))
    # severity class of a collision (Fatal / Serious / Slight) comes from rdf:type, an explicit fact
    for s, o in stored.subject_objects(RDF.type):
        if str(s).startswith("https://crash.example.org/resource/Collision_"):
            cls = {"FatalCollision": "Fatal", "SeriousCollision": "Serious", "Collision": "Slight"}[o.split("#")[-1]]
            T.append((s.split("/")[-1], "collisionSeverity", f"severity={cls}"))
        elif str(s).startswith("https://crash.example.org/resource/Casualty_"):
            T.append((s.split("/")[-1], "roadUserType", f"roadUser={o.split('#')[-1]}"))
    return sorted(set(T))


class TransE:
    def __init__(self, triples, dim=50, seed=0):
        self.rng = np.random.default_rng(seed)
        self.ents = sorted({x for h, _, t in triples for x in (h, t)})
        self.rels = sorted({r for _, r, _ in triples})
        self.e2i = {e: i for i, e in enumerate(self.ents)}
        self.r2i = {r: i for i, r in enumerate(self.rels)}
        self.dim = dim
        b = 6 / np.sqrt(dim)
        self.E = self.rng.uniform(-b, b, (len(self.ents), dim))
        self.R = self.rng.uniform(-b, b, (len(self.rels), dim))
        self.R /= np.linalg.norm(self.R, axis=1, keepdims=True)
        self.history = []

    def idx(self, triples):
        return np.array([(self.e2i[h], self.r2i[r], self.e2i[t]) for h, r, t in triples if h in self.e2i
                         and t in self.e2i and r in self.r2i], dtype=int)

    def fit(self, triples, epochs=200, lr=0.05, margin=1.0, batch=1024, log=None):
        X = self.idx(triples)
        n = len(self.ents)
        for ep in range(epochs):
            self.E /= np.maximum(np.linalg.norm(self.E, axis=1, keepdims=True), 1.0)  # keep ||e|| <= 1
            self.rng.shuffle(X)
            total = 0.0
            for i in range(0, len(X), batch):
                b = X[i:i + batch]
                neg = b.copy()
                corrupt_tail = self.rng.random(len(b)) < 0.5
                rnd = self.rng.integers(0, n, len(b))
                neg[corrupt_tail, 2] = rnd[corrupt_tail]
                neg[~corrupt_tail, 0] = rnd[~corrupt_tail]
                dp = self.E[b[:, 0]] + self.R[b[:, 1]] - self.E[b[:, 2]]
                dn = self.E[neg[:, 0]] + self.R[neg[:, 1]] - self.E[neg[:, 2]]
                lp, ln = np.linalg.norm(dp, axis=1), np.linalg.norm(dn, axis=1)
                loss = margin + lp - ln
                act = loss > 0
                total += loss[act].sum()
                if not act.any():
                    continue
                gp = dp[act] / np.maximum(lp[act, None], 1e-9)
                gn = dn[act] / np.maximum(ln[act, None], 1e-9)
                bp, bn = b[act], neg[act]
                np.add.at(self.E, bp[:, 0], -lr * gp)
                np.add.at(self.E, bp[:, 2], lr * gp)
                np.add.at(self.R, bp[:, 1], -lr * gp)
                np.add.at(self.E, bn[:, 0], lr * gn)
                np.add.at(self.E, bn[:, 2], -lr * gn)
                np.add.at(self.R, bn[:, 1], lr * gn)
            self.history.append(total / len(X))
            if log and (ep % 25 == 0 or ep == epochs - 1):
                log(f"epoch {ep:3d}  mean margin loss {self.history[-1]:.4f}")
        return self

    # ---- scoring / prediction
    def score_tails(self, h, r):
        v = self.E[self.e2i[h]] + self.R[self.r2i[r]]
        return -np.linalg.norm(self.E - v, axis=1)

    def predict_tail(self, h, r, candidates, k=3):
        s = self.score_tails(h, r)
        cand = [(c, float(s[self.e2i[c]])) for c in candidates if c in self.e2i]
        return sorted(cand, key=lambda x: -x[1])[:k]

    def similar(self, entity, pool, k=5):
        """Cosine-nearest entities among `pool`."""
        v = self.E[self.e2i[entity]]
        P = np.array([self.E[self.e2i[p]] for p in pool])
        sims = P @ v / (np.linalg.norm(P, axis=1) * np.linalg.norm(v) + 1e-9)
        order = np.argsort(-sims)
        return [(pool[i], float(sims[i])) for i in order if pool[i] != entity][:k]


def evaluate_tail_prediction(model, test, all_true, cand_by_rel, freq_by_rel, seed=0):
    """Filtered, type-constrained ranking. Returns metrics for TransE, popularity baseline and random baseline."""
    rng = np.random.default_rng(seed)
    out = {}
    rows = {"TransE": [], "Popularity": [], "Random": []}
    per_rel = {}
    for h, r, t in test:
        cands = cand_by_rel[r]
        known = {tt for hh, rr, tt in all_true.get((h, r), [])} - {t}
        cands = [c for c in cands if c not in known]
        s = model.score_tails(h, r)
        sc = {c: s[model.e2i[c]] for c in cands}
        rank_t = 1 + sum(1 for c in cands if c != t and sc[c] > sc[t])
        pop = freq_by_rel[r]
        rank_p = 1 + sum(1 for c in cands if c != t and pop.get(c, 0) > pop.get(t, 0))
        rank_r = int(rng.integers(1, len(cands) + 1))
        for name, rk in (("TransE", rank_t), ("Popularity", rank_p), ("Random", rank_r)):
            rows[name].append(rk)
            per_rel.setdefault((r, name), []).append(rk)

    def m(ranks):
        a = np.array(ranks)
        return {"n": len(a), "MRR": float(np.mean(1 / a)), "Hits@1": float(np.mean(a <= 1)),
                "Hits@3": float(np.mean(a <= 3)), "Hits@10": float(np.mean(a <= 10))}
    out["overall"] = {k: m(v) for k, v in rows.items()}
    out["per_relation"] = {r: {n: m(per_rel[(r, n)]) for n in rows} for r in sorted({r for r, _ in per_rel})}
    return out
