"""KG retrieval: question -> (LLM) SPARQL plan -> execute on the rule-materialised graph -> tagged evidence.

Every result row is tagged:
  stored    - the same row is returned when the query is run on the stored triples alone
  inferred  - the row only exists because a rule (R1-R8) derived facts that the query used
"""
import json, re
from rdflib.plugins.sparql import prepareQuery
from .kg import KG, PFX, RULES

MAX_ROWS_RETURNED = 500

PLAN_SYSTEM = """You translate a road-safety question into ONE SPARQL 1.1 SELECT query over the CRASH knowledge graph.
Reply with JSON only: {"answerable": true|false, "reason": "...", "sparql": "..."}.
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
"""

ANSWER_SYSTEM = """You are CRASH, a road-safety advisor. Answer the user's question using ONLY the retrieved knowledge-graph context below.
Rules:
1. Never use outside knowledge, memory, or general statistics. Every number and name in your answer must appear in the context.
2. Each statement must carry the tag of the context rows it comes from: [stored], [inferred] or [predicted], and cite collision IDs
   (e.g. Collision_202560C002220) as evidence. For counts, cite a few example IDs from the evidence column and say how many rows exist in total.
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

    def plan(self, llm, question, error=None):
        user = f"Question: {question}"
        if error:
            user += f"\n\nYour previous query failed: {error}\nReturn a corrected JSON object."
        return extract_json(llm.complete(self.plan_system, user, tag="plan" if not error else "plan-retry"))

    @staticmethod
    def check_select_only(sparql):
        if re.search(r"\b(INSERT|DELETE|LOAD|CLEAR|DROP|CREATE|COPY|MOVE|ADD)\b", sparql, re.I) and \
                not re.match(r"\s*(PREFIX[^\n]*\n\s*)*SELECT", sparql, re.I):
            raise ValueError("only SELECT queries are allowed")
        prepareQuery(PFX + sparql)       # syntax check

    def execute(self, sparql):
        self.check_select_only(sparql)
        full = self.kg.full.query(PFX + sparql)
        cols = [str(v) for v in full.vars]
        def cell(x):
            x = "" if x is None else str(x)
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
        """Return dict: answerable, reason, sparql, columns, rows (tagged), error."""
        out = {"question": question, "answerable": False, "reason": "", "sparql": "", "columns": [], "rows": [], "error": None}
        plan, err = None, None
        for attempt in range(2):
            plan = self.plan(llm, question, err)
            out["sparql"] = plan.get("sparql", "")
            out["reason"] = plan.get("reason", "")
            if not plan.get("answerable", False):
                out["reason"] = plan.get("reason", "planner judged the question not answerable from the graph")
                return out
            try:
                out["columns"], out["rows"] = self.execute(plan["sparql"])
                out["answerable"] = True
                out["error"] = None
                return out
            except Exception as e:                      # bad SPARQL: feed the error back once
                err = f"{type(e).__name__}: {str(e)[:300]}"
                out["error"] = err
        return out


def context_text(ret, max_rows=40):
    """Serialise retrieved rows for the answer prompt (with tags and total count)."""
    rows = ret["rows"]
    lines = [f"SPARQL used:\n{ret['sparql']}", f"Total rows returned: {len(rows)} (showing first {min(len(rows), max_rows)})",
             "Columns: " + ", ".join(ret["columns"]) + ", tag"]
    for r in rows[:max_rows]:
        lines.append(" | ".join(r["row"][c] for c in ret["columns"]) + f" | [{r['tag']}]")
    tags = {r["tag"] for r in rows}
    if "inferred" in tags:
        lines.append("Rules that can make rows [inferred]: " + "; ".join(f"{k}: {v[0]}" for k, v in RULES.items()))
    return "\n".join(lines)
