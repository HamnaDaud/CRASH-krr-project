"""CRASH chat application (CLI and a tiny web page).

  python -m crash.app                 # interactive CLI
  python -m crash.app --web 8000      # web UI on http://127.0.0.1:8000
  python -m crash.app --backend manual --ask "..."   # no API key: prompts go to eval/manual/pending
Commands in the CLI:  /similar <CollisionID>   embedding-based similar collisions (predicted)
                      /rules                   list the symbolic rules and inferred-triple counts
"""
import argparse, json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
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
    s.append("--- Answer (AI-written) ---\n" + res["answer"])
    if res.get("grounding") and (res["grounding"]["unsupported_ids"] or res["grounding"]["unsupported_numbers"]):
        s.append("WARNING unsupported by context: " + json.dumps(res["grounding"]))
    s.append(LEGEND)
    return "\n".join(s)


def serve(port, retr, llm):
    from .hybrid import Hybrid
    hy = Hybrid(retr.kg)
    page = """<!doctype html><meta charset=utf-8><title>CRASH</title><body style="font:15px system-ui;max-width:900px;margin:2em auto">
<h2>CRASH road-safety advisor</h2><form method=get><input name=q size=80 placeholder="Ask about collisions...">
<button>Ask</button></form><pre style="white-space:pre-wrap">%s</pre><p style=color:#666>%s</p>"""

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            from urllib.parse import urlparse, parse_qs
            q = parse_qs(urlparse(self.path).query).get("q", [""])[0]
            out = ""
            if q:
                try:
                    out = render(ask_grounded(retr, llm, q))
                except PendingResponse as e:
                    out = f"LLM response pending (manual backend): {e}"
            body = (page % (out.replace("<", "&lt;"), LEGEND)).encode()
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write(body)
    print(f"CRASH web UI on http://127.0.0.1:{port}")
    HTTPServer(("127.0.0.1", port), H).serve_forever()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["anthropic", "manual"])
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
