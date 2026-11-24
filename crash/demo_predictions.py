"""Show predictions for HELD-OUT links (same split as train_eval_embeddings, seed 0) next to the true stored value."""
import random
from .kg import load_stored
from .embed import build_triples
from .train_eval_embeddings import TEST_RELS
from .hybrid import Hybrid
from .kg import KG

triples = build_triples(load_stored())
rnd = random.Random(0)
cand = [t for t in triples if t[1] in TEST_RELS and t[0].startswith("Collision_")]
rnd.shuffle(cand)
test = cand[: int(0.1 * len(cand))]
h = Hybrid(KG())
shown = 0
for c, r, t in test:
    if r in ("weatherCondition", "roadClass", "lightCondition", "collisionSeverity") and shown < 8:
        pred = h.predict_attribute(c, r, k=3)
        top = pred[0]["value"]
        print(f"{c:28s} {r:18s} held-out TRUE={t.split('=',1)[-1]:28s} predicted top-3={[p['value'] for p in pred]} "
              f"{'HIT' if t.split('=',1)[-1]==top else 'miss'}  [predicted, not a stored fact]")
        shown += 1
