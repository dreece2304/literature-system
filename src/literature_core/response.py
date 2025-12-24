"""Standardized response helpers for consistent API responses.

All MCP tools should use these helpers to ensure consistent response format.
This makes it easier for clients to parse responses and handle errors uniformly.

Usage:
    from literature_core.response import success, error, paginated

    def get_paper(paper_id: int) -> dict:
        try:
            paper = PaperService.get(paper_id)
            return success(paper_to_dict(paper))
        except PaperNotFoundError as e:
            return error(str(e), code=e.code, details={"paper_id": e.paper_id})
"""
from typing import Any


def success(data: Any, message: str | None = None) -> dict:
    """Create a successful response.

    Args:
        data: The response payload (dict, list, or primitive)
        message: Optional success message for the user

    Returns:
        Standardized success response dict

    Example:
        >>> success({"id": 1, "title": "Paper"})
        {"success": True, "data": {"id": 1, "title": "Paper"}}

        >>> success({"count": 5}, message="Created 5 papers")
        {"success": True, "data": {"count": 5}, "message": "Created 5 papers"}
    """
    response = {"success": True, "data": data}
    if message:
        response["message"] = message
    return response


def error(
    message: str,
    code: str | None = None,
    details: dict | None = None,
) -> dict:
    """Create an error response.

    Args:
        message: Human-readable error message
        code: Machine-readable error code (e.g., "PAPER_NOT_FOUND")
        details: Additional context about the error

    Returns:
        Standardized error response dict

    Example:
        >>> error("Paper not found")
        {"success": False, "error": "Paper not found"}

        >>> error("Paper not found", code="PAPER_NOT_FOUND", details={"paper_id": 123})
        {
            "success": False,
            "error": "Paper not found",
            "code": "PAPER_NOT_FOUND",
            "details": {"paper_id": 123}
        }
    """
    response: dict[str, Any] = {"success": False, "error": message}
    if code:
        response["code"] = code
    if details:
        response["details"] = details
    return response


def paginated(
    items: list,
    total: int,
    limit: int,
    offset: int,
    message: str | None = None,
) -> dict:
    """Create a paginated response.

    Args:
        items: List of items for the current page
        total: Total count of all items (before pagination)
        limit: Maximum items per page
        offset: Number of items skipped

    Returns:
        Standardized paginated response dict

    Example:
        >>> paginated([paper1, paper2], total=100, limit=20, offset=0)
        {
            "success": True,
            "data": [paper1, paper2],
            "pagination": {
                "total": 100,
                "limit": 20,
                "offset": 0,
                "count": 2,
                "has_more": True,
                "page": 1,
                "total_pages": 5
            }
        }
    """
    count = len(items)
    has_more = offset + count < total
    page = (offset // limit) + 1 if limit > 0 else 1
    total_pages = (total + limit - 1) // limit if limit > 0 else 1

    response: dict[str, Any] = {
        "success": True,
        "data": items,
        "pagination": {
            "total": total,
            "limit": limit,
            "offset": offset,
            "count": count,
            "has_more": has_more,
            "page": page,
            "total_pages": total_pages,
        },
    }
    if message:
        response["message"] = message
    return response


def created(data: Any, message: str | None = None) -> dict:
    """Create a response for newly created resources.

    Args:
        data: The created resource
        message: Optional success message

    Returns:
        Standardized creation response dict

    Example:
        >>> created({"id": 123, "title": "New Paper"}, message="Paper created")
        {"success": True, "status": "created", "data": {...}, "message": "Paper created"}
    """
    response: dict[str, Any] = {"success": True, "status": "created", "data": data}
    if message:
        response["message"] = message
    return response


def updated(data: Any, message: str | None = None) -> dict:
    """Create a response for updated resources.

    Args:
        data: The updated resource
        message: Optional success message

    Returns:
        Standardized update response dict
    """
    response: dict[str, Any] = {"success": True, "status": "updated", "data": data}
    if message:
        response["message"] = message
    return response


def deleted(
    entity_type: str,
    entity_id: int | str,
    message: str | None = None,
) -> dict:
    """Create a response for deleted resources.

    Args:
        entity_type: Type of deleted entity (e.g., "paper", "note")
        entity_id: ID of the deleted entity
        message: Optional success message

    Returns:
        Standardized deletion response dict

    Example:
        >>> deleted("paper", 123)
        {"success": True, "status": "deleted", "entity_type": "paper", "entity_id": 123}
    """
    response: dict[str, Any] = {
        "success": True,
        "status": "deleted",
        "entity_type": entity_type,
        "entity_id": entity_id,
    }
    if message:
        response["message"] = message
    return response


def batch_result(
    processed: list,
    failed: list,
    skipped: list | None = None,
    message: str | None = None,
) -> dict:
    """Create a response for batch operations.

    Args:
        processed: Successfully processed items
        failed: Items that failed processing
        skipped: Items that were skipped (optional)
        message: Optional summary message

    Returns:
        Standardized batch operation response dict

    Example:
        >>> batch_result(
        ...     processed=[{"id": 1}, {"id": 2}],
        ...     failed=[{"id": 3, "error": "Invalid DOI"}],
        ...     skipped=[{"id": 4, "reason": "Already exists"}]
        ... )
    """
    response: dict[str, Any] = {
        "success": True,
        "summary": {
            "processed": len(processed),
            "failed": len(failed),
            "skipped": len(skipped) if skipped else 0,
            "total": len(processed) + len(failed) + (len(skipped) if skipped else 0),
        },
        "details": {
            "processed": processed,
            "failed": failed,
        },
    }
    if skipped:
        response["details"]["skipped"] = skipped
    if message:
        response["message"] = message
    return response


def search_result(
    results: list,
    query: str,
    search_type: str,
    total: int | None = None,
    message: str | None = None,
) -> dict:
    """Create a response for search operations.

    Args:
        results: Search results
        query: The search query
        search_type: Type of search performed (keyword, semantic, etc.)
        total: Total matching results (if known)
        message: Optional message

    Returns:
        Standardized search response dict
    """
    response: dict[str, Any] = {
        "success": True,
        "query": query,
        "search_type": search_type,
        "count": len(results),
        "results": results,
    }
    if total is not None:
        response["total"] = total
    if message:
        response["message"] = message
    return response


def status_response(
    status: str,
    details: dict | None = None,
    message: str | None = None,
) -> dict:
    """Create a generic status response.

    Useful for operations like sync status, queue status, etc.

    Args:
        status: Status string (e.g., "synced", "queued", "pending")
        details: Additional status details
        message: Optional message

    Returns:
        Standardized status response dict
    """
    response: dict[str, Any] = {"success": True, "status": status}
    if details:
        response["details"] = details
    if message:
        response["message"] = message
    return response
