"""KG retrieval: question -> (LLM) SPARQL plan -> execute on the rule-materialised graph -> tagged evidence.

Every result row is tagged:
  stored    - the same row is returned when the query is run on the stored triples alone
  inferred  - the row only exists because a rule (R1-R8) derived facts that the query used
"""
import json, os, re, multiprocessing as mp
from rdflib.plugins.sparql import prepareQuery
from .kg import KG, PFX, RULES

MAX_ROWS_RETURNED = 500

PLAN_SYSTEM = """You translate a road-safety question into ONE SPARQL 1.1 SELECT query over the CRASH knowledge graph.
Reply with JSON only: {"answerable": true|false, "reason": "...", "sparql": "...", "sparql_total": "... (optional, see rules)"}.
Set answerable=false (and give the reason) when the graph cannot contain the answer, e.g. the question is about a year other than 2025,
a place outside North Wales (police force 60) and Gwent (61), causes/blame/alcohol/driver behaviour, or anything not in the schema below.
Do not invent data. Do not answer the question yourself.

PREFIXES (already declared, do not repeat them):
PREFIX : <https://crash.example.org/ontology#>   PREFIX res: <https://crash.example.org/resource/>

GRAPH CONTENT: STATS19 2025 collisions of North Wales and Gwent police, 1115 collisions, 1962 vehicles, 1491 casualties.
CLASSES: Collision, FatalCollision, SeriousCollision, KSICollision (derived: fatal or serious), VRUCollision (derived: has a vulnerable
road user casualty), Vehicle, Casualty, VulnerableRoadUser (derived), Pedestrian, Cyclist, Motorcyclist (stored casualty types),
ChildCasualty (derived, age 0-15), LSOA, LocalAuthority, PoliceForce, HighRiskArea (derived: LSOA with >=3 KSI collisions).
Slight collisions are plain :Collision with no subclass. Derived classes are ALREADY materialised: just query them.
OBJECT PROPERTIES: :hasVehicle (Collision->Vehicle), :hasCasualty (Vehicle->Casualty), :involvesCasualty (Collision->Casualty, shortcut),
:occurredIn (Collision->LSOA), :partOf (LSOA->LocalAuthority->PoliceForce, transitive, so LSOA :partOf PoliceForce also holds).
DATA PROPERTIES (all text unless stated): collisions: :collisionIndex, :collisionDate (xsd:date), :speedLimit (integer), :roadClass,
:roadType, :junctionType, :lightCondition, :weatherCondition, :surfaceCondition; vehicles: :vehicleType, :vehicleManoeuvre, :driverAge (int);
casualties: :casualtySeverity (Fatal|Serious|Slight), :casualtyClass, :casualtyAgeBand (int, 1-3 = child); areas: :areaCode, :areaName
(LocalAuthority and PoliceForce have :areaName; an LSOA has :areaCode only).
Resource IRIs look like res:Collision_202560C002220, res:Casualty_202560C002220_1; use STRAFTER(STR(?c),"resource/") to show IDs.
EXACT LABELS (use these strings in FILTERs):
{labels}
RULES FOR THE QUERY:
- SELECT only, no UPDATE. Use COUNT(DISTINCT ...) for counts.
- ALWAYS include an evidence column named ?evidence = GROUP_CONCAT(DISTINCT STRAFTER(STR(?c),"resource/");separator=",") over the collisions
  behind each row (for list queries just return the collision ID as ?collision). Casualty-level questions should also return the casualty ID.
- Return all columns needed to answer. Add a sensible LIMIT (<=500).
- Aggregates (COUNT, GROUP_CONCAT, SUM ...) may appear ONLY as (AGG(...) AS ?alias) in the SELECT clause of a query or sub-select. NEVER put an
  aggregate inside BIND, FILTER or WHERE, never nest aggregates, and never GROUP BY an aggregate alias such as ?evidence or ?count.
  Compute row-level values (e.g. BIND(STRAFTER(STR(?c),"resource/") AS ?cid)) first, then aggregate them in the SELECT clause:
  SELECT ?g (COUNT(DISTINCT ?c) AS ?n) (GROUP_CONCAT(DISTINCT ?cid; separator=",") AS ?evidence) WHERE { ... BIND(STRAFTER(STR(?c),"resource/") AS ?cid) } GROUP BY ?g
- When the question asks for an overall count AND a breakdown (or a ranking), do NOT combine them: put the breakdown in "sparql" and a second,
  separate, simple query that returns only the overall figure in "sparql_total", e.g.
  SELECT (COUNT(DISTINCT ?c) AS ?total) WHERE { ?c a :X }. Never use sub-selects. Leave "sparql_total" out when no overall figure is asked for.
- For rankings or "most" questions alias the count (e.g. AS ?n) and ORDER BY DESC(?n); for "high-risk areas" query the derived class :HighRiskArea.
- Keep queries simple: use the derived classes (:KSICollision, :VRUCollision, :HighRiskArea) directly instead of re-counting by hand, and do not
  add filters the question does not ask for (the whole graph is already the 2025 North Wales + Gwent data).
- "Local authority" of a collision: ?c :occurredIn ?lsoa . ?lsoa :partOf ?la . ?la a :LocalAuthority ; :areaName ?name (class check needed,
  because partOf is transitive and also reaches the police force). Police force of an LSOA: ?lsoa :partOf ?pf . ?pf a :PoliceForce.
- "A or B conditions" means a FILTER over BOTH exact labels (e.g. ?s IN ("x","y")); map plain words to the exact labels listed above
  (wet -> "Wet or damp", icy -> "Frost or ice"). "How many X were there" with a breakdown by group: GROUP BY the group name, not the force.
- IMPORTANT: an LSOA has NO :areaName (only :areaCode); only LocalAuthority and PoliceForce have :areaName. A triple pattern that asks for a property
  the class does not have makes the whole result EMPTY. Put non-essential properties in OPTIONAL { ... }.
- Always SELECT the human-readable name (?areaName for local authorities and police forces, :areaCode for an LSOA), never only the IRI.
- Each row must be one answer item (one area, one vehicle type ...); do not return only a grand total when items are asked for.
"""

