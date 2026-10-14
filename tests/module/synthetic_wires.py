"""Authored synthetic data only; no receipt image, human label or provider observation."""

import hashlib

from rfr.shared.docio.identity import artifact_bytes, raw_revision
from rfr.shared.docio.models import Document, ProcessingArtifact, SourceEvidence
from rfr.shared.evalkit.identity import ordered_ids_digest
from rfr.shared.rulings.identity import canonical_pair, pair_generation, pair_key

H = "a" * 64
G = "b" * 64
NOW = "2026-01-01T00:00:00Z"


def transforms():
    return {
        "source_to_engine": {
            "direction": "source_to_engine",
            "algorithm": "scale/1",
            "matrix": ((2.0, 0.0, 4.0), (0.0, 2.0, 6.0), (0.0, 0.0, 1.0)),
        },
        "engine_to_source": {
            "direction": "engine_to_source",
            "algorithm": "scale/1",
            "matrix": ((0.5, 0.0, -2.0), (0.0, 0.5, -3.0), (0.0, 0.0, 1.0)),
        },
    }


def document_fixture(*, geometry="native"):
    raw = raw_revision("collection-a:document", H)
    box = {"x0": 2.0, "y0": 3.0, "x1": 20.0, "y1": 13.0}
    word = {
        "stable_id": "word-1",
        "text": "café  Ω",
        "bbox_px": box,
        "ocr_confidence": None,
        "geometry_provenance": geometry,
        "source_engine": "synthetic-native",
        "source_engine_version": "1",
    }
    line = {**word, "stable_id": "line-1", "ordered_child_ids": ("word-1",)}
    block = {**word, "stable_id": "block-1", "ordered_child_ids": ("line-1",)}
    grid = {
        "document_id": "collection-a:document",
        "raw_source_revision": raw,
        "page_id": "page-0",
        "page_index": 0,
        "width_px": 100,
        "height_px": 80,
        "page_sha256": G,
        "grid_policy_id": "synthetic-grid/1",
        "words": (word,),
        "lines": (line,),
        "blocks": (block,),
    }
    artifact = ProcessingArtifact.model_validate(
        {
            **grid,
            "artifact_id": "artifact-1",
            "engine": "synthetic-native",
            "engine_version": "1",
            "config_digest": H,
            **transforms(),
        }
    )
    document = Document.model_validate(
        {
            "document_id": grid["document_id"],
            "original_content_sha256": H,
            "raw_source_revision": raw,
            "source_kind": "native_text",
            "pages": ({**grid, "source_kind": "native_text", "processing_ref": "artifact-1"},),
            "provenance": {
                "producer": "synthetic",
                "version": "1",
                "config_sha256": H,
                "source_grid_profile": "synthetic-grid/1",
            },
        }
    )
    retained = artifact_bytes(artifact)
    ref = SourceEvidence.model_validate(
        {
            key: grid[key]
            for key in (
                "document_id",
                "raw_source_revision",
                "page_id",
                "page_index",
                "page_sha256",
                "width_px",
                "height_px",
                "grid_policy_id",
            )
        }
        | {
            "original_content_sha256": H,
            "evidence_artifact_sha256": hashlib.sha256(retained).hexdigest(),
            "bbox_px": box,
            "word_ids": None,
            "line_ids": ("line-1",),
            "excerpt_sha256": hashlib.sha256(word["text"].encode()).hexdigest(),
            "transform_ref": None,
        }
    )
    return document, artifact, retained, ref


def scalar_intent():
    return {
        "event_id": "event-1",
        "namespace": "synthetic-annotations",
        "subject": {"kind": "field", "item_id": "posting:opaque-1", "field_id": "supported"},
        "generation_identity": {
            "kind": "scalar",
            "profile": "fixture-scalar/1",
            "source_sha256": H,
            "raw_source_revision": "raw-1",
            "evidence_revision": "evidence-1",
        },
        "event_kind": "scalar_decision",
        "payload": {
            "action": "correct",
            "old_value": False,
            "new_value": True,
            "issue_dispositions": (),
        },
        "expected_source_revision": "raw-1",
        "expected_evidence_revision": "evidence-1",
        "expected_prior_event_id": None,
        "actor_label": "fixture-agent",
        "actor_provenance": "agent_provisional",
        "actor_provenance_ref": None,
        "at_utc": NOW,
        "reason": "synthetic conformance",
        "context_refs": (),
    }


