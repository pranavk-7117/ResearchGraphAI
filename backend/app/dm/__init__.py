"""
Discrete Mathematics package (DM-1) for ResearchGraphAI.
Built strictly atop our hand-built DS-1 structures (zero networkx/sklearn imports).
"""

from app.dm.inclusion_exclusion import inclusion_exclusion_breakdown, union_size
from app.dm.main_path import global_main_path, key_route_main_path
from app.dm.partial_order import transitive_closure, transitive_reduction
from app.dm.path_counting import compute_spc
from app.dm.reading_path import compute_reading_path

__all__ = [
    "transitive_closure",
    "transitive_reduction",
    "compute_spc",
    "global_main_path",
    "key_route_main_path",
    "union_size",
    "inclusion_exclusion_breakdown",
    "compute_reading_path",
]
