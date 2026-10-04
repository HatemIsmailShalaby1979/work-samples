"""A local-only, evaluated support-policy assistant.

A work sample, not a product. It demonstrates retrieval, an optional
local-model answer path, a deterministic decision gate, and a human-approval
boundary — with a labelled evaluation set and a measured comparison between the
simplest baseline and the gated workflow.

Nothing here is production experience, and no part of it has been deployed.
"""

from support_assistant.adapters import (
    AnswerGenerator,
    GenerationError,
    MockAnswerGenerator,
    OllamaAnswerGenerator,
    is_ollama_available,
)
from support_assistant.gate import GateConfig, evaluate
from support_assistant.metrics import category_breakdown, compute_metrics
from support_assistant.models import (
    ApprovalRecord,
    ApprovalStatus,
    AssistantResponse,
    CaseResult,
    ConsequentialAction,
    Corpus,
    Decision,
    DecisionReason,
    EvalCase,
    EvalCategory,
    GateOutcome,
    Metrics,
    Procedure,
    ProcedureStatus,
    QueryRequest,
    RetrievalHit,
)
from support_assistant.retrieval import Bm25Index, load_corpus, stem, tokenize
from support_assistant.workflow import (
    RetrievalOnlyBaseline,
    SupportAssistant,
    WorkflowConfig,
    WorkflowTimeout,
    build_assistant,
    detect_consequential_action,
    execute_approved_action,
    strategies,
)

__version__ = "0.1.0"

__all__ = [
    "AnswerGenerator",
    "ApprovalRecord",
    "ApprovalStatus",
    "AssistantResponse",
    "Bm25Index",
    "CaseResult",
    "ConsequentialAction",
    "Corpus",
    "Decision",
    "DecisionReason",
    "EvalCase",
    "EvalCategory",
    "GateConfig",
    "GateOutcome",
    "GenerationError",
    "Metrics",
    "MockAnswerGenerator",
    "OllamaAnswerGenerator",
    "Procedure",
    "ProcedureStatus",
    "QueryRequest",
    "RetrievalHit",
    "RetrievalOnlyBaseline",
    "SupportAssistant",
    "WorkflowConfig",
    "WorkflowTimeout",
    "__version__",
    "build_assistant",
    "category_breakdown",
    "compute_metrics",
    "detect_consequential_action",
    "evaluate",
    "execute_approved_action",
    "is_ollama_available",
    "load_corpus",
    "stem",
    "strategies",
    "tokenize",
]
