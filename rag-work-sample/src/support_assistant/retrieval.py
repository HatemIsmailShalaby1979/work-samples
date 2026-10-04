"""BM25 lexical retrieval, implemented in the standard library.

Why BM25 and not embeddings
---------------------------
The brief for this sample asks for a *retrieval-only baseline* established
before any model is involved. A lexical ranker is exactly that: it is fully
deterministic, it needs no model file, no download and no dependency, and its
behaviour can be explained line by line in an interview.

It is also honestly limited. BM25 matches terms, so a query that shares no
vocabulary with a procedure will not retrieve it. The evaluation set in
``evalset/`` contains paraphrased cases specifically to expose that limit, and
the report in ``expected/`` records the failures rather than hiding them.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

from support_assistant.models import Corpus, Procedure, RetrievalHit

# BM25 free parameters. k1 controls term-frequency saturation; b controls the
# strength of length normalisation. 1.5 / 0.75 are the usual defaults.
K1 = 1.5
B = 0.75

#: Title tokens are counted this many times, so a query matching a procedure's
#: title outranks one that only matches a phrase buried in the body.
TITLE_WEIGHT = 2

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")

#: A deliberately small stop list. BM25's IDF term already down-weights words
#: that appear everywhere; this only removes words that carry no topic signal
#: at all and would otherwise create spurious matches on short queries.
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "but",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "for",
        "from",
        "had",
        "has",
        "have",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "me",
        "my",
        "no",
        "not",
        "of",
        "on",
        "or",
        "our",
        "should",
        "so",
        "than",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "to",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "would",
        "you",
        "your",
    }
)


def _collapse_trailing_double(text: str) -> str:
    """Collapse a doubled final consonant left behind by suffix stripping.

    Without this, ``cancelled`` stems to ``cancell`` while ``cancel`` stays
    ``cancel``, and the two never match. Only consonants collapse, so ``see``
    and ``free`` are untouched.
    """
    if len(text) > 3 and text[-1] == text[-2] and text[-1] not in "aeiou":
        return text[:-1]
    return text


def stem(token: str) -> str:
    """A deliberately conservative suffix stripper.

    Not a Porter stemmer. It handles the plural and participle forms that
    matter for support queries — bags/bag, refunds/refund, cancelled/cancel —
    and leaves everything else alone. Over-stemming would merge unrelated
    terms, which is worse than under-stemming in a small corpus.
    """
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 5 and token.endswith("ing"):
        return _collapse_trailing_double(token[:-3])
    if len(token) > 4 and token.endswith("ed"):
        return _collapse_trailing_double(token[:-2])
    if len(token) > 4 and token.endswith("es") and not token.endswith("ses"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def tokenize(text: str) -> list[str]:
    """Lower-case, split on non-alphanumerics, drop stopwords, then stem.

    Kept public because the evaluation report explains retrieval failures in
    terms of which tokens survived this step.
    """
    return [
        stem(token)
        for token in _TOKEN_PATTERN.findall(text.lower())
        if token not in _STOPWORDS and len(token) > 1
    ]


def load_corpus(path: Path) -> Corpus:
    """Load and validate a corpus from JSON."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return Corpus.model_validate(payload)


class Bm25Index:
    """An in-memory BM25 index over a :class:`Corpus`."""

    def __init__(self, corpus: Corpus) -> None:
        self._corpus = corpus
        self._documents: dict[str, list[str]] = {}
        self._term_frequencies: dict[str, Counter[str]] = {}
        self._document_frequency: Counter[str] = Counter()

        for procedure in corpus.procedures:
            tokens = self._index_tokens(procedure)
            self._documents[procedure.procedure_id] = tokens
            frequencies = Counter(tokens)
            self._term_frequencies[procedure.procedure_id] = frequencies
            for term in frequencies:
                self._document_frequency[term] += 1

        self._document_count = len(self._documents)
        self._average_length = (
            sum(len(tokens) for tokens in self._documents.values())
            / self._document_count
            if self._document_count
            else 0.0
        )

    @staticmethod
    def _index_tokens(procedure: Procedure) -> list[str]:
        """Build the token list for one procedure, weighting the title."""
        title_tokens = tokenize(procedure.title)
        weighted_title = title_tokens * TITLE_WEIGHT
        return weighted_title + tokenize(procedure.body)

    @property
    def corpus(self) -> Corpus:
        return self._corpus

    def _idf(self, term: str) -> float:
        """Inverse document frequency, in the always-positive BM25 form."""
        frequency = self._document_frequency.get(term, 0)
        return math.log(
            1.0 + (self._document_count - frequency + 0.5) / (frequency + 0.5)
        )

    def score(self, query: str) -> dict[str, float]:
        """Score every procedure against a query. Unmatched procedures score 0."""
        query_terms = tokenize(query)
        scores: dict[str, float] = {
            procedure_id: 0.0 for procedure_id in self._documents
        }

        if not query_terms:
            return scores

        for procedure_id, frequencies in self._term_frequencies.items():
            length = len(self._documents[procedure_id])
            total = 0.0
            for term in query_terms:
                occurrences = frequencies.get(term, 0)
                if occurrences == 0:
                    continue
                denominator = occurrences + K1 * (
                    1.0 - B + B * (length / self._average_length)
                )
                total += self._idf(term) * (occurrences * (K1 + 1.0)) / denominator
            scores[procedure_id] = total

        return scores

    def search(self, query: str, top_k: int = 5) -> list[RetrievalHit]:
        """Return the ``top_k`` highest-scoring procedures, best first.

        Ties are broken by ``procedure_id`` so the ranking is deterministic —
        without that, two equally-scored procedures could swap places between
        runs and the evaluation would not be reproducible.
        """
        if top_k < 1:
            raise ValueError("top_k must be at least 1")

        scores = self.score(query)
        ranked = sorted(
            scores.items(),
            key=lambda item: (-item[1], item[0]),
        )

        hits: list[RetrievalHit] = []
        for rank, (procedure_id, score) in enumerate(ranked[:top_k], start=1):
            procedure = self._corpus.by_id(procedure_id)
            if procedure is None:  # pragma: no cover - guarded by construction
                continue
            hits.append(RetrievalHit(procedure=procedure, score=score, rank=rank))
        return hits
