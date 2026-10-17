"""Typed local operations shared by the recognized-bundle HTTP adapter and Python controls."""

from pathlib import Path

from pydantic import BaseModel

from ..export.receipt import export_receipts
from ..pipeline.commands import draft_decision
from ..pipeline.files import BatchError
from ..pipeline.store import BatchStore
from ..shared.rulings.identity import canonical_bytes
from ..shared.rulings.models import AppendReceipt, ScalarSubject
from ..shared.rulings.store import JournalStore, PriorConflict
from .models import (
    BatchSummary,
    CreateBatch,
    DecisionDraft,
    DraftRequest,
    ItemDetail,
    ItemSummary,
    RecognizedImport,
)
from .security import RequestRefused
from .source_images import SourcePage, source_page


def _wire[T: BaseModel](model: type[T], value: object) -> T:
    return model.model_validate_json(canonical_bytes(value))


def _request[T: BaseModel](model: type[T], request: T) -> T:
    if type(request) is not model:
        raise BatchError("validated_api_request_required")
    # Revalidate nested mutable mappings before the public workflow mutates durable state.
    return _wire(model, request.model_dump(mode="json"))


class ReviewOperations:
    """Trusted Python boundary; the transport must admit every request before invoking it."""

    def __init__(self, data_root: Path):
        self.data_root = Path(data_root).absolute()
        JournalStore(self.data_root)

    def _store(self, batch_id: str) -> BatchStore:
        return BatchStore(self.data_root, batch_id)

    def create(self, request: CreateBatch) -> BatchSummary:
        request = _request(CreateBatch, request)
        store = BatchStore.create(self.data_root, request.currency)
        return BatchSummary(batch_id=store.batch_id, currency=request.currency.code, item_count=0)

    def import_recognized(self, batch_id: str, request: RecognizedImport) -> str:
        request = _request(RecognizedImport, request)
        return self._store(batch_id).register(
            request.bundle, expected_revision=request.expected_revision
        )

    def items(self, batch_id: str) -> tuple[ItemSummary, ...]:
        summaries = []
        for view in self._store(batch_id).list_items():
            deleted = view.get("deleted", False)
            summaries.append(
                ItemSummary(
                    item_id=view["item_id"],
                    revision=None if deleted else view["revision"],
                    deleted=deleted,
                    clean=False if deleted else view["clean"],
                    unfinished_fields=() if deleted else tuple(view["unfinished_fields"]),
                    unresolved_issues=() if deleted else tuple(view["unresolved_issues"]),
                )
            )
        return tuple(summaries)

    def detail(self, batch_id: str, item_id: str) -> ItemDetail:
        view = self._store(batch_id).detail(item_id)
        review = {key: value for key, value in view.items() if key != "retained_artifact_base64"}
        # Missing/invalid optional source pixels must not prevent text correction/export.
        # Availability is checked against this exact review revision, never a cached filename.
        try:
            self.source_page(batch_id, item_id, view["revision"])
            available = True
        except (RequestRefused, BatchError, OSError, ValueError, PriorConflict):
            available = False
        return _wire(ItemDetail, {"review": review, "image_available": available})

    def source_page(self, batch_id: str, item_id: str, revision: str) -> SourcePage:
        return source_page(self._store(batch_id), item_id, revision)

    def draft(self, batch_id: str, item_id: str, request: DraftRequest) -> DecisionDraft:
        request = _request(DraftRequest, request)
        draft = draft_decision(self._store(batch_id), item=item_id, **request.command_arguments())
        return _wire(DecisionDraft, draft)

    def apply(self, batch_id: str, item_id: str, request: DecisionDraft) -> AppendReceipt:
        request = _request(DecisionDraft, request)
        if (
            type(request.intent.subject) is not ScalarSubject
            or request.intent.subject.item_id != item_id
        ):
            raise BatchError("decision_route_item_conflict")
        return self._store(batch_id).decide(
            request.intent, expected_item_revision=request.expected_item_revision
        )

    def delete(self, batch_id: str, item_id: str, *, expected_revision: str) -> None:
        self._store(batch_id).delete(item_id, expected_revision=expected_revision)

    def export(self, batch_id: str, *, mode: str = "review") -> dict[str, bytes]:
        # No client filesystem destination; HTTP streams only these closed outputs.
        return export_receipts(self._store(batch_id), mode=mode)
