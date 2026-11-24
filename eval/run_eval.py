"""10-question LLM-only (A) vs KG-grounded (B) evaluation + 3 insufficient-evidence probes.

  python -m eval.run_eval --backend openai         # needs LLM_API_KEY (free Groq key)
  python -m eval.run_eval --backend manual         # file-based replay, see crash/llm.py
Writes results/eval_results.json (answers, SPARQL, evidence, auto-check) and prints the table.
Run it repeatedly with the manual backend: each pass writes the next batch of pending prompts.
"""
import argparse, json, re
from pathlib import Path
from crash.kg import KG
from crash.retrieval import Retriever
from crash.answer import ask_grounded, ask_llm_only
from crash.llm import get_backend, PendingResponse

HERE = Path(__file__).parent
OUT = HERE.parent / "results" / "eval_results.json"


def norm(s):
    s = re.sub(r"[\u2010-\u2015\u2212]", "-", s.lower())          # unify unicode dashes
    return re.sub(r"[\s,*|]+", "", s)                             # ignore spaces, commas, markdown bold/table bars


def tokens(cq, gold):
    rows, spec = gold["rows"], cq["keys"]
    t = []
    if "all" in spec:
        t += [c for r in rows for c in r]
    if "total" in spec:
        t.append(gold["total"])
    if "count" in spec:
        t.append(str(gold["n_rows"]))
    for s in spec:
        m = re.match(r"top(\d+)", s)
        if m:
            t += [c for r in rows[: int(m.group(1))] for c in r]
    return list(dict.fromkeys(t))


def auto_check(answer, toks):
    a = norm(answer or "")
    found = [t for t in toks if norm(t) in a]
    return {"tokens": toks, "found": found, "missing": [t for t in toks if t not in found], "all_found": len(found) == len(toks)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["openai", "manual"])
    ap.add_argument("--limit", type=int, help="only run the first N items (quick live check)")
    ap.add_argument("--out", help="output JSON path (default results/eval_results.json)")
    a = ap.parse_args()
    llm = get_backend(a.backend)
    retr = Retriever(KG())
    gold = json.loads((HERE / "gold_answers.json").read_text())
    results, pending = [], 0
    items = [(c, True) for c in json.loads((HERE / "cqs.json").read_text())] + \
            [(c, False) for c in json.loads((HERE / "insufficient_probes.json").read_text())]
    items = items[:a.limit] if a.limit else items
    import time
    for c, is_cq in items:
        t0 = time.time()
        print(f"[{c['id']}] start", flush=True)
        rec = {"id": c["id"], "question": c["q"]}
        try:
            rec["A_llm_only"] = ask_llm_only(llm, c["q"])
        except PendingResponse:
            rec["A_llm_only"] = None; pending += 1
        try:
            g = ask_grounded(retr, llm, c["q"])
            rec["B_status"] = g["status"]
            rec["B_answer"] = g["answer"]
            rec["B_sparql"] = g["retrieval"]["sparql"]
            rec["B_planner_reason"] = g["retrieval"]["reason"]
            rec["B_n_rows"] = len(g["retrieval"]["rows"])
            rec["B_row_tags"] = sorted({r["tag"] for r in g["retrieval"]["rows"]})
            rec["B_rows_sample"] = g["retrieval"]["rows"][:10]
            rec["B_grounding"] = g.get("grounding")
            rec["B_context"] = g.get("context")
        except PendingResponse:
            rec["B_answer"] = None; pending += 1
        if is_cq:
            toks = tokens(c, gold[c["id"]])
            rec["expected"] = gold[c["id"]]
            rec["A_auto"] = auto_check(rec["A_llm_only"], toks)
            rec["B_auto"] = auto_check(rec.get("B_answer"), toks)
        results.append(rec)
        print(f"[{c['id']}] done in {time.time() - t0:.0f}s", flush=True)
    out = Path(a.out) if a.out else OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=1))
    print(f"backend={llm.name} pending prompts={pending}")
    for r in results:
        if "A_auto" in r:
            print(f"{r['id']}  A auto-correct={r['A_auto']['all_found']}  B auto-correct={r['B_auto']['all_found']}  "
                  f"B rows={r.get('B_n_rows')} status={r.get('B_status')}")
        else:
            print(f"{r['id']}  probe: B status={r.get('B_status')}")


if __name__ == "__main__":
    main()
