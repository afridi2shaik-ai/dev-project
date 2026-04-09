from collections.abc import Callable

from fastapi.routing import APIRoute
from opentelemetry import trace
from opentelemetry.propagate import extract
from starlette.requests import Request


class TracingAPIRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> any:
            # Extract the context from the incoming request headers
            # B3 headers are commonly used for trace propagation (e.g., by Istio, Linkerd)
            # W3C Trace Context headers (traceparent, tracestate) are the standard
            carrier = dict(request.headers)
            parent_context = extract(carrier)

            # Start a new span with the extracted context as the parent
            tracer = trace.get_tracer(__name__)
            with tracer.start_as_current_span(self.name, context=parent_context):
                response = await original_route_handler(request)
            return response

        return custom_route_handler
