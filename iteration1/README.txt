(Submitted Iteration 1 package, kept as submitted except the paths noted in the first lines below.)
CRASH - AI-3001 Iteration 1 (team CRASH). Data: STATS19 2025, North Wales + Gwent police.
Team: Hamna Daud (24i-0039), Ritaj Suleman (24i-0112), Tahreem Fatima (24i-0025)

(In this repository the ontology, RDF data and builder are the shared copies in ../data/ (byte-identical to the submitted
Ontology/ and RDF_Knowledge_Graph/); the raw CSVs and data guide are not committed, see ../README.md.)
SPARQL_Queries/         Q1-Q10, Inference1-3, R7_HighRiskArea_INSERT.rq, CRASH_PartE_Queries.md (queries + expected results)
Results/                CSV result per query + CRASH_Query_Result_Screenshots.pdf
Visualization/          CRASH_GraphDB_Visualization.pdf
Report/                 CRASH_Iteration1_Report.pdf (single combined report)

Run: load ../data/crash_schema.ttl and ../data/crash_data.ttl into a GraphDB repository with the OWL2-RL ruleset, run R7_HighRiskArea_INSERT.rq once, then run the .rq files with "Include inferred" ON.
Rebuild data: python ../data/crash_build_abox.py <folder with the 3 CSVs + xlsx> <out.ttl>
