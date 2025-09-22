from typing import Dict
from pydantic import BaseModel, Field


class NDJsonOutput(BaseModel):
    """
    Pydantic model for the final NDJSON output structure.
    This schema is derived from Table 1 in the project specification.
    """

    name: str = Field(..., description="Model/dataset/code name")
    category: str = Field(..., description="Category type [MODEL, DATASET, CODE]")
    net_score: float = Field(..., ge=0, le=1, description="Overall quality score")
    net_score_latency: int = Field(
        ..., ge=0, description="Time to compute net_score in milliseconds"
    )
    ramp_up_time: float = Field(..., ge=0, le=1, description="Ease of ramp-up")
    ramp_up_time_latency: int = Field(
        ..., ge=0, description="Time to compute ramp up time in milliseconds"
    )
    bus_factor: float = Field(
        ..., ge=0, le=1, description="Metric measuring knowledge concentration"
    )
    bus_factor_latency: int = Field(
        ..., ge=0, description="Time to compute bus_factor in milliseconds"
    )
    performance_claims: float = Field(
        ..., ge=0, le=1, description="Evidence of claims (benchmarks, evals)"
    )
    performance_claims_latency: int = Field(
        ..., ge=0, description="Time to compute claims in milliseconds"
    )
    license: float = Field(
        ..., ge=0, le=1, description="License clarity & permissiveness"
    )
    license_latency: int = Field(
        ..., ge=0, description="Time to compute license info in milliseconds"
    )
    size_score: Dict[str, float] = Field(
        ..., description="Dictionary mapping hardware types to size compatibility scores (0-1)"
    )
    size_score_latency: int = Field(
        ..., ge=0, description="Time to compute size score in milliseconds"
    )
    dataset_and_code_score: float = Field(
        ...,
        ge=0,
        le=1,
        description="Score for documentation of dataset and example code",
    )
    dataset_and_code_score_latency: int = Field(
        ..., ge=0, description="Time to compute availability score in milliseconds"
    )
    dataset_quality: float = Field(..., ge=0, le=1, description="Dataset quality")
    dataset_quality_latency: int = Field(
        ..., ge=0, description="Time to compute dataset quality in milliseconds"
    )
    code_quality: float = Field(
        ..., ge=0, le=1, description="Code style, maintainability"
    )
    code_quality_latency: int = Field(
        ..., ge=0, description="Time to compute code quality in milliseconds"
    )

