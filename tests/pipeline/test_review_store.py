"""Catch lost/stale decisions, false clean exports and untrusted source-file authority."""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from rfr.pipeline.files import BatchError, atomic
from rfr.pipeline.models import BatchManifest, ReceiptBundle
from rfr.pipeline.review import NAMESPACE, subject
from rfr.pipeline.store import BatchStore
from rfr.shared.rulings.identity import canonical_bytes
from rfr.shared.rulings.models import RulingIntent, ScalarPayload
from rfr.shared.rulings.store import GenerationConflict, JournalReadOnly, PriorConflict


def decision(
    bundle,
    view,
    fid="merchant_name",
    *,
    event="e1",
    action="correct",
    new="Corrected Shop",
    issues=(),
):
    field = view["fields"][fid]
    return RulingIntent(
        event_id=event,
        namespace=NAMESPACE,
        subject=subject(bundle.document.document_id, fid),
        generation_identity=bundle.generation,
        event_kind="scalar_decision",
        payload=ScalarPayload(
            action=action,
            old_value=field["decision_old_value"],
            new_value=new,
            issue_dispositions=issues,
        ),
        expected_source_revision=bundle.document.raw_source_revision,
        expected_evidence_revision=bundle.generation.evidence_revision,
        expected_prior_event_id=field["head_event_id"],
        actor_label="synthetic implementation controller",
        actor_provenance="agent_provisional",
        actor_provenance_ref=None,
        at_utc="2026-10-15T00:00:00Z",
        reason="Literal workflow control, no human label authenticity claim",
        context_refs=(),
    )


def test_restart_rerun_preserves_correction_and_raw_machine_confidence(batch, bundle_factory):
    bundle = bundle_factory()
    revision = batch.register(bundle, expected_revision=None)
    view = batch.detail(bundle.document.document_id)
    assert view["clean"] is False and view["fields"]["merchant_name"]["effective_value"] is None
    intent = decision(bundle, view)
    receipt = batch.decide(intent, expected_item_revision=revision)
    restarted = BatchStore(batch.data_root, batch.batch_id)
    assert restarted.register(bundle, expected_revision=revision) == revision
    current = restarted.detail(bundle.document.document_id)
    field = current["fields"]["merchant_name"]
    assert field["effective_value"] == "Corrected Shop" and field["review_state"] == "correct"
    assert field["machine"] == bundle.receipt.fields["merchant_name"].model_dump(mode="json")
    assert field["label"]["label_source"] == "agent_provisional"
    retry = restarted.decide(intent, expected_item_revision="irrelevant-on-exact-retry")
    assert (
        retry.event_id == receipt.event_id and retry.historical and retry.outcome == "exact_retry"
    )


def test_changed_evidence_conflict_and_historical_retry_do_not_revive_decision(
    batch, bundle_factory
):
    before = bundle_factory()
    revision = batch.register(before, expected_revision=None)
    intent = decision(before, batch.detail(before.document.document_id))
    batch.decide(intent, expected_item_revision=revision)
    after = bundle_factory(["Merchant: DIFFERENT SHOP", "TOTAL 3.00", "CURRENCY USD"])
    newer = batch.register(after, expected_revision=revision)
    view = batch.detail(after.document.document_id)
    assert newer != revision and view["fields"]["merchant_name"]["effective_value"] is None
    assert view["fields"]["merchant_name"]["conflict"] == "generation_changed"
    retry = batch.decide(intent, expected_item_revision=revision)
    assert (
        retry.historical
        and batch.detail(after.document.document_id)["fields"]["merchant_name"]["effective_value"]
        is None
    )
    stale = intent.model_copy(update={"event_id": "stale-new"})
    with pytest.raises((GenerationConflict, PriorConflict)):
        batch.decide(stale, expected_item_revision=revision)


def test_two_stale_tabs_one_wins_and_reopen_is_barrier(batch, bundle_factory):
    bundle = bundle_factory()
    revision = batch.register(bundle, expected_revision=None)
    view = batch.detail(bundle.document.document_id)
    first, second = decision(bundle, view), decision(bundle, view, event="e2", new="Other Shop")

    def attempt(intent):
        store = BatchStore(batch.data_root, batch.batch_id)
        try:
            return store.decide(intent, expected_item_revision=revision).outcome
        except PriorConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, (first, second)))
    assert sorted(results) == ["appended", "conflict"]
    current = batch.detail(bundle.document.document_id)
    reopen = decision(bundle, current, event="reopen", action="reopen", new=None)
    batch.decide(reopen, expected_item_revision=revision)
    restarted = BatchStore(batch.data_root, batch.batch_id).detail(bundle.document.document_id)
    assert restarted["fields"]["merchant_name"]["effective_value"] is None
    assert restarted["fields"]["merchant_name"]["conflict"] == "reopened"


