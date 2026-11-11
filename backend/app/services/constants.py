"""
Shared domain constants for graph relations, evidence bases, and evolution kinds.
"""

# PaperRelation.relation_type values
RELATION_CITES = "cites"
RELATION_SIMILAR = "similar"
RELATION_COUPLING = "coupling"

# PaperRelation / EvolutionTransition basis values
BASIS_CITATION_METADATA = "citation_metadata"
BASIS_EMBEDDING_SIMILARITY = "embedding_similarity"
BASIS_BIBLIOGRAPHIC_COUPLING = "bibliographic_coupling"
BASIS_EXTRACTED_TEXT = "extracted_text"
BASIS_LLM_INFERENCE = "llm_inference"

# Evolution transition kinds
KIND_CITATION = "citation"
KIND_THEMATIC_LINEAGE = "thematic_lineage"
KIND_METHOD_CHANGE = "method_change"


def layer_for_relation(relation_type: str) -> str:
    """Map PaperRelation.relation_type to multi-layer graph layer name."""
    if relation_type == RELATION_CITES:
        return "citation"
    if relation_type == RELATION_COUPLING:
        return "coupling"
    return "semantic"
