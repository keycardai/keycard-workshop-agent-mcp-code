from langchain_core.tools import BaseTool

from ..config import Settings
from .requests_queue import make_request_tools


def get_tools(settings: Settings) -> list[BaseTool]:
    # The swap point: register tools for your own resources here.
    return make_request_tools(settings)
