from langchain_core.tools import BaseTool

from ..config import Settings
from .directory import make_directory_tools
from .requests_queue import make_request_tools


def get_tools(settings: Settings) -> list[BaseTool]:
    # The swap point: register tools for your own resources here (Chapter 8).
    return make_directory_tools(settings) + make_request_tools(settings)
