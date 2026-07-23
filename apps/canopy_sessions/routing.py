"""WebSocket routes for the chat app (SP3 multiplayer). session_id is validated in
the consumer, which 4004s an unparsable id rather than 404ing at the router."""
from django.urls import re_path

from .consumers import SessionConsumer

websocket_urlpatterns = [
    re_path(r"^ws/canopy-sessions/(?P<session_id>[0-9a-fA-F-]+)/$", SessionConsumer.as_asgi()),
]
