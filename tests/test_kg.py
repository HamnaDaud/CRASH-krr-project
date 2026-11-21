"""Verification of the symbolic layer against the numbers verified in Iteration 1 (GraphDB). No LLM needed."""
import pytest
from crash.kg import KG, PFX, RES


@pytest.fixture(scope="module")
def kg():
    return KG()


def n(kg, q):
    return int(next(iter(kg.full.query(PFX + q)))[0])


def test_stored_counts(kg):
    assert n(kg, "SELECT (COUNT(DISTINCT ?c) AS ?n) WHERE { ?c :collisionIndex ?i }") == 1115


def test_ksi_inferred(kg):
    assert n(kg, "SELECT (COUNT(?c) AS ?n) WHERE { ?c a :KSICollision }") == 432


def test_high_risk_area(kg):
    assert n(kg, "SELECT (COUNT(?l) AS ?n) WHERE { ?l a :HighRiskArea }") == 30


def test_vru_collisions(kg):
    assert n(kg, "SELECT (COUNT(?c) AS ?n) WHERE { ?c a :VRUCollision }") == 520


def test_ksi_is_inferred_not_stored(kg):
    c = RES["Collision_202560C000676"]
    assert ("KSICollision", "inferred:R1") in kg.types_of(c) and ("SeriousCollision", "stored") in kg.types_of(c)


def test_transitive_partof(kg):
    q = "SELECT (COUNT(?l) AS ?n) WHERE { ?l a :LSOA ; :partOf ?p . ?p a :PoliceForce }"
    assert n(kg, q) == 510
