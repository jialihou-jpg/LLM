from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pet_hospital_mcp.errors import AppError, BackendInvalidResponseError, ValidationError
from pet_hospital_mcp.rest_client import PetHospitalRestClient

Species = Literal["犬", "猫", "兔", "鸟", "爬宠", "鱼", "其他"]
Status = Literal["待就诊", "就诊中", "住院中", "已康复", "慢性病随访"]
SortBy = Literal["id", "name", "ownerName", "totalCost", "visitCount", "status", "species", "doctor"]
Order = Literal["asc", "desc"]


class ListPetsInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    q: str | None = None
    name: str | None = None
    ownerName: str | None = None
    ownerPhone: str | None = None
    species: Species | None = None
    doctor: str | None = None
    disease: str | None = None
    status: Status | None = None
    min: float | None = Field(default=None, ge=0)
    max: float | None = Field(default=None, ge=0)
    sortBy: SortBy | None = None
    order: Order | None = None
    page: int = Field(default=1, ge=1)
    pageSize: int = Field(default=20, ge=1, le=500)

    @field_validator("min", "max")
    @classmethod
    def reject_non_finite_values(cls, value: float | None) -> float | None:
        if value is None:
            return value
        if not math.isfinite(value):
            raise ValueError("must be finite")
        return value

    @model_validator(mode="after")
    def validate_min_max(self) -> "ListPetsInput":
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("min cannot be greater than max")
        return self


class ListPetsSuccess(BaseModel):
    items: list[dict[str, Any]] = []
    total: int = 0
    page: int = 1
    pageSize: int = 20
    totalPages: int = 0
    totalCost: float | int | None = None


class ToolErrorOutput(BaseModel):
    error: dict[str, Any]


class ListPetsTool:
    def __init__(self, client: PetHospitalRestClient):
        self.client = client

    async def __call__(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            dto = ListPetsInput.model_validate(params)
        except Exception as exc:  # noqa: BLE001
            raise ValidationError("Invalid tool parameters", {"reason": str(exc)}) from exc

        payload = dto.model_dump(exclude_none=True)
        response = await self.client.get("/api/v1/pets", params=payload)

        if "data" not in response or not isinstance(response["data"], dict):
            raise BackendInvalidResponseError("Backend response did not include a data object")

        data = response["data"]
        normalized = ListPetsSuccess.model_validate(
            {
                "items": data.get("items") if isinstance(data.get("items"), list) else [],
                "total": data.get("total", 0),
                "page": data.get("page", 1),
                "pageSize": data.get("pageSize", 20),
                "totalPages": data.get("totalPages", 0),
                "totalCost": data.get("totalCost"),
            }
        )
        return normalized.model_dump()
