"""Tests for tokenisation and BM25 retrieval."""

from __future__ import annotations

import pathlib

import pytest

from support_assistant import Bm25Index, load_corpus
from support_assistant.retrieval import stem, tokenize

CORPUS_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "corpus"
    / "harbourline_procedures.json"
)


@pytest.fixture(scope="module")
def index() -> Bm25Index:
    return Bm25Index(load_corpus(CORPUS_PATH))


# --- Tokenisation -------------------------------------------------------------


def test_stopwords_are_removed() -> None:
    assert tokenize("what is the refund policy") == ["refund", "policy"]


def test_stemming_handles_plurals() -> None:
    """The failure this guards against: 'bags' never matching 'bag'."""
    assert stem("bags") == "bag"
    assert stem("refunds") == "refund"
    assert stem("policies") == "policy"


def test_stemming_handles_participles_and_collapses_doubling() -> None:
    """'cancelled' must meet 'cancel'; a naive strip gives 'cancell'."""
    assert stem("cancelled") == "cancel"
    assert stem("travelling") == "travel"
    assert stem("cancel") == "cancel"


def test_stemming_leaves_short_words_alone() -> None:
    for word in ("bus", "gas", "ss", "is"):
        assert stem(word) == word


def test_tokenize_drops_single_characters_and_punctuation() -> None:
    assert tokenize("a b c 1 22 !!!") == ["22"]


# --- Ranking ------------------------------------------------------------------


def test_relevant_procedure_ranks_first(index: Bm25Index) -> None:
    hits = index.search("how do I book a crossing online", top_k=3)
    assert hits
    assert hits[0].procedure.procedure_id == "booking-online"


def test_results_are_ordered_by_descending_score(index: Bm25Index) -> None:
    hits = index.search("baggage allowance", top_k=5)
    scores = [hit.score for hit in hits]
    assert scores == sorted(scores, reverse=True)


def test_ranking_is_deterministic(index: Bm25Index) -> None:
    """Identical queries must give identical rankings, ties included."""
    first = [
        hit.procedure.procedure_id for hit in index.search("refund policy", top_k=5)
    ]
    second = [
        hit.procedure.procedure_id for hit in index.search("refund policy", top_k=5)
    ]
    assert first == second


def test_unrelated_query_scores_zero(index: Bm25Index) -> None:
    hits = index.search("cryptocurrency mining rig", top_k=3)
    assert all(hit.score == 0.0 for hit in hits)


def test_empty_query_returns_zero_scores(index: Bm25Index) -> None:
    hits = index.search("", top_k=3)
    assert len(hits) == 3
    assert all(hit.score == 0.0 for hit in hits)


def test_top_k_is_respected(index: Bm25Index) -> None:
    assert len(index.search("refund", top_k=2)) == 2


def test_ranks_are_one_based_and_contiguous(index: Bm25Index) -> None:
    hits = index.search("refund policy", top_k=4)
    assert [hit.rank for hit in hits] == [1, 2, 3, 4]


# --- Negative -----------------------------------------------------------------


def test_top_k_below_one_is_rejected(index: Bm25Index) -> None:
    with pytest.raises(ValueError):
        index.search("refund", top_k=0)


def test_missing_corpus_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_corpus(pathlib.Path("does-not-exist.json"))
