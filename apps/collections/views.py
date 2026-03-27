from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.common.envelope import error_response, start_timing, success_response

from .models import Collection
from .serializers import CollectionSerializer, SourceSerializer


@api_view(["GET", "POST"])
def collection_list(request):
    start_timing()

    if request.method == "GET":
        collections = Collection.objects.all().order_by("-created_at")
        serializer = CollectionSerializer(collections, many=True)
        return Response(success_response(serializer.data))

    # POST
    serializer = CollectionSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(success_response(serializer.data), status=status.HTTP_201_CREATED)

    return Response(
        error_response("VALIDATION_ERROR", serializer.errors),
        status=status.HTTP_400_BAD_REQUEST,
    )


@api_view(["GET"])
def collection_detail(request, pk):
    start_timing()

    try:
        collection = Collection.objects.prefetch_related("sources").get(pk=pk)
    except Collection.DoesNotExist:
        return Response(
            error_response("NOT_FOUND", "Collection not found."),
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = CollectionSerializer(collection)
    return Response(success_response(serializer.data))


@api_view(["POST"])
def add_source(request, pk):
    start_timing()

    try:
        collection = Collection.objects.get(pk=pk)
    except Collection.DoesNotExist:
        return Response(
            error_response("NOT_FOUND", "Collection not found."),
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = SourceSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save(collection=collection)
        return Response(success_response(serializer.data), status=status.HTTP_201_CREATED)

    return Response(
        error_response("VALIDATION_ERROR", serializer.errors),
        status=status.HTTP_400_BAD_REQUEST,
    )