def test_delete_retains_history_and_retry_but_refuses_new_decision(batch, bundle_factory):
    bundle = bundle_factory()
    revision = batch.register(bundle, expected_revision=None)
    intent = decision(bundle, batch.detail(bundle.document.document_id))
    batch.decide(intent, expected_item_revision=revision)
    batch.delete(bundle.document.document_id, expected_revision=revision)
    assert batch.list_items() == [{"item_id": bundle.document.document_id, "deleted": True}]
    assert batch.decide(intent, expected_item_revision=revision).historical
    with pytest.raises((GenerationConflict, PriorConflict)):
        batch.decide(intent.model_copy(update={"event_id": "new"}), expected_item_revision=revision)


def test_tombstoned_identity_cannot_resurrect_earlier_corrections(batch, bundle_factory):
    bundle = bundle_factory()
    revision = batch.register(bundle, expected_revision=None)
    batch.decide(
        decision(bundle, batch.detail(bundle.document.document_id)), expected_item_revision=revision
    )
    batch.delete(bundle.document.document_id, expected_revision=revision)
    with pytest.raises(BatchError, match="deleted_item"):
        batch.register(bundle, expected_revision=None)


def test_printed_future_date_can_be_reviewed_without_becoming_a_pass(batch, bundle_factory):
    bundle = bundle_factory()
    revision = batch.register(bundle, expected_revision=None)
    view = batch.detail(bundle.document.document_id)
    intent = decision(bundle, view, "date", new="2030-01-01")
    batch.decide(intent, expected_item_revision=revision)
    view = batch.detail(bundle.document.document_id)
    assert view["fields"]["date"]["effective_value"] == "2030-01-01"
    assert any(
        c["check_id"] == "valid_nonfuture_date" and c["status"] == "fail" for c in view["checks"]
    )
    assert any(
        issue.startswith("check:valid_nonfuture_date:") for issue in view["unresolved_issues"]
    )


def test_corrupt_tail_and_bundle_fail_closed_without_repair(batch, bundle_factory):
    bundle = bundle_factory()
    revision = batch.register(bundle, expected_revision=None)
    intent = decision(bundle, batch.detail(bundle.document.document_id))
    batch.journal.path.write_bytes(b'{"incomplete"')
    damaged = batch.journal.path.read_bytes()
    assert batch.detail(bundle.document.document_id)["clean"] is False
    with pytest.raises(JournalReadOnly):
        batch.decide(intent, expected_item_revision=revision)
    assert batch.journal.path.read_bytes() == damaged
    with pytest.raises(BatchError, match="journal_not_clean"):
        batch.register(bundle, expected_revision=revision)
    path = batch.root / "runs" / (revision + ".json")
    path.write_bytes(b"{}")
    with pytest.raises(BatchError, match="digest_conflict"):
        batch.bundle(bundle.document.document_id)


def test_foreign_artifact_mixed_currency_and_capacity_guards(batch, bundle_factory):
    bundle = bundle_factory()
    payload = json.loads(bundle.model_dump_json())
    payload["artifact_base64"] = "e30="
    with pytest.raises(ValueError):
        ReceiptBundle.model_validate_json(json.dumps(payload))
    payload = json.loads(bundle.model_dump_json())
    payload["receipt"]["context"]["currency"]["code"] = "EUR"
    other_currency = ReceiptBundle.model_validate_json(json.dumps(payload))
    with pytest.raises(BatchError, match="mixed_currency"):
        batch.register(other_currency, expected_revision=None)
    # Literal typed manifest boundary only, not101 executed receipt imports.
    manifest = BatchManifest(
        batch_id=batch.batch_id,
        currency=bundle.receipt.context.currency,
        items={f"old-{n}": None for n in range(100)},
    )
    atomic(batch.root / "manifest.json", canonical_bytes(manifest.model_dump(mode="json")))
    with pytest.raises(BatchError, match="item_limit"):
        batch.register(bundle, expected_revision=None)
    with pytest.raises(ValueError):
        BatchManifest(
            batch_id=batch.batch_id,
            currency=manifest.currency,
            items={f"old-{n}": None for n in range(101)},
        )


