"""Compute the EXPECTED answers from hand-written gold SPARQL (never shown to the system). Writes eval/gold_answers.json."""
import json
from pathlib import Path
from crash.kg import KG, PFX

HERE = Path(__file__).parent
kg = KG()
out = {}
for cq in json.loads((HERE / "cqs.json").read_text()):
    rows = [[str(x) for x in r] for r in kg.full.query(PFX + cq["gold"])]
    d = {"cols": [str(v) for v in kg.full.query(PFX + cq["gold"]).vars], "rows": rows, "n_rows": len(rows)}
    if "total" in cq:
        d["total"] = str(next(iter(kg.full.query(PFX + cq["total"])))[0])
    out[cq["id"]] = d
(HERE / "gold_answers.json").write_text(json.dumps(out, indent=1))
for k, v in out.items():
    print(k, v["n_rows"], "rows;", v["rows"][:5], v.get("total", ""))