def pair_intent():
    refs = canonical_pair(
        ({"dataset_id": "left", "record_id": "123"}, {"dataset_id": "right", "record_id": "123"})
    )
    key = pair_key(refs)
    generation = pair_generation(key, (H, G))
    return scalar_intent() | {
        "subject": {"kind": "pair", "pair_key": key, "refs": refs},
        "generation_identity": {
            "kind": "pair",
            "profile": "product-raw-fields-v1",
            "pair_generation": generation,
            "raw_fingerprints": (H, G),
        },
        "event_kind": "pair_decision",
        "payload": {"action": "decide", "verdict": "unsure"},
        "expected_source_revision": generation,
        "expected_evidence_revision": None,
    }


def projection_policy():
    return {
        "mode": "aggregate_only",
        "allowed_dimensions": ("method", "dataset_alias"),
        "allowed_value_sets": {"method": ("baseline",), "dataset_alias": ("synthetic",)},
        "allowed_numeric_metrics": ("value", "eligible_N"),
        "synthetic_example_refs": (),
    }


def manifest_wire():
    ids = ("case:1", "case:2")
    pinned = {"status": "available", "ref": "fixture", "sha256": H}
    return {
        "manifest_id": "synthetic-manifest",
        "parent_manifest_sha256": None,
        "split_seed": None,
        "partition_provenance": "published_canonical",
        "frozen_at": NOW,
        "scorer_version": "fixture/1",
        "comparator_config": pinned,
        "domain_adapter_ref": pinned,
        "experiment_refs": {"gold": pinned},
        "splits": (
            {
                "split": "dev",
                "items_file": "gold/dev.jsonl",
                "item_count": 2,
                "ordered_item_ids": ids,
                "items_sha256": G,
                "ordered_ids_sha256": ordered_ids_digest(ids),
                "group_ids": ("group:1", "group:2"),
            },
        ),
        "group_split_map": {"group:1": "dev", "group:2": "dev"},
        "group_members": {"group:1": ("case:1", "asset:1"), "group:2": ("case:2",)},
        "source_artifacts": (
            {
                "namespace": "fixture",
                "status": "available",
                "sha256": H,
                "count": 2,
                "member_ids": ids,
            },
        ),
        "publication_policy": projection_policy(),
        "run_history_ref": "history:fixture",
    }


def gold_wire():
    return {
        "item_id": "case:1",
        "dataset": "synthetic",
        "group_id": "group:1",
        "split": "dev",
        "label_version": "fixture/1",
        "source_ref": {"handle": "private:1", "sha256": H},
        "input_sha256": H,
        "label_source": "human_corrected",
        "label_provenance_ref": "fixture-only",
        "domain_kind": "classification",
        "label_payload": {
            "kind": "field_labels",
            "labels": {"supported": {"presence": "present", "value": False}},
        },
    }


def prediction_wire():
    return {
        "item_id": "case:1",
        "method": "baseline",
        "method_version": "fixture/1",
        "config_sha256": H,
        "model": None,
        "origin": "synthetic",
        "status": "ok",
        "domain_payload": {"supported": False},
        "machine_output": False,
        "human_effective_output": True,
        "human_provenance_ref": "fixture-only",
        "issues": (),
        "ledger_refs": (),
        "source_refs": (),
    }


def metric_wire():
    return {
        "dataset_alias": "synthetic",
        "split": "dev",
        "method": "baseline",
        "config_ref": "fixture",
        "field": None,
        "class_name": None,
        "metric": "accuracy",
        "statistic_version": "fixture/1",
        "measurement_status": "measured",
        "numerator": 3.0,
        "denominator": 6.0,
        "confusion_counts": None,
        "supports": {"labelled": 6},
        "corpus_N": 7,
        "eligible_N": 6,
        "answered_N": 5,
        "comparable_N": 6,
        "error_N": 1,
        "abstention_N": 0,
        "stale_N": 0,
        "value": 0.5,
        "null_reason": None,
        "interval": None,
        "evidence_origin": "synthetic",
    }
