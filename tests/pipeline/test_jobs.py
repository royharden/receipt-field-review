"""No lost fixed-cohort failures, duplicate execution or automatic interrupted-job resumption."""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from test_review_store import decision

from rfr.pipeline.files import BatchError
from rfr.pipeline.job_models import JobRecord, JobSpec
from rfr.pipeline.jobs import JobStore, LocalB0
from rfr.pipeline.models import ReceiptBundle


def setup_job(batch, bundle_factory, *, method="B0", request="request-1", extra=None):
    bundle = bundle_factory()
    revision = batch.register(bundle, expected_revision=None)
    spec = JobSpec(
        method=method, source_revisions={bundle.document.document_id: revision, **(extra or {})}
    )
    jobs = JobStore(batch)
    record = jobs.start(request, spec)
    return bundle, jobs, record


def test_actual_local_B0_rerun_preserves_review_and_only_actual_execution_has_origin(
    batch, bundle_factory
):
    bundle, jobs, record = setup_job(batch, bundle_factory)
    assert record.execution_origin == "not_run" and record.model_cost_status == "not_run"
    view = batch.detail(bundle.document.document_id)
    batch.decide(decision(bundle, view), expected_item_revision=bundle.revision)
    result = jobs.run(record.job_id)
    assert result.state == "complete" and result.execution_origin == "local_rules"
    assert result.model_cost_usd is None and result.model_cost_status == "not_applicable"
    assert (
        batch.detail(bundle.document.document_id)["fields"]["merchant_name"]["effective_value"]
        == "Corrected Shop"
    )


def test_missing_item_retained_in_fixed_requested_cohort_and_partial_not_complete(
    batch, bundle_factory
):
    bundle, jobs, record = setup_job(batch, bundle_factory, extra={"missing-input": "a" * 64})
    result = jobs.run(record.job_id)
    assert result.state == "partial" and len(result.items) == 2
    assert result.items[bundle.document.document_id].status == "ok"
    assert result.items["missing-input"].status == "unavailable"
    assert result.items["missing-input"].result_revision is None


@pytest.mark.parametrize("method", ["J1", "V2"])
def test_unconnected_canonical_methods_are_unavailable_not_authored_success(
    batch, bundle_factory, method
):
    _, jobs, record = setup_job(batch, bundle_factory, method=method)

    class Forbidden:
        def execute(self, bundle):
            raise AssertionError("unavailable model arm cannot dispatch a local substitute")

    result = jobs.run(record.job_id, local_b0=Forbidden())
    assert result.state == "failed"
    assert {item.status for item in result.items.values()} == {"unavailable"}
    assert result.execution_origin == result.model_cost_status == "not_run"
    assert result.model_cost_usd is None


def test_exact_request_and_run_retries_do_not_execute_again_and_changed_spec_conflicts(
    batch, bundle_factory
):
    _, jobs, record = setup_job(batch, bundle_factory)

    class Counter:
        calls = 0

        def execute(self, bundle):
            self.calls += 1
            return LocalB0().execute(bundle)

    counter = Counter()
    first = jobs.run(record.job_id, local_b0=counter)
    assert jobs.start(record.request_id, record.spec) == first
    assert jobs.run(record.job_id, local_b0=counter) == first and counter.calls == 1
    with pytest.raises(BatchError, match="intent_conflict"):
        jobs.start(record.request_id, record.spec.model_copy(update={"method": "J1"}))


def test_one_active_job_and_concurrent_claim_execute_only_once(batch, bundle_factory):
    _, jobs, record = setup_job(batch, bundle_factory)
    with pytest.raises(BatchError, match="already_active"):
        jobs.start("another-request", record.spec)
    entered, release = Event(), Event()

    class Gate:
        calls = 0

        def execute(self, bundle):
            self.calls += 1
            entered.set()
            assert release.wait(5)
            return LocalB0().execute(bundle)

    gate = Gate()
    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(jobs.run, record.job_id, local_b0=gate)
        assert entered.wait(5)
        duplicate = JobStore(batch).run(record.job_id, local_b0=gate)
        assert duplicate.state == "running" and gate.calls == 1
        release.set()
        assert future.result(timeout=10).state == "complete"


def test_changed_source_before_dispatch_stays_stale_without_local_call(batch, bundle_factory):
    bundle, jobs, record = setup_job(batch, bundle_factory)
    payload = json.loads(bundle.model_dump_json())
    payload["receipt"]["fields"]["merchant_name"]["method"] = "new-source-head"
    new = ReceiptBundle.model_validate_json(json.dumps(payload))
    batch.register(new, expected_revision=bundle.revision)

    class Forbidden:
        def execute(self, bundle):
            raise AssertionError("stale input must not dispatch")

    result = jobs.run(record.job_id, local_b0=Forbidden())
    assert result.state == "failed" and next(iter(result.items.values())).status == "stale"
    assert result.execution_origin == result.model_cost_status == "not_run"


