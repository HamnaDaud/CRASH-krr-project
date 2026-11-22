# CRASH – Collision Risk Analysis through Semantic Hierarchies (AI-3001 KRR, Fall 2026)

Knowledge-grounded road-safety advisor for Great Britain, built on the DfT STATS19 2025 data (OGL v3.0). Team: Hamna Daud (24i0039, `HamnaDaud`), Ritaj Suleman (24i0112, `ritaj-suleman`), Tahreem Fatima (24i0025).
This repository holds **both iterations** in one structure:

| Path | What it is |
|---|---|
| `iteration1/` | The submitted Iteration 1 package: `Report/` (combined report PDF), `SPARQL_Queries/` (Q1–Q10, Inference1–3, R7 INSERT, query list with expected results), `Results/` (one CSV per query + screenshot PDF), `Visualization/` (GraphDB graph views), `README.txt` |
| `data/` | ontology `crash_schema.ttl` (171 triples), RDF `crash_data.ttl` (30,865 triples; 31,036 together), builder `crash_build_abox.py` – the files submitted in Iteration 1, used unchanged by Iteration 2 |
| `crash/`, `eval/`, `tests/`, `results/` | Iteration 2 code, evaluation, tests and results (see below) |
| `docs/` | explainability examples, captured console screenshots, Git steps (`CRASH_Git_Steps_Phase2.*`), the course briefs in `docs/brief/` |
| `report/` | Iteration 2 report source (`build_report.py`) and the PDF |

The raw DfT CSV files (about 48 MB) are **not** in the repository: see "Data preparation" below. Frozen submission version: see the commit hash in the report.

---
# Iteration 2 – knowledge-grounded application

AI-3001 Knowledge Representation & Reasoning, Fall 2026. Team: Hamna Daud (24i0039, `HamnaDaud`), Ritaj Suleman (24i0112, `ritaj-suleman`), Tahreem Fatima (24i0025).
Repository: <https://github.com/HamnaDaud/CRASH-krr-project> · Final submission commit: `<COMMIT-HASH-PLACEHOLDER>` · Demo video: `<DEMO-LINK-PLACEHOLDER>`

CRASH answers questions about the DfT STATS19 2025 road-collision data (North Wales + Gwent police, 1,115 collisions, 1,962 vehicles,
1,491 casualties; Open Government Licence v3.0) from a knowledge graph. This iteration adds:

1. **Symbolic reasoning** (rules R1–R8: KSICollision, VRUCollision, VulnerableRoadUser, partOf chain, ChildCasualty, HighRiskArea).
2. **Hybrid rule + embedding reasoning (Option D)**: a numpy TransE model predicts held-out links and finds similar collisions
   inside the pool the rules certify. Predictions are always labelled *predicted*.
3. **KG-grounded LLM application (KG-RAG)**: question → LLM writes SPARQL from the schema → executed on the rule-materialised graph →
   rows tagged *stored* / *inferred* → LLM writes the answer from that context only → grounding check; refuses when evidence is missing.
4. **Evaluation**: 10 competency questions, LLM-only vs KG-grounded with the same model and settings, plus 3 insufficient-evidence probes.

```
question → [LLM planner: SPARQL] → rdflib on stored + inferred triples → tagged rows (stored/inferred)
        → [LLM answerer: context only] → answer (AI-written) + evidence table + grounding check
TransE (stored triples only) → [predicted] similar collisions / missing attributes, restricted by rule classes
```

## Layout
| Path | Content |
|---|---|
| `data/` | ontology, RDF data and builder (shared with Iteration 1); raw CSV links below |
| `crash/kg.py` | load graph, rules R1–R8 as SPARQL INSERT with per-triple rule provenance |
| `crash/embed.py`, `crash/train_eval_embeddings.py` | TransE, hold-out link prediction (MRR, Hits@k) |
| `crash/hybrid.py` | rule + embedding reasoning |
| `crash/retrieval.py`, `crash/answer.py`, `crash/llm.py` | planner/answer prompts, SPARQL execution, tags, refusal, LLM backends |
| `crash/app.py` | CLI and web chat |
| `eval/` | 10 CQs, gold SPARQL (never shown to the system), probes, `run_eval.py` |
| `results/` | embedding metrics, evaluation results |
| `tests/` | pytest checks of rules, tagging, TransE |
| `docs/explainability_examples.md` | 3+ worked examples |

