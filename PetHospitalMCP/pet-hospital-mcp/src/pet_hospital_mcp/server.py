from __future__ import annotations

import logging

import uvicorn
from mcp.server.mcpserver.server import MCPServer
from starlette.responses import JSONResponse

from .config import get_settings
from .errors import AppError, ValidationError
from .logging_config import configure_logging
from .rest_client import PetHospitalRestClient
from .tools.list_pets import ListPetsInput, ListPetsSuccess, ListPetsTool, ToolErrorOutput

configure_logging()
logger = logging.getLogger(__name__)

server = MCPServer(
    name="pet_hospital_mcp",
    title="Pet Hospital MCP",
    description="Exposes the pet hospital REST API through a stateless MCP 2026-07-28 Streamable HTTP server.",
    version="0.1.0",
)

settings = get_settings()
client = PetHospitalRestClient(settings.pet_hospital_base_url)
list_pets_tool = ListPetsTool(client)


@server.tool(
    name="list_pets",
    description=(
        "Query the pet hospital archive with optional text search, filters, sorting, and pagination. "
        "This wraps GET /api/v1/pets and returns the backend data payload in the standard MCP result format."
    ),
)
async def list_pets(
    q: str | None = None,
    name: str | None = None,
    ownerName: str | None = None,
    ownerPhone: str | None = None,
    species: str | None = None,
    doctor: str | None = None,
    disease: str | None = None,
    status: str | None = None,
    min: float | None = None,
    max: float | None = None,
    sortBy: str | None = None,
    order: str | None = None,
    page: int = 1,
    pageSize: int = 20,
) -> ListPetsSuccess | ToolErrorOutput:
    try:
        dto = ListPetsInput.model_validate({
            "q": q,
            "name": name,
            "ownerName": ownerName,
            "ownerPhone": ownerPhone,
            "species": species,
            "doctor": doctor,
            "disease": disease,
            "status": status,
            "min": min,
            "max": max,
            "sortBy": sortBy,
            "order": order,
            "page": page,
            "pageSize": pageSize,
        })
        return ListPetsSuccess.model_validate(await list_pets_tool(dto.model_dump(exclude_none=True)))
    except AppError as exc:
        return ToolErrorOutput(error=exc.to_payload()["error"])
    except ValidationError as exc:
        return ToolErrorOutput(error=exc.to_payload()["error"])


@server.custom_route("/health", methods=["GET"])
async def health(request):
    return JSONResponse({"status": "ok"})


def main() -> None:
    settings = get_settings()
    app = server.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=False,
        stateless_http=True,
        host=settings.host,
    )
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")
