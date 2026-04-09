from typing import TypeVar

from pydantic import Field

from .base_schema import BaseSchema

DataType = TypeVar("DataType")


class PaginatedResponse[DataType](BaseSchema):
    total_items: int = Field(..., description="The total number of items matching the query.")
    total_pages: int = Field(..., description="The total number of pages.")
    current_page: int = Field(..., description="The current page number.")
    data: list[DataType] = Field(..., description="The list of items for the current page.")
