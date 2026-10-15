"""Files are authoritative for source heads; JSONL is authoritative for decisions."""

import hashlib
import re
import uuid
from pathlib import Path

from ..shared.rulings.identity import canonical_bytes
from ..shared.rulings.models import RulingIntent, ScalarPayload, ScalarSubject
from ..shared.rulings.store import GenerationConflict, JournalStore, PriorConflict
from .files import BatchError, atomic, batch_mutex, immutable, plain, read
from .models import BatchManifest, ReceiptBundle
from .review import NAMESPACE, normalized_value, review_item


class BatchStore:
    def __init__(self, data_root: Path, batch_id: str):
        if type(batch_id) is not str or not re.fullmatch(r"[0-9a-f]{32}", batch_id):
            raise BatchError("invalid_batch_id")
        self.data_root = Path(data_root).absolute()
        # Public journal constructor checks trusted local root and every ancestor/reparse component.
        JournalStore(self.data_root)
        self.root = self.data_root / batch_id
        self.journal = JournalStore(self.root)
        self.batch_id = batch_id

    @classmethod
    def create(cls, data_root, currency):
        root = Path(data_root).absolute()
        JournalStore(root)
        batch_id = uuid.uuid4().hex
        folder = root / batch_id
        folder.mkdir(mode=0o700)
        for name in ("runs", "pages", "ocr"):
            (folder / name).mkdir(mode=0o700)
        manifest = BatchManifest(batch_id=batch_id, currency=currency, items={})
        atomic(folder / "manifest.json", canonical_bytes(manifest.model_dump(mode="json")))
        return cls(root, batch_id)

    def _manifest(self):
        try:
            manifest = BatchManifest.model_validate_json(
                read(self.root / "manifest.json", 1024 * 1024)
            )
        except ValueError:
            raise BatchError("invalid_batch_manifest") from None
        if manifest.batch_id != self.batch_id:
            raise BatchError("batch_manifest_identity_conflict")
        return manifest

    def _bundle(self, manifest, item_id):
        revision = manifest.items.get(item_id)
        if revision is None:
            raise BatchError("item_missing_or_deleted")
        directory = self.root / "runs"
        plain(directory, directory=True)
        raw = read(directory / (revision + ".json"), 8 * 1024 * 1024)
        if hashlib.sha256(raw).hexdigest() != revision:
            raise BatchError("immutable_bundle_digest_conflict")
        try:
            bundle = ReceiptBundle.model_validate_json(raw)
        except ValueError:
            raise BatchError("invalid_retained_bundle") from None
        if bundle.document.document_id != item_id or bundle.revision != revision:
            raise BatchError("immutable_bundle_identity_conflict")
        return bundle

    def register(self, bundle: ReceiptBundle, *, expected_revision: str | None):
        if type(bundle) is not ReceiptBundle:
            raise BatchError("validated_receipt_bundle_required")
        raw = canonical_bytes(bundle.model_dump(mode="json"))
        if len(raw) > 8 * 1024 * 1024:
            raise BatchError("receipt_bundle_limit")
        # Revalidate mutable nested mappings before persistence.
        bundle = ReceiptBundle.model_validate_json(raw)
        with batch_mutex(self.root):
            manifest = self._manifest()
            item = bundle.document.document_id
            if item in manifest.items and manifest.items[item] is None:
                raise BatchError("deleted_item_requires_new_identity")
            if manifest.items.get(item) != expected_revision:
                raise PriorConflict("item_revision_conflict")
            if bundle.receipt.context.currency != manifest.currency:
                raise BatchError("mixed_currency_batch")
            if item not in manifest.items and len(manifest.items) >= 100:
                raise BatchError("batch_item_limit")
            if not self.journal.replay().can_append:
                raise BatchError("journal_not_clean")
            directory = self.root / "runs"
            plain(directory, directory=True)
            immutable(directory / (bundle.revision + ".json"), raw)
            items = dict(manifest.items)
            items[item] = bundle.revision
            updated = BatchManifest(batch_id=self.batch_id, currency=manifest.currency, items=items)
            atomic(self.root / "manifest.json", canonical_bytes(updated.model_dump(mode="json")))
            return bundle.revision

    def detail(self, item_id):
        with batch_mutex(self.root):
            bundle = self._bundle(self._manifest(), item_id)
            return review_item(bundle, self.journal.replay())

    def list_items(self):
        with batch_mutex(self.root):
            manifest, snapshot = self._manifest(), self.journal.replay()
            return [
                {"item_id": item, "deleted": True}
                if revision is None
                else review_item(self._bundle(manifest, item), snapshot)
                for item, revision in manifest.items.items()
            ]

    def bundle(self, item_id):
        with batch_mutex(self.root):
            return self._bundle(self._manifest(), item_id)

    def delete(self, item_id, *, expected_revision):
        with batch_mutex(self.root):
            manifest = self._manifest()
            if manifest.items.get(item_id) != expected_revision or expected_revision is None:
                raise PriorConflict("item_revision_conflict")
            items = dict(manifest.items)
            items[item_id] = None
            updated = BatchManifest(batch_id=self.batch_id, currency=manifest.currency, items=items)
            atomic(self.root / "manifest.json", canonical_bytes(updated.model_dump(mode="json")))

    def decide(self, intent: RulingIntent, *, expected_item_revision: str):
        if (
            type(intent) is not RulingIntent
            or intent.namespace != NAMESPACE
            or type(intent.subject) is not ScalarSubject
            or type(intent.payload) is not ScalarPayload
            or not intent.reason.strip()
            or len(intent.reason.encode("utf-8")) > 4096
            or any(not issue.reason.strip() for issue in intent.payload.issue_dispositions)
        ):
            raise BatchError("invalid_receipt_decision")
        with batch_mutex(self.root):
            owner = self

            # Capture before append, while the batch mutex freezes all app source/head mutations.
            # Generation validation never reenters the public journal lock.
            snapshot = self.journal.replay()
            manifest = self._manifest()

            class Validator:
                def validate(self, subject, generation):
                    bundle = owner._bundle(manifest, subject.item_id)
                    if bundle.revision != expected_item_revision or generation != bundle.generation:
                        raise GenerationConflict("current_receipt_generation_conflict")
                    if subject.row_key is not None:
                        raise BatchError("row_identity_is_bound_in_field_id")
                    view = review_item(bundle, snapshot)
                    field = view["fields"].get(subject.field_id)
                    if field is None:
                        raise BatchError("unknown_receipt_field")
                    if canonical_bytes(field["decision_old_value"]) != canonical_bytes(
                        intent.payload.old_value
                    ):
                        raise PriorConflict("current_field_value_conflict")
                    if intent.payload.action in {"correct", "confirm"}:
                        value = normalized_value(
                            subject.field_id, intent.payload.new_value, bundle.receipt.context
                        )
                        if canonical_bytes(value) != canonical_bytes(intent.payload.new_value):
                            raise BatchError("canonical_review_value_required")
                    if any(
                        issue.issue_id not in view["issue_ids"]
                        for issue in intent.payload.issue_dispositions
                    ):
                        raise BatchError("unknown_current_issue")

            return self.journal.append(intent, Validator())