ANSWER_SYSTEM = """You are CRASH, a road-safety advisor. Answer the user's question using ONLY the retrieved knowledge-graph context below.
Rules:
1. Never use outside knowledge, memory, or general statistics. Every number and name in your answer must appear in the context.
2. Each statement must carry the tag of the context rows it comes from: [stored], [inferred] or [predicted], and cite collision IDs
   (e.g. Collision_202560C002220) as evidence. For counts, cite a few example IDs from the evidence column and say how many rows exist in total.
   If the context has a "Second query (overall figure)", state that figure (e.g. the overall total) in the answer.
3. [predicted] items come from the embedding model: say clearly they are predictions, not facts.
4. If the context is empty or does not contain what is needed, reply exactly: INSUFFICIENT_EVIDENCE: <one sentence why>. Do not guess.
5. Be concise (under 180 words). Your text is AI-written; the evidence table is shown to the user separately."""

LLM_ONLY_SYSTEM = """You are a road-safety assistant. Answer the user's question as well as you can. The question is about collisions in the
STATS19 2025 data of North Wales and Gwent police (Great Britain). Be concise (under 180 words)."""


def labels_block(kg):
    lines = []
    for p, vals in kg.categorical_values().items():
        lines.append(f"  :{p}: " + "; ".join(f'"{v}"' for v, _ in vals))
    return "\n".join(lines)


def extract_json(text):
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0))