def test_source_changed_during_compute_cannot_persist_stale_result(batch, bundle_factory):
    bundle, jobs, record = setup_job(batch, bundle_factory)
    payload = json.loads(bundle.model_dump_json())
    payload["receipt"]["fields"]["merchant_name"]["method"] = "new-current-head"
    new = ReceiptBundle.model_validate_json(json.dumps(payload))

    class ConcurrentChange:
        def execute(self, captured):
            batch.register(new, expected_revision=captured.revision)
            return LocalB0().execute(captured)

    result = jobs.run(record.job_id, local_b0=ConcurrentChange())
    assert next(iter(result.items.values())).status == "stale"
    assert batch.bundle(bundle.document.document_id).revision == new.revision


def test_interrupted_worker_requires_explicit_recovery_and_never_auto_resumes(
    batch, bundle_factory
):
    _, jobs, record = setup_job(
        batch,
        bundle_factory,
        extra={"aaa-earlier-missing": "a" * 64, "zzz-later-input": "b" * 64},
    )

    class Exit:
        calls = 0

        def execute(self, bundle):
            self.calls += 1
            raise KeyboardInterrupt("synthetic process interruption boundary")

    exiting = Exit()
    with pytest.raises(KeyboardInterrupt):
        jobs.run(record.job_id, local_b0=exiting)
    assert jobs.get(record.job_id).state == "running"
    recovered = JobStore(batch).recover_interrupted(record.job_id)
    assert recovered.state == "interrupted"
    assert {item.status for item in recovered.items.values()} == {
        "unavailable",
        "unknown_interrupted",
        "not_run",
    }
    assert recovered.items["aaa-earlier-missing"].status == "unavailable"
    assert recovered.items["zzz-later-input"].status == "not_run"
    assert jobs.run(record.job_id, local_b0=exiting) == recovered and exiting.calls == 1
    assert jobs.start(record.request_id, record.spec) == recovered


def test_pending_restart_has_no_execution_and_damaged_job_bytes_are_preserved(
    batch, bundle_factory
):
    _, jobs, record = setup_job(batch, bundle_factory)
    recovered = JobStore(batch).recover_interrupted(record.job_id)
    assert recovered.execution_origin == recovered.model_cost_status == "not_run"
    assert {item.status for item in recovered.items.values()} == {"not_run"}
    path = jobs.folder / (record.job_id + ".json")
    path.write_bytes(b'{"incomplete"')
    with pytest.raises(BatchError, match="invalid_job_state"):
        jobs.get(record.job_id)
    assert path.read_bytes() == b'{"incomplete"'


@pytest.mark.parametrize("request_key", ["../outside", "a/b", "", "a" * 129])
def test_request_keys_cannot_select_paths(batch, bundle_factory, request_key):
    bundle = bundle_factory()
    revision = batch.register(bundle, expected_revision=None)
    with pytest.raises(BatchError, match="request_id"):
        JobStore(batch).start(
            request_key,
            JobSpec(method="B0", source_revisions={bundle.document.document_id: revision}),
        )


def test_changed_frozen_execution_configuration_preserves_axes_without_dispatch(
    batch, bundle_factory, monkeypatch
):
    _, jobs, record = setup_job(batch, bundle_factory)
    import rfr.pipeline.jobs as implementation

    monkeypatch.setattr(implementation, "local_execution_fingerprint", lambda: "f" * 64)

    class Forbidden:
        def execute(self, bundle):
            raise AssertionError("changed execution configuration cannot run")

    result = jobs.run(record.job_id, local_b0=Forbidden())
    assert result.state == "failed" and result.execution_origin == "not_run"
    assert set(result.items) == set(record.spec.source_revisions)
    assert {item.reason for item in result.items.values()} == {"frozen_execution_config_changed"}


def test_stored_wire_cannot_promote_unrun_model_arm_or_drop_requested_axes(batch, bundle_factory):
    bundle, jobs, record = setup_job(batch, bundle_factory, method="J1")
    payload = json.loads(record.model_dump_json())
    payload["state"] = "complete"
    payload["items"][bundle.document.document_id] = {
        "status": "ok",
        "result_revision": bundle.revision,
        "reason": None,
    }
    with pytest.raises(ValueError):
        JobRecord.model_validate_json(json.dumps(payload))
    payload["execution_origin"] = "local_rules"
    payload["model_cost_status"] = "not_applicable"
    with pytest.raises(ValueError):
        JobRecord.model_validate_json(json.dumps(payload))
    original = json.loads(record.model_dump_json())
    original["spec"]["source_revisions"]["omitted-input"] = "a" * 64
    with pytest.raises(ValueError):
        JobRecord.model_validate_json(json.dumps(original))
