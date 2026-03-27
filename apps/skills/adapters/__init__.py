from .claude_code import ClaudeCodeAdapter
from .open_claw import OpenClawAdapter
from .web import WebAdapter

ADAPTERS = {
    "web": WebAdapter,
    "claude_code": ClaudeCodeAdapter,
    "open_claw": OpenClawAdapter,
}


def get_adapter(runtime: str):
    adapter_class = ADAPTERS.get(runtime)
    if not adapter_class:
        raise ValueError(f"Unknown runtime: {runtime}. Available: {list(ADAPTERS.keys())}")
    return adapter_class()
