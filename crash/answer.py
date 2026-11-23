"""Question -> retrieve -> answer, with provenance labels and a post-hoc grounding check."""
import re
from .retrieval import Retriever, context_text, ANSWER_SYSTEM, LLM_ONLY_SYSTEM
from .llm import PendingResponse
import os

ID_RE = re.compile(r"(?:Collision|Casualty|Vehicle)_[0-9A-Z]+(?:_\d+)?")
NUM_RE = re.compile(r"\b\d+\b")


def grounding_check(answer, context):
    """Flag IDs/numbers in the AI-written answer that do not occur in the retrieved context."""
    ctx_ids = set(ID_RE.findall(context)) | {("Collision_" + x) for x in re.findall(r"\b(20\d{2}[0-9A-Z]{9,})\b", context)}
    ctx_text = context
    bad_ids = [i for i in set(ID_RE.findall(answer)) if i not in ctx_ids and i.split("_", 1)[-1] not in ctx_text]
    ctx_nums = set(NUM_RE.findall(ctx_text))
    bad_nums = [n for n in set(NUM_RE.findall(re.sub(ID_RE, "", answer))) if n not in ctx_nums and int(n) > 12]
    return {"unsupported_ids": sorted(bad_ids), "unsupported_numbers": sorted(bad_nums)}


def ask_grounded(retriever, llm, question, max_rows=None):
    max_rows = max_rows or int(os.environ.get("CRASH_CONTEXT_ROWS", "30"))
    ret = retriever.retrieve(llm, question)
    res = {"question": question, "retrieval": ret, "answer": None, "status": None}
    if not ret["answerable"] or not ret["rows"]:
        res["status"] = "insufficient_evidence"
        why = ret["reason"] or "the graph returned no matching rows for this question"
        if ret.get("error") and ret["sparql"]:
            why = f"no usable query result after {ret.get('attempts', 1)} attempts ({ret['error']})"
        res["answer"] = "INSUFFICIENT_EVIDENCE: " + why + " No answer is given rather than guessing."
        return res
    ctx = context_text(ret, max_rows)
    res["context"] = ctx
    ans = llm.complete(ANSWER_SYSTEM, f"CONTEXT:\n{ctx}\n\nQUESTION: {question}", tag="answer")
    res["answer"] = ans.strip()
    res["status"] = "insufficient_evidence" if ans.strip().startswith("INSUFFICIENT_EVIDENCE") else "answered"
    res["grounding"] = grounding_check(ans, ctx)
    return res


def ask_llm_only(llm, question):
    return llm.complete(LLM_ONLY_SYSTEM, question, tag="llm-only").strip()
