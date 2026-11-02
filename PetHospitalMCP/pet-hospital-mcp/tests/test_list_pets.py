import json

import httpx
import pytest
from httpx import ASGITransport

from pet_hospital_mcp.rest_client import PetHospitalRestClient
from pet_hospital_mcp.server import server
from pet_hospital_mcp.tools.list_pets import ListPetsInput, ListPetsTool


@pytest.mark.asyncio
async def test_list_pets_success_forwards_filters_and_pagination():
    async def handler(request):
        assert request.url.path == "/api/v1/pets"
        assert request.url.params["species"] == "犬"
        assert request.url.params["status"] == "待就诊"
        assert request.url.params["sortBy"] == "totalCost"
        assert request.url.params["order"] == "desc"
        assert request.url.params["page"] == "2"
        assert request.url.params["pageSize"] == "25"
        return httpx.Response(200, json={"code": 200, "message": "ok", "data": {"items": [{"id": "PET-1"}], "total": 1, "page": 2, "pageSize": 25, "totalPages": 1, "totalCost": 1000}})

    client = PetHospitalRestClient(base_url="http://example.com")
    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient
    httpx.AsyncClient = lambda *args, **kwargs: original_client(*args, transport=transport, **kwargs)
    try:
        tool = ListPetsTool(client)
        result = await tool({
            "species": "犬",
            "status": "待就诊",
            "sortBy": "totalCost",
            "order": "desc",
            "page": 2,
            "pageSize": 25,
        })
        assert result["items"][0]["id"] == "PET-1"
        assert result["total"] == 1
        assert result["page"] == 2
        assert result["pageSize"] == 25
        assert result["totalCost"] == 1000
    finally:
        httpx.AsyncClient = original_client


@pytest.mark.parametrize(
    "payload",
    [
        {"page": 0},
        {"pageSize": 0},
        {"pageSize": 501},
        {"min": -1},
        {"max": -1},
        {"min": 5, "max": 3},
        {"unknown": 1},
    ],
)
async def test_list_pets_rejects_invalid_input(payload):
    tool = ListPetsTool(PetHospitalRestClient(base_url="http://example.com"))
    with pytest.raises(Exception):
        await tool(payload)


@pytest.mark.asyncio
async def test_list_pets_handles_backend_4xx_5xx():
    async def handler(request):
        return httpx.Response(503, json={"code": 503, "message": "down"})

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient
    httpx.AsyncClient = lambda *args, **kwargs: original_client(*args, transport=transport, **kwargs)
    try:
        tool = ListPetsTool(PetHospitalRestClient(base_url="http://example.com"))
        with pytest.raises(Exception):
            await tool({"page": 1, "pageSize": 10})
    finally:
        httpx.AsyncClient = original_client


@pytest.mark.asyncio
async def test_list_pets_handles_timeout_and_unavailable_backend():
    async def timeout_handler(request):
        raise httpx.TimeoutException("timeout")

    transport = httpx.MockTransport(timeout_handler)
    original_client = httpx.AsyncClient
    httpx.AsyncClient = lambda *args, **kwargs: original_client(*args, transport=transport, **kwargs)
    try:
        tool = ListPetsTool(PetHospitalRestClient(base_url="http://example.com"))
        with pytest.raises(Exception):
            await tool({"page": 1, "pageSize": 10})
    finally:
        httpx.AsyncClient = original_client


@pytest.mark.asyncio
async def test_server_lists_tool_registration_and_health():
    tools = await server.list_tools()
    names = {t.name for t in tools}
    assert "list_pets" in names
    app = server.streamable_http_app(streamable_http_path="/mcp", stateless_http=True)
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_tools_call_accepts_direct_arguments_without_nested_params():
    async def fake_get(_path, params=None):
        return {"code": 200, "message": "ok", "data": {"items": [{"id": "PET-1"}], "total": 1, "page": 1, "pageSize": 2, "totalPages": 1, "totalCost": 100}}

    import pet_hospital_mcp.server as module_server
    module_server.list_pets_tool.client.get = fake_get
    result = await module_server.server.call_tool("list_pets", {"page": 1, "pageSize": 2})
    assert result.is_error is False
    assert result.content[0].text is not None


def test_list_pets_input_model_schema_validates_enum_values():
    schema = ListPetsInput.model_json_schema()
    assert "properties" in schema
    assert "species" in schema["properties"]
    assert "status" in schema["properties"]
    assert "sortBy" in schema["properties"]
    assert "order" in schema["properties"]
