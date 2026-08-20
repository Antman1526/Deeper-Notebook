from fastapi import APIRouter, HTTPException
from loguru import logger

from api.models import NoteResponse, SaveAsNoteRequest, SourceInsightResponse
from api.utils.iso import iso  # v0.7.182 — Safari-safe datetime serialization
from deeper_notebook.domain.notebook import SourceInsight
from deeper_notebook.exceptions import InvalidInputError, NotFoundError

router = APIRouter()


@router.get("/insights/{insight_id}", response_model=SourceInsightResponse)
async def get_insight(insight_id: str):
    """Get a specific insight by ID."""
    try:
        insight = await SourceInsight.get(insight_id)
        if not insight:
            raise HTTPException(status_code=404, detail="Insight not found")

        # Get source ID from the insight relationship.
        # v0.7.64 — guard against the orphaned-insight case explicitly.
        # If the source was deleted without cascading to its insights
        # (older data, or a partial-cascade race), `get_source()`
        # returns None and the immediately-following `source.id` access
        # used to AttributeError, which the generic `except Exception`
        # below mapped to "Error fetching insight" 500. The actual
        # situation is a 404-shaped problem: the insight references a
        # source that no longer exists.
        source = await insight.get_source()
        if source is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Insight references a source that no longer exists "
                    "(orphaned record from an incomplete delete)."
                ),
            )

        return SourceInsightResponse(
            id=insight.id or "",
            source_id=source.id or "",
            insight_type=insight.insight_type,
            content=insight.content,
            created=iso(insight.created),
            updated=iso(insight.updated),
        )
    except HTTPException:
        raise
    except NotFoundError:
        # v0.7.160 — let the global handler at api/main.py:567 map to
        # HTTP 404; previously the generic except below clobbered to 500.
        raise
    except Exception as e:
        logger.error(f"Error fetching insight {insight_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching insight")


@router.delete("/insights/{insight_id}")
async def delete_insight(insight_id: str):
    """Delete a specific insight."""
    try:
        insight = await SourceInsight.get(insight_id)
        if not insight:
            raise HTTPException(status_code=404, detail="Insight not found")

        await insight.delete()

        return {"message": "Insight deleted successfully"}
    except HTTPException:
        raise
    except NotFoundError:
        # v0.7.160 — same rationale as get_insight above.
        raise
    except Exception as e:
        logger.error(f"Error deleting insight {insight_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error deleting insight")


@router.post("/insights/{insight_id}/save-as-note", response_model=NoteResponse)
async def save_insight_as_note(insight_id: str, request: SaveAsNoteRequest):
    """Convert an insight to a note."""
    try:
        insight = await SourceInsight.get(insight_id)
        if not insight:
            raise HTTPException(status_code=404, detail="Insight not found")

        # Use the existing save_as_note method from the domain model
        note = await insight.save_as_note(request.notebook_id)

        return NoteResponse(
            id=note.id or "",
            title=note.title,
            content=note.content,
            note_type=note.note_type,
            created=iso(note.created),
            updated=iso(note.updated),
        )
    except HTTPException:
        raise
    except NotFoundError:
        # v0.7.160 — same rationale as get_insight above.
        raise
    except InvalidInputError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error saving insight {insight_id} as note: {str(e)}")
        raise HTTPException(status_code=500, detail="Error saving insight as note")