## Prerequisites and setup
Python 3.11+. Tested with Python 3.13, rdflib 7, numpy 2, pandas 3. The LLM is called through Groq's **free** OpenAI-compatible API
(model `openai/gpt-oss-120b`); no credit card is needed.

1. Get a free key: sign up at <https://console.groq.com> and create a key at <https://console.groq.com/keys>.
2. Install and configure:
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp config.sample.env .env      # then edit .env: paste your key after LLM_API_KEY=  (.env is git-ignored)
export $(grep -v '^#' .env | xargs)                    # Windows PowerShell: $env:LLM_API_KEY="..."  (same for the other variables)
```
Never commit a real key. The same model, temperature 0 and token limits are used for both evaluation conditions (LLM-only and KG-grounded).

**Free-tier limits.** Groq allows 8,000 tokens per minute for this model. `crash/llm.py` keeps itself under that budget automatically
(`CRASH_TPM`), so a single question takes a few seconds and the full evaluation (13 questions, about 40 LLM calls) takes about 15 minutes.
There is also a **daily** limit (about 200,000 tokens for `gpt-oss-120b`, roughly 40 questions; it is per Groq account, not per key). Do not burn it on
test runs before a live demo. Optionally set `CRASH_FALLBACK_MODEL=openai/gpt-oss-20b` in `.env`: the app then switches to that model (own quota, weaker)
when the daily limit is reached. Leave it empty for the evaluation so both conditions use one model.
Other OpenAI-compatible providers work by changing `LLM_BASE_URL` and `CRASH_MODEL` (see `config.sample.env`); xAI Grok is credit-based, not free.

## Data preparation (only if you want to rebuild the RDF)
Download the three 2025 CSVs and the data guide from <https://www.gov.uk/government/statistical-data-sets/road-safety-open-data>
(e.g. `https://data.dft.gov.uk/road-accidents-safety-data/dft-road-casualty-statistics-collision-2025.csv`, same pattern for `vehicle` and
`casualty`), put them next to `data/crash_build_abox.py` and run `python data/crash_build_abox.py data data/crash_data.ttl`.
The committed `data/crash_data.ttl` already contains the result (the raw CSVs are not committed because of their size).

## Run
```bash
python -m pytest -q tests                    # symbolic layer + retrieval guard + TransE (no key needed)
python -m crash.app --ask "Which five local authorities had the most fatal or serious collisions on A roads in wet or icy conditions?"
python -m crash.app                          # interactive chat (needs LLM_API_KEY)
python -m crash.app --web 8000               # web UI at http://127.0.0.1:8000 (cards, evidence table, example buttons, /similar)
python -m crash.train_eval_embeddings --seed 0   # ~25 s per seed; writes results/embedding_eval_seed0.json (no key needed)
python -m eval.gold                          # recompute expected answers from gold SPARQL (no key needed)
python -m eval.run_eval --backend openai     # 10 CQ + 3 probes, both conditions -> results/eval_results.json (about 15 min)
python -m eval.reliability --runs 3         # repeat the 3 demo questions on the live model and count correct answers (uses tokens!)
python -m eval.run_eval --backend openai --limit 3 --out /tmp/slice.json    # quick live check, does not touch the committed results
```
In the chat: `/similar Collision_202560C002220` (embedding-based, predicted), `/rules`. A step-by-step live demo is in `docs/DEMO.md`.

### Legacy offline replay (`--backend manual`, not needed for the demo)
`eval/manual/` holds prompt/response files from an earlier run in which a Claude session answered the prompts because no API key was available.
They are kept only for history and are not used by the default path or by the committed `results/eval_results.json`, which now comes from the Groq run.

## Labels used everywhere
`[stored]` fact in the graph · `[inferred]` derived by rule R1–R8 (tag computed by re-running the query on stored triples only) ·
`[predicted]` TransE prediction, never a confirmed fact · *AI-written* = the LLM's text.

## Credits and licences
Data: UK DfT Road Safety Open Data, OGL v3.0. TransE: Bordes et al. 2013. Libraries: rdflib, numpy, pandas, OpenAI Python SDK (client for the Groq OpenAI-compatible API).