class Retriever:
    def __init__(self, kg: KG = None):
        self.kg = kg or KG()
        self.plan_system = PLAN_SYSTEM.replace("{labels}", labels_block(self.kg))
        # IRI -> readable name, so rows never show a bare resource IRI such as .../LA_W06000004 to the answering model
        self.names = {str(r[0]).split("resource/")[-1]: str(r[1]) for r in self.kg.full.query(PFX + "SELECT ?x ?n WHERE { ?x :areaName ?n }")}

    def plan(self, llm, question, error=None, prev=None):
        user = f"Question: {question}"
        if error:
            user += (f"\n\nYour previous query was:\n{prev}\n\nIt failed: {error}\nThe question IS answerable from the graph. "
                     "Write a simpler, corrected query (aggregates only in the SELECT clause, no BIND/GROUP BY of aggregates, "
                     "exact labels from the list) and return a corrected JSON object.")
        return extract_json(llm.complete(self.plan_system, user, tag="plan" if not error else "plan-retry"))

    @staticmethod
    def lint(sparql):
        """Cheap checks for the mistakes the LLM makes most often; the message goes back to the planner."""
        if re.search(r"BIND\s*\(\s*(COUNT|SUM|AVG|MIN|MAX|GROUP_CONCAT|SAMPLE)\s*\(", sparql, re.I):
            raise ValueError("an aggregate function is used inside BIND; aggregates are only allowed as (AGG(...) AS ?x) in a SELECT clause")
        m = re.search(r"GROUP\s+BY(.*?)(?=\bORDER\s+BY\b|\bHAVING\b|\bLIMIT\b|\bOFFSET\b|\}|$)", sparql, re.I | re.S)
        for alias in re.findall(r"\(\s*(?:COUNT|SUM|AVG|MIN|MAX|GROUP_CONCAT|SAMPLE)\s*\(.*?\)\s+AS\s+\?(\w+)\s*\)", sparql, re.I | re.S):
            if m and re.search(r"\?" + alias + r"\b", m.group(1)):
                raise ValueError(f"GROUP BY contains the aggregate alias ?{alias}; group only by non-aggregate variables")

    @staticmethod
    def check_select_only(sparql):
        if re.search(r"\b(INSERT|DELETE|LOAD|CLEAR|DROP|CREATE|COPY|MOVE|ADD)\b", sparql, re.I) and \
                not re.match(r"\s*(PREFIX[^\n]*\n\s*)*SELECT", sparql, re.I):
            raise ValueError("only SELECT queries are allowed")
        prepareQuery(PFX + sparql)       # syntax check

    def execute(self, sparql):
        """Run the query in a forked child with a time limit: an LLM-written query with nested aggregates can take hours in rdflib."""
        self.check_select_only(sparql)
        self.lint(sparql)
        limit = float(os.environ.get("CRASH_QUERY_TIMEOUT", "40"))
        if limit <= 0 or not hasattr(os, "fork"):
            return self._execute(sparql)
        ctx = mp.get_context("fork")
        rx, tx = ctx.Pipe(duplex=False)

        def work():
            try:
                tx.send(("ok", self._execute(sparql)))
            except Exception as e:
                tx.send(("err", f"{type(e).__name__}: {e}"))
        p = ctx.Process(target=work, daemon=True)
        p.start()
        if rx.poll(limit):
            kind, val = rx.recv()
            p.join()
            if kind == "ok":
                return val
            raise ValueError(val)
        p.terminate(); p.join()
        raise TimeoutError(f"the query ran longer than {limit:.0f} s; rewrite it much simpler (no nested aggregate sub-selects, "
                           "no extra joins, use the derived classes directly)")

    def _execute(self, sparql):
        full = self.kg.full.query(PFX + sparql)
        cols = [str(v) for v in full.vars]
        def cell(x):
            x = "" if x is None else str(x)
            if x.startswith("https://crash.example.org/resource/"):
                loc = x.split("resource/")[-1]
                x = f"{self.names[loc]} ({loc})" if loc in self.names else loc
            return ",".join(sorted(x.split(","))) if re.fullmatch(r"(Collision|Casualty)?_?[0-9A-Z_]+(,[0-9A-Z_]+)+", x) else x
        rows_full = [tuple(cell(x) for x in r) for r in full]
        if not re.search(r"ORDER\s+BY", sparql, re.I):      # deterministic order when the query gives none
            rows_full.sort()
        rows_full = rows_full[:MAX_ROWS_RETURNED]
        # stored-only run without LIMIT/OFFSET, so a row is 'stored' iff it also exists without any rule
        stored = self.kg.stored.query(PFX + re.sub(r"\s*\b(LIMIT|OFFSET)\s+\d+", "", sparql, flags=re.I))
        rows_stored = {tuple(cell(x) for x in r) for r in stored}
        rows = [{"row": dict(zip(cols, r)), "tag": "stored" if r in rows_stored else "inferred"} for r in rows_full]
        return cols, rows

    def retrieve(self, llm, question):
        """Return dict: answerable, reason, sparql, columns, rows (tagged), error, attempts.
        Up to CRASH_PLAN_ATTEMPTS (default 4) planner tries: a syntax error, a timeout, an invalid query or an EMPTY result
        is fed back to the planner together with its previous query. The first attempt may declare the question not answerable."""
        out = {"question": question, "answerable": False, "reason": "", "sparql": "", "columns": [], "rows": [], "error": None, "attempts": 0}
        n_try = int(os.environ.get("CRASH_PLAN_ATTEMPTS", "4"))
        err, prev = None, None
        for attempt in range(n_try):
            out["attempts"] = attempt + 1
            try:
                plan = self.plan(llm, question, err, prev)
            except (ValueError, KeyError, AttributeError) as e:    # unparsable JSON from the model (json.JSONDecodeError is a ValueError)
                err, prev = f"your reply was not valid JSON ({type(e).__name__})", prev or ""
                out["error"] = err
                continue
            if not plan.get("answerable", False):
                if attempt == 0:                          # genuine refusal (unknown year, cause of collision ...)
                    out["reason"] = plan.get("reason", "planner judged the question not answerable from the graph")
                    return out
                err = "you declared the question not answerable, but it is answerable; write the query"
                continue
            out["sparql"], out["reason"] = plan.get("sparql", ""), plan.get("reason", "")
            try:
                out["columns"], out["rows"] = self.execute(plan["sparql"])
                out["answerable"], out["error"] = True, None
                if out["rows"]:
                    if plan.get("sparql_total"):          # optional second query: the overall figure
                        try:
                            c2, r2 = self.execute(plan["sparql_total"])
                            out["extra"] = {"sparql": plan["sparql_total"], "columns": c2, "rows": r2}
                        except Exception as e:
                            out["extra_error"] = f"{type(e).__name__}: {str(e)[:200]}"
                    return out
                err, prev = ("the query ran but returned 0 rows; a required triple pattern probably does not exist in the schema "
                             "(e.g. :areaName on an LSOA, a wrong label or class); check every pattern against the schema, move non-essential "
                             "ones into OPTIONAL and remove unnecessary filters/joins"), plan["sparql"]
                out["error"] = "empty result"
            except Exception as e:                        # bad SPARQL / timeout: feed the error back
                err, prev = f"{type(e).__name__}: {str(e)[:300]}", plan["sparql"]
                out["error"], out["answerable"] = err, False
        return out


