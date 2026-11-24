import pytest
from crash.embed import TransE
from crash.retrieval import Retriever
from crash.kg import KG


def test_transe_learns_toy_graph():
    T = [("a", "r", "x"), ("b", "r", "y"), ("c", "r", "x")]
    m = TransE(T, dim=8, seed=0).fit(T, epochs=300, lr=0.05, batch=3)
    assert m.predict_tail("a", "r", ["x", "y"], 1)[0][0] == "x"


def test_update_query_is_rejected():
    with pytest.raises(Exception):
        Retriever.check_select_only("INSERT DATA { :a :b :c }")


def test_row_tags_stored_vs_inferred():
    r = Retriever(KG())
    _, rows = r.execute('SELECT ?c WHERE { ?c a :SeriousCollision } LIMIT 3')
    assert {x["tag"] for x in rows} == {"stored"}
    _, rows = r.execute('SELECT ?c WHERE { ?c a :KSICollision } LIMIT 3')
    assert {x["tag"] for x in rows} == {"inferred"}
