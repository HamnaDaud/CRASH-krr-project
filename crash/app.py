"""CRASH chat application (CLI and a tiny web page).

  python -m crash.app                 # interactive CLI
  python -m crash.app --web 8000      # web UI on http://127.0.0.1:8000
  python -m crash.app --ask "..."     # one question, answer printed
Commands in the CLI:  /similar <CollisionID>   embedding-based similar collisions (predicted)
                      /rules                   list the symbolic rules and inferred-triple counts
"""
import argparse, json, sys
from .kg import KG, RULES
from .retrieval import Retriever
from .answer import ask_grounded
from .llm import get_backend, PendingResponse

LEGEND = "Labels: [stored] fact in the graph | [inferred] derived by rule R1-R8 | [predicted] TransE prediction | AI-written = the answer text"


def render(res):
    r = res["retrieval"]
    s = [f"\nQ: {res['question']}", f"Status: {res['status']}"]
    if r["sparql"]:
        s.append("--- SPARQL (retrieval) ---\n" + r["sparql"])
    if r["rows"]:
        s.append(f"--- Evidence rows ({len(r['rows'])}; first 8) ---")
        for x in r["rows"][:8]:
            s.append(f"  [{x['tag']}] " + " | ".join(f"{k}={v[:90]}" for k, v in x["row"].items()))
    if r.get("extra"):
        s.append("--- Overall figure (second query) ---\n" + r["extra"]["sparql"])
        for x in r["extra"]["rows"][:3]:
            s.append(f"  [{x['tag']}] " + " | ".join(f"{k}={v[:90]}" for k, v in x["row"].items()))
    s.append("--- Answer (AI-written) ---\n" + res["answer"])
    if res.get("grounding") and (res["grounding"]["unsupported_ids"] or res["grounding"]["unsupported_numbers"]):
        s.append("WARNING unsupported by context: " + json.dumps(res["grounding"]))
    s.append(LEGEND)
    return "\n".join(s)


def serve(port, retr, llm):
    from .webui import serve as _serve
    _serve(port, retr, llm)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["openai", "manual"])
    ap.add_argument("--web", type=int)
    ap.add_argument("--ask")
    a = ap.parse_args()
    print("Loading graph and applying rules R1-R8 ...")
    kg = KG()
    print(kg.stats())
    retr, llm = Retriever(kg), get_backend(a.backend)
    if a.web:
        return serve(a.web, retr, llm)
    from .hybrid import Hybrid
    hy = Hybrid(kg)

    def handle(line):
        if line.startswith("/similar"):
            cid = line.split()[1].replace("res:", "")
            print(json.dumps(hy.similar_collisions(cid), indent=1)); return
        if line.startswith("/rules"):
            for k, v in RULES.items():
                print(k, v[0])
            return
        try:
            print(render(ask_grounded(retr, llm, line)))
        except PendingResponse as e:
            print(f"(manual backend) LLM response pending: {e}; fill eval/manual/responses/{e}.txt and ask again")
        except Exception as e:      # API errors (rate limit, bad key, network): show a short message instead of a traceback
            print(f"LLM API error: {type(e).__name__}: {str(e)[:300]}\n(free tier: wait a minute and ask again; check LLM_API_KEY)")
    if a.ask:
        return handle(a.ask)
    while True:
        try:
            line = input("\nask> ").strip()
        except EOFError:
            break
        if line in ("", "quit", "exit"):
            break
        handle(line)


if __name__ == "__main__":
    main()
