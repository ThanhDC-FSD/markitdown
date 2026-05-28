"""RAG Pipeline package for document ingestion, embedding, retrieval, and LLM integration."""

# Lazy imports to avoid dependency issues
def __getattr__(name):
    if name == "DocumentConverter":
        from .converter import DocumentConverter
        return DocumentConverter
    elif name == "TextChunker":
        from .chunker import TextChunker
        return TextChunker
    elif name == "Embedder":
        from .embedder import Embedder
        return Embedder
    elif name == "Retriever":
        from .retriever import Retriever
        return Retriever
    elif name == "CrossEncoderReranker":
        from .reranker import CrossEncoderReranker
        return CrossEncoderReranker
    elif name == "LLMCaller":
        from .llm_caller import LLMCaller
        return LLMCaller
    elif name == "IntentAnalyzer":
        from .intent_analyzer import IntentAnalyzer
        return IntentAnalyzer
    elif name == "FailureTaxonomyAnalyzer":
        from .failure_taxonomy import FailureTaxonomyAnalyzer
        return FailureTaxonomyAnalyzer
    elif name == "FailureCategory":
        from .failure_taxonomy import FailureCategory
        return FailureCategory
    elif name == "QualityGates":
        from .quality_gates import QualityGates
        return QualityGates
    elif name == "EvaluationFramework":
        from .evaluation_framework import EvaluationFramework
        return EvaluationFramework
    elif name == "GroundedQAClient":
        from .grounded_qa import GroundedQAClient
        return GroundedQAClient
    elif name == "GroundedQAResult":
        from .grounded_qa import GroundedQAResult
        return GroundedQAResult
    elif name == "run_grounded_query":
        from .grounded_qa import run_grounded_query
        return run_grounded_query
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "DocumentConverter",
    "TextChunker",
    "Embedder",
    "Retriever",
    "CrossEncoderReranker",
    "LLMCaller",
    "IntentAnalyzer",
    "FailureTaxonomyAnalyzer",
    "FailureCategory",
    "QualityGates",
    "EvaluationFramework",
    "GroundedQAClient",
    "GroundedQAResult",
    "run_grounded_query",
]