def _short(cell, keep=5):
    ids = cell.split(",")
    return cell if len(ids) <= keep + 2 else ",".join(ids[:keep]) + f",... (+{len(ids) - keep} more, {len(ids)} in total)"


def context_text(ret, max_rows=30):
    """Serialise retrieved rows for the answer prompt (with tags and total count)."""
    rows = ret["rows"]
    lines = [f"SPARQL used:\n{ret['sparql']}", f"Total rows returned: {len(rows)} (showing first {min(len(rows), max_rows)})",
             "Columns: " + ", ".join(ret["columns"]) + ", tag"]
    for r in rows[:max_rows]:
        lines.append(" | ".join(_short(r["row"][c]) for c in ret["columns"]) + f" | [{r['tag']}]")
    if ret.get("extra"):
        ex = ret["extra"]
        lines.append(f"\nSecond query (overall figure):\n{ex['sparql']}\nColumns: " + ", ".join(ex["columns"]) + ", tag")
        for r in ex["rows"][:5]:
            lines.append(" | ".join(_short(r["row"][c]) for c in ex["columns"]) + f" | [{r['tag']}]")
    tags = {r["tag"] for r in rows}
    if ret.get("extra"):
        tags |= {r["tag"] for r in ret["extra"]["rows"]}
    if "inferred" in tags:
        lines.append("Rules that can make rows [inferred]: " + "; ".join(f"{k}: {v[0]}" for k, v in RULES.items()))
    return "\n".join(lines)
