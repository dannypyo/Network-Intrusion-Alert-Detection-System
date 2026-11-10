"""Pydantic models for the agent report contract.

These models are the source of truth for the report format. FastAPI checks
every POST /report body against Report and answers 422 naming the bad field.
"""

from collections import Counter
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, IPvAnyAddress, model_validator

# Numbers, booleans and strings are strict: "80" is not 80 and "true" is not True.
# Timestamps and IPs are left lax so they can be parsed from their JSON strings.
Count = Annotated[int, Field(strict=True, ge=0)]
Millis = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]
Text = Annotated[str, Field(strict=True, min_length=1, max_length=128)]

AGENT_ID_PATTERN = r"^[A-Za-z0-9._-]{1,64}$"
ERROR_PATTERN = r"^(timeout|refused|dns|unreachable|http_5\d\d)$"


class ContractModel(BaseModel):
    """Base for every contract model: unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")


class Traffic(ContractModel):
    bytes_in: Count
    bytes_out: Count
    packets_in: Count
    packets_out: Count
    interval_s: Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False)]


class FailedLogin(ContractModel):
    user: Text  # attacker-controlled text: escape it before displaying
    source_ip: IPvAnyAddress
    time: AwareDatetime


class ServiceCheck(ContractModel):
    name: Text
    host: Annotated[str, Field(strict=True, min_length=1, max_length=255)]
    port: Annotated[int, Field(strict=True, ge=1, le=65535)]
    up: Annotated[bool, Field(strict=True)]
    response_ms: Millis | None  # required key; null only when no response came back
    error: Annotated[str, Field(strict=True, pattern=ERROR_PATTERN)] | None = None

    @model_validator(mode="after")
    def check_consistency(self) -> "ServiceCheck":
        if self.up and self.error is not None:
            raise ValueError("error must be null when up is true")
        if self.up and self.response_ms is None:
            raise ValueError("response_ms is required when up is true")
        if not self.up and self.error is None:
            raise ValueError("error is required when up is false")
        return self


class Report(ContractModel):
    agent_id: Annotated[str, Field(strict=True, pattern=AGENT_ID_PATTERN)]
    timestamp: AwareDatetime
    traffic: Traffic
    failed_logins: Annotated[list[FailedLogin], Field(max_length=1000)]
    services: Annotated[list[ServiceCheck], Field(max_length=50)]

    @model_validator(mode="after")
    def check_unique_service_names(self) -> "Report":
        duplicates = sorted(name for name, n in Counter(s.name for s in self.services).items() if n > 1)
        if duplicates:
            raise ValueError(f"duplicate service names: {', '.join(duplicates)}")
        return self
