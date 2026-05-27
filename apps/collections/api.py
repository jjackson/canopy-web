"""Django Ninja v2 router for the collections surface."""
from __future__ import annotations

from django.http import HttpRequest
from ninja import Router

from apps.api.auth import session_auth
from apps.api.errors import TYPE_NOT_FOUND, ProblemError

from .models import Collection, Source
from .schemas import (
    CollectionCreateIn,
    CollectionOut,
    SourceCreateIn,
    SourceOut,
)

router = Router(auth=session_auth, tags=["collections"])


def _serialize_collection(c: Collection) -> dict:
    """Build a CollectionOut-shaped dict from a Collection."""
    return {
        "id": c.id,
        "name": c.name,
        "description": c.description,
        "sources": [
            {
                "id": s.id,
                "source_type": s.source_type,
                "title": s.title,
                "content": s.content,
                "metadata": s.metadata,
                "created_at": s.created_at,
            }
            for s in c.sources.all().order_by("created_at")
        ],
        "created_at": c.created_at,
        "updated_at": c.updated_at,
    }


@router.post("/", response={201: CollectionOut})
def create_collection(request: HttpRequest, payload: CollectionCreateIn):
    c = Collection.objects.create(name=payload.name, description=payload.description)
    return 201, CollectionOut.model_validate(_serialize_collection(c))


@router.get("/{pk}/", response=CollectionOut)
def get_collection(request: HttpRequest, pk: int) -> CollectionOut:
    c = Collection.objects.filter(pk=pk).first()
    if c is None:
        raise ProblemError(404, "Collection not found", type_=TYPE_NOT_FOUND)
    return CollectionOut.model_validate(_serialize_collection(c))


@router.post("/{pk}/sources/", response={201: SourceOut})
def add_source(request: HttpRequest, pk: int, payload: SourceCreateIn):
    c = Collection.objects.filter(pk=pk).first()
    if c is None:
        raise ProblemError(404, "Collection not found", type_=TYPE_NOT_FOUND)
    source = Source.objects.create(
        collection=c,
        source_type=payload.source_type,
        title=payload.title,
        content=payload.content,
        metadata=payload.metadata,
    )
    return 201, SourceOut.model_validate(source)
