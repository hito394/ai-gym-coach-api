"""Exercise directory and search endpoints."""
from typing import Dict, List, Optional

from fastapi import APIRouter, Query

from app.utils.exercise_registry import _CATEGORY_MAP, ALL_GYM_EXERCISES, get_exercise_category

router = APIRouter(prefix="/exercises", tags=["exercises"])


@router.get("", summary="List all gym exercises grouped by category")
def list_exercises() -> Dict[str, List[str]]:
    """Return every supported gym exercise, organised by category."""
    return {category: sorted(keys) for category, keys in _CATEGORY_MAP.items()}


@router.get("/search", summary="Search exercises by keyword")
def search_exercises(
    q: str = Query(..., min_length=1, description="Search term"),
    category: Optional[str] = Query(default=None, description="Filter by category"),
) -> Dict[str, object]:
    """
    Search exercises whose key contains *q* (case-insensitive).

    Optionally restrict results to a single *category*.
    """
    term = q.lower().strip().replace(" ", "_")

    if category:
        candidates = sorted(_CATEGORY_MAP.get(category, frozenset()))
    else:
        candidates = sorted(ALL_GYM_EXERCISES)

    matches = [key for key in candidates if term in key]

    return {
        "query": q,
        "category_filter": category,
        "total": len(matches),
        "results": [
            {"key": key, "category": get_exercise_category(key)}
            for key in matches
        ],
    }


@router.get("/categories", summary="List available exercise categories")
def list_categories() -> List[str]:
    """Return the list of exercise categories."""
    return sorted(_CATEGORY_MAP.keys())
