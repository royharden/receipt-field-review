"""Explicit trusted per-axis raw-machine status binding; digests are causality, not authority."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from pydantic import TypeAdapter

from .identity import canonical_bytes
from .models import OpaqueId, Prediction, Sha256, Status


@dataclass(frozen=True)
class AxisStatus:
    field: str | None
    class_name: str | None
    status: Status

    def __post_init__(self):
        for value in (self.field, self.class_name):
            if value is not None:
                TypeAdapter(OpaqueId, config={"strict": True}).validate_python(value)
        TypeAdapter(Status, config={"strict": True}).validate_python(self.status)
        if self.status == "not_run":
            raise ValueError("per_axis_not_run_not_admitted")


@dataclass(frozen=True)
class AxisStatusBinding:
    prediction_sha256: str
    raw_machine_sha256: str
    axes: tuple[AxisStatus, ...]

    def __post_init__(self):
        for value in (self.prediction_sha256, self.raw_machine_sha256):
            TypeAdapter(Sha256, config={"strict": True}).validate_python(value)
        if (
            type(self.axes) is not tuple
            or not self.axes
            or any(type(a) is not AxisStatus for a in self.axes)
        ):
            raise ValueError("explicit_axis_status_tuple_required")
        keys = [(axis.field, axis.class_name) for axis in self.axes]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate_axis_status_binding")


class AxisStatusPort(Protocol):
    """Trusted consumer derives ALL frozen domain axes from validated actual raw/controller output.

    It must not select successful fields, use Gold/correctness/human labels or run model effects.
    Its complete schema/profile authority requires actual consumer implementation/conformance proof;
    a valid binding object or matching SHA alone does not establish that authority.
    """

    def bind(self, prediction: Prediction) -> AxisStatusBinding: ...


def prediction_digest(prediction: Prediction) -> str:
    return hashlib.sha256(canonical_bytes(prediction.model_dump(mode="json"))).hexdigest()


def raw_machine_digest(prediction: Prediction) -> str:
    return hashlib.sha256(
        canonical_bytes(
            {
                "domain_payload": prediction.domain_payload,
                "machine_output": prediction.machine_output,
            }
        )
    ).hexdigest()


def validate_binding(
    binding: AxisStatusBinding, prediction: Prediction
) -> dict[tuple[str | None, str | None], Status]:
    if type(binding) is not AxisStatusBinding:
        raise ValueError("axis_status_binding_required")
    # Revalidate even if an injected caller bypassed dataclass construction/frozen attributes.
    checked = AxisStatusBinding(
        binding.prediction_sha256,
        binding.raw_machine_sha256,
        tuple(AxisStatus(axis.field, axis.class_name, axis.status) for axis in binding.axes),
    )
    if checked.prediction_sha256 != prediction_digest(
        prediction
    ) or checked.raw_machine_sha256 != raw_machine_digest(prediction):
        raise ValueError("axis_status_response_binding_mismatch")
    return {(axis.field, axis.class_name): axis.status for axis in checked.axes}
