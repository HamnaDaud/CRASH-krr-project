"""Hold-out link prediction + similar-collision demo. Writes results/embedding_eval.json and results/embedding_model.npz.
Run: python -m crash.train_eval_embeddings [--epochs 300] [--dim 50]
"""
import argparse, json, random
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
from .kg import load_stored
from .embed import build_triples, TransE, evaluate_tail_prediction

TEST_RELS = ["roadClass", "roadType", "junctionType", "lightCondition", "weatherCondition", "surfaceCondition",
             "speedLimit", "collisionSeverity", "occurredIn"]
OUT = Path(__file__).resolve().parent.parent / "results"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=300)
    ap.add_argument("--dim", type=int, default=50)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    triples = build_triples(load_stored())
    print(f"{len(triples)} training-graph triples")
    rnd = random.Random(a.seed)
    cand = [t for t in triples if t[1] in TEST_RELS and t[0].startswith("Collision_")]
    rnd.shuffle(cand)
    test = cand[: int(0.1 * len(cand))]
    test_set = set(test)
    train = [t for t in triples if t not in test_set]
    print(f"held out {len(test)} collision links ({len(test)/len(triples):.1%} of all); training on {len(train)}")
    model = TransE(train, dim=a.dim, seed=a.seed).fit(train, epochs=a.epochs, log=print)
    # tails for each relation: entities seen as tails of that relation in the full graph (type constraint)
    cand_by_rel = defaultdict(set)
    freq = defaultdict(Counter)
    for h, r, t in train:
        cand_by_rel[r].add(t)
        freq[r][t] += 1
    for h, r, t in test:                     # held-out tails must be in the candidate list too
        cand_by_rel[r].add(t)
    cand_by_rel = {r: sorted(v & set(model.ents)) for r, v in cand_by_rel.items()}
    all_true = defaultdict(list)
    for h, r, t in train:
        all_true[(h, r)].append((h, r, t))
    test_in = [t for t in test if t[2] in model.e2i and t[0] in model.e2i]
    res = evaluate_tail_prediction(model, test_in, all_true, cand_by_rel, freq)
    res["config"] = {"dim": a.dim, "epochs": a.epochs, "seed": a.seed, "train_triples": len(train),
                     "test_triples": len(test_in), "entities": len(model.ents), "relations": len(model.rels),
                     "final_loss": model.history[-1]}
    # similarity check: do the 5 nearest collisions of a collision share more attributes than random collisions?
    attrs = defaultdict(set)
    for h, r, t in train:
        if h.startswith("Collision_") and r in ("roadClass", "roadType", "junctionType", "lightCondition",
                                                  "weatherCondition", "surfaceCondition", "speedLimit",
                                                  "collisionSeverity"):
            attrs[h].add((r, t))
    cols = sorted(c for c in attrs)
    jac = lambda x, y: len(attrs[x] & attrs[y]) / len(attrs[x] | attrs[y])
    near, rand_ = [], []
    r2 = random.Random(1)
    for c in cols[:300]:
        near += [jac(c, n) for n, _ in model.similar(c, cols, 5)]
        rand_ += [jac(c, r2.choice(cols)) for _ in range(5)]
    res["similarity_check"] = {"mean_jaccard_top5_neighbours": float(np.mean(near)),
                               "mean_jaccard_random_pairs": float(np.mean(rand_))}
    OUT.mkdir(exist_ok=True)
    (OUT / f"embedding_eval_seed{a.seed}.json").write_text(json.dumps(res, indent=2))
    np.savez_compressed(OUT / f"embedding_model_seed{a.seed}.npz", E=model.E, R=model.R, ents=np.array(model.ents),
                        rels=np.array(model.rels))
    print(json.dumps(res["overall"], indent=1))
    for r, v in res["per_relation"].items():
        print(f"{r:18s} n={v['TransE']['n']:3d} MRR TransE {v['TransE']['MRR']:.3f}  Pop {v['Popularity']['MRR']:.3f}  "
              f"Rand {v['Random']['MRR']:.3f}")
    print(res["similarity_check"])


if __name__ == "__main__":
    main()