def test_method_only_rerun_preserves_review_but_old_ui_revision_refuses_new_write(
    batch, bundle_factory
):
    bundle = bundle_factory()
    first = batch.register(bundle, expected_revision=None)
    intent = decision(bundle, batch.detail(bundle.document.document_id))
    batch.decide(intent, expected_item_revision=first)
    data = json.loads(bundle.model_dump_json())
    data["receipt"]["fields"]["merchant_name"]["method"] = "B0-same-evidence-rerun"
    rerun = ReceiptBundle.model_validate_json(json.dumps(data))
    assert rerun.generation == bundle.generation
    second = batch.register(rerun, expected_revision=first)
    assert second != first
    view = batch.detail(bundle.document.document_id)
    assert view["fields"]["merchant_name"]["effective_value"] == "Corrected Shop"
    with pytest.raises(GenerationConflict):
        batch.decide(decision(rerun, view, event="stale-tab"), expected_item_revision=first)


def test_context_change_invalidates_current_review_and_manifest_damage_stays_closed(
    batch, bundle_factory
):
    bundle = bundle_factory()
    first = batch.register(bundle, expected_revision=None)
    batch.decide(
        decision(bundle, batch.detail(bundle.document.document_id)), expected_item_revision=first
    )
    data = json.loads(bundle.model_dump_json())
    data["receipt"]["context"]["reference_date"] = "2026-10-15"
    changed = ReceiptBundle.model_validate_json(json.dumps(data))
    batch.register(changed, expected_revision=first)
    assert (
        batch.detail(bundle.document.document_id)["fields"]["merchant_name"]["effective_value"]
        is None
    )
    manifest = batch.root / "manifest.json"
    manifest.write_bytes(b"{bad")
    with pytest.raises(BatchError, match="invalid_batch_manifest"):
        batch.list_items()
    assert manifest.read_bytes() == b"{bad"


def test_wrong_old_value_is_refused_without_journal_effect(batch, bundle_factory):
    bundle = bundle_factory()
    revision = batch.register(bundle, expected_revision=None)
    intent = decision(bundle, batch.detail(bundle.document.document_id))
    intent = intent.model_copy(
        update={"payload": intent.payload.model_copy(update={"old_value": "wrong"})}
    )
    with pytest.raises(PriorConflict, match="field_value"):
        batch.decide(intent, expected_item_revision=revision)
    assert not batch.journal.path.exists()


def test_actual_two_native_processes_cannot_overwrite_same_head(batch, bundle_factory, tmp_path):
    bundle = bundle_factory()
    revision = batch.register(bundle, expected_revision=None)
    view = batch.detail(bundle.document.document_id)
    intents = [
        decision(bundle, view),
        decision(bundle, view, event="other-process", new="Other Shop"),
    ]
    script = """
import pathlib,socket,sys
from rfr.pipeline.store import BatchStore
from rfr.shared.rulings.models import RulingIntent
from rfr.shared.rulings.store import PriorConflict
def denied(*a,**k):raise RuntimeError('native workflow control network forbidden')
socket.create_connection=denied;socket.socket.connect=denied
store=BatchStore(pathlib.Path(sys.argv[1]),sys.argv[2])
intent=RulingIntent.model_validate_json(pathlib.Path(sys.argv[4]).read_bytes())
try: print(store.decide(intent,expected_item_revision=sys.argv[3]).outcome)
except PriorConflict: print('conflict')
"""
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src")}
    processes = []
    for index, intent in enumerate(intents):
        path = tmp_path / f"intent-{index}.json"
        path.write_text(intent.model_dump_json())
        processes.append(
            subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    script,
                    str(batch.data_root),
                    batch.batch_id,
                    revision,
                    str(path),
                ],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        )
    results = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=20)
        assert process.returncode == 0, stderr
        results.append(stdout.strip())
    assert sorted(results) == ["appended", "conflict"]
    assert len(batch.journal.replay().events) == 1


@pytest.mark.parametrize("batch_id", ["../x", "a/b", "C:\\outside", "", "0" * 31])
def test_batch_ids_cannot_select_paths(tmp_path, batch_id):
    with pytest.raises(BatchError, match="invalid_batch_id"):
        BatchStore(tmp_path, batch_id)
