"""Immutable runtime repository for the destructive retention redesign.

This module owns every durable runtime record.  It intentionally does not read
legacy ``state.json``, fixed output filenames, workspace configuration, or a
live Canon store.  The only mutable file it permits is a rebuildable cache,
which is deliberately outside this module's write path.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import sys
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from novel_forge.pnca.contracts import (
    AcceptanceCommit,
    FrontierBinding,
    OperationRecord,
    SeriesAcceptanceCommit,
    VolumeAcceptanceCommit,
)

FORMAT_VERSION = 1
_DIR_MODE = 0o700
_FILE_MODE = 0o600
_SECRET_KEY = re.compile(
    r"(?:authorization|proxy-authorization|api[_-]?key|token|password|secret|connection[_-]?string)",
    re.IGNORECASE,
)
_INLINE_AUTHORIZATION = re.compile(
    r"\b(?:proxy-)?authorization\s*[:=]\s*(?:bearer|basic)\s+[^\s,;]+",
    re.IGNORECASE,
)
_INLINE_SECRET = re.compile(
    r"\b(?:api[_-]?key|token|password|secret|connection[_-]?string)\s*[:=]\s*[^\s,;]+",
    re.IGNORECASE,
)


class RuntimeContractError(RuntimeError):
    """A durable runtime contract has been violated."""


class CorruptArtifactError(RuntimeContractError):
    """A ready marker, artifact, or selection snapshot failed verification."""


class LockHeldError(RuntimeContractError):
    """A side-effecting command already owns the requested scope."""


class SeriesSlugExistsError(RuntimeContractError):
    code = "SERIES_SLUG_EXISTS"

    def __init__(self, slug: str) -> None:
        super().__init__(f"{self.code}: series slug already exists: {slug}")


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def digest_bytes(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest_json(value: Any) -> str:
    return digest_bytes(canonical_json(value))


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _mkdir_private(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=_DIR_MODE)
    os.chmod(path, _DIR_MODE)


def _safe_relative(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise RuntimeContractError(f"unsafe artifact relative path: {value}")
    return path


def sanitize_for_storage(value: Any) -> Any:
    """Redact credentials and remove Ollama thinking recursively before writes."""
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered == "thinking" or (lowered == "message" and isinstance(item, dict)):
                if lowered == "thinking":
                    continue
                result[str(key)] = sanitize_for_storage(item)
            elif _SECRET_KEY.search(str(key)):
                result[str(key)] = "[REDACTED]"
            else:
                result[str(key)] = sanitize_for_storage(item)
        return result
    if isinstance(value, list):
        return [sanitize_for_storage(item) for item in value]
    if isinstance(value, str):
        parts = urlsplit(value)
        if parts.query:
            query = [
                (key, "[REDACTED]" if _SECRET_KEY.search(key) else item)
                for key, item in parse_qsl(parts.query, keep_blank_values=True)
            ]
            value = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
        value = _INLINE_AUTHORIZATION.sub("Authorization: [REDACTED]", value)
        return _INLINE_SECRET.sub("[REDACTED]", value)
    return value


class VersionedRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format_version: int = FORMAT_VERSION
    record_type: str

    @field_validator("format_version")
    @classmethod
    def _known_format_version(cls, value: int) -> int:
        if value != FORMAT_VERSION:
            raise ValueError(f"unsupported format_version: {value}")
        return value


class RunManifest(VersionedRecord):
    record_type: Literal["run"] = "run"
    run_id: str
    command: str
    workspace: str
    input_snapshot_id: str | None
    input_kind: Literal["bootstrap", "selection_snapshot"]
    started_at: str
    verbose: bool
    model: str

    @model_validator(mode="after")
    def _bootstrap_rule(self) -> RunManifest:
        if (self.input_kind == "bootstrap") != (self.input_snapshot_id is None):
            raise ValueError("bootstrap is the only run type that may have a null input snapshot")
        if self.input_kind == "bootstrap" and self.command != "plan":
            raise ValueError("only plan may start a bootstrap run")
        return self


class AttemptManifest(VersionedRecord):
    record_type: Literal["attempt"] = "attempt"
    attempt_id: str
    run_id: str
    task_id: str
    phase: str
    model: str
    seed: int | None = None
    reason: str
    retry_number: int = Field(ge=1)
    started_at: str


class ArtifactManifest(VersionedRecord):
    record_type: Literal["artifact_manifest"] = "artifact_manifest"
    artifact_id: str
    artifact_type: str
    logical_key: str
    payload_path: str
    content_digest: str
    input_artifact_ids: tuple[str, ...] = ()
    prompt_digest: str | None = None
    schema_digest: str | None = None
    canon_lineage_root_digest: str | None = None
    input_canon_frontier_digest: str | None = None
    parent_frontier_artifact_id: str | None = None
    parent_frontier_digest: str | None = None
    source_patch_artifact_ids: tuple[str, ...] = ()
    output_canon_frontier_artifact_id: str | None = None
    quality_status: Literal["passed", "review_limit_reached", "review_error"] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _canon_event_set_contract(self) -> ArtifactManifest:
        if self.artifact_type != "canon.event_set":
            return self
        root = self.parent_frontier_artifact_id is None and self.parent_frontier_digest is None
        paired_parent = (
            self.parent_frontier_artifact_id is not None
            and self.parent_frontier_digest is not None
        )
        if not (root or paired_parent):
            raise ValueError("canon.event_set requires paired parent frontier references or root nulls")
        if not root and not self.source_patch_artifact_ids:
            raise ValueError("non-root canon.event_set requires source patch artifact references")
        return self


class ArtifactFile(VersionedRecord):
    record_type: Literal["artifact_file"] = "artifact_file"
    relative_path: str
    digest: str


class ArtifactReady(VersionedRecord):
    record_type: Literal["artifact_ready"] = "artifact_ready"
    attempt_id: str
    artifact_id: str
    files: tuple[ArtifactFile, ...]
    created_at: str


class SelectionSnapshot(VersionedRecord):
    record_type: Literal["selection_snapshot"] = "selection_snapshot"
    selection_snapshot_id: str
    base_snapshot_id: str | None = None
    slots: dict[str, str]
    slots_digest: str
    created_at: str

    @model_validator(mode="after")
    def _slots_digest_matches(self) -> SelectionSnapshot:
        if self.slots_digest != digest_json(self.slots):
            raise ValueError("selection snapshot slots_digest does not match slots")
        return self


class LedgerEvent(VersionedRecord):
    record_type: Literal["ledger_event"] = "ledger_event"
    event_id: str
    event_type: str
    timestamp: str
    payload: dict[str, Any]
    payload_digest: str

    @model_validator(mode="after")
    def _payload_digest_matches(self) -> LedgerEvent:
        if self.payload_digest != digest_json(self.payload):
            raise ValueError("ledger event payload_digest does not match payload")
        return self


class ImmutableWriter:
    """Exclusive-create writer with explicit permissions and durable ordering."""

    def mkdir(self, path: Path) -> None:
        _mkdir_private(path)

    def mkdir_exclusive(self, path: Path) -> None:
        """Create a new immutable directory; collisions are ID-generation errors."""
        _mkdir_private(path.parent)
        os.mkdir(path, _DIR_MODE)
        os.chmod(path, _DIR_MODE)
        _fsync_directory(path.parent)

    def write_bytes(self, path: Path, content: bytes) -> str:
        _mkdir_private(path.parent)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, _FILE_MODE)
        try:
            with os.fdopen(fd, "wb", closefd=False) as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            os.close(fd)
        os.chmod(path, _FILE_MODE)
        return digest_bytes(content)

    def write_text(self, path: Path, content: str) -> str:
        return self.write_bytes(path, content.encode("utf-8"))

    def write_json(self, path: Path, value: Any) -> str:
        return self.write_bytes(path, canonical_json(sanitize_for_storage(value)))

    def append_jsonl(self, path: Path, value: Any) -> str:
        _mkdir_private(path.parent)
        content = canonical_json(sanitize_for_storage(value)) + b"\n"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, _FILE_MODE)
        try:
            os.write(fd, content)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.chmod(path, _FILE_MODE)
        return digest_bytes(content)


@dataclass(frozen=True, slots=True)
class RunHandle:
    manifest: RunManifest
    path: Path


@dataclass(frozen=True, slots=True)
class AttemptHandle:
    manifest: AttemptManifest
    path: Path


@dataclass(frozen=True, slots=True)
class ArtifactReference:
    artifact_id: str
    attempt_id: str
    path: Path
    manifest: ArtifactManifest


class RunRepository:
    """Append-only run, artifact, ledger and snapshot repository."""

    def __init__(self, workspace: Path, *, read_only: bool = False) -> None:
        self.workspace = workspace.resolve()
        self.read_only = read_only
        self.writer = ImmutableWriter()
        if not read_only:
            self.writer.mkdir(self.workspace)
            self.writer.mkdir(self.runtime_root)
            self.writer.mkdir(self.runs_root)

    @property
    def runtime_root(self) -> Path:
        return self.workspace / ".novel-forge"

    @property
    def runs_root(self) -> Path:
        return self.runtime_root / "runs"

    def series_root(self, slug: str) -> Path:
        if not re.fullmatch(r"[a-z0-9_]+", slug):
            raise ValueError(f"Unsafe series slug: {slug}")
        return self.workspace / slug

    def series_runtime_root(self, slug: str) -> Path:
        return self.series_root(slug) / ".novel-forge"

    def ledger_root(self, slug: str) -> Path:
        return self.series_runtime_root(slug) / "ledger"

    def create_run(
        self,
        *,
        command: str,
        model: str,
        verbose: bool,
        input_snapshot_id: str | None = None,
    ) -> RunHandle:
        if input_snapshot_id is None and command != "plan":
            raise RuntimeContractError("only plan may start a bootstrap run")
        run_id = f"run_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:6]}"
        path = self.runs_root / run_id
        self.writer.mkdir_exclusive(path)
        self.writer.mkdir_exclusive(path / "attempts")
        self.writer.mkdir_exclusive(path / "logs")
        manifest = RunManifest(
            run_id=run_id,
            command=command,
            workspace=str(self.workspace),
            input_snapshot_id=input_snapshot_id,
            input_kind="bootstrap" if input_snapshot_id is None else "selection_snapshot",
            started_at=utc_now(),
            verbose=verbose,
            model=model,
        )
        self.writer.write_json(path / "run.json", manifest.model_dump())
        self.writer.write_text(path / "logs" / "run.log", "")
        self._append_run_event(path, "run.created", {"run_id": run_id, "command": command})
        _fsync_directory(path)
        return RunHandle(manifest=manifest, path=path)

    def start_attempt(
        self,
        run: RunHandle,
        *,
        task_id: str,
        phase: str,
        reason: str,
        retry_number: int = 1,
        seed: int | None = None,
    ) -> AttemptHandle:
        attempt_id = (
            f"att_{len(tuple((run.path / 'attempts').iterdir())) + 1:06d}_"
            f"{task_id.replace('.', '_')}_{uuid.uuid4().hex[:6]}"
        )
        path = run.path / "attempts" / attempt_id
        self.writer.mkdir_exclusive(path)
        self.writer.mkdir_exclusive(path / "artifacts")
        manifest = AttemptManifest(
            attempt_id=attempt_id,
            run_id=run.manifest.run_id,
            task_id=task_id,
            phase=phase,
            model=run.manifest.model,
            seed=seed,
            reason=reason,
            retry_number=retry_number,
            started_at=utc_now(),
        )
        self.writer.write_json(path / "attempt.json", manifest.model_dump())
        _fsync_directory(path)
        self._append_run_event(run.path, "attempt.created", {"attempt_id": attempt_id, "task_id": task_id})
        return AttemptHandle(manifest=manifest, path=path)

    def commit_artifact(
        self,
        attempt: AttemptHandle,
        *,
        artifact_type: str,
        logical_key: str,
        payload: Any,
        payload_name: str,
        input_artifact_ids: tuple[str, ...] = (),
        prompt_digest: str | None = None,
        schema_digest: str | None = None,
        canon_lineage_root_digest: str | None = None,
        input_canon_frontier_digest: str | None = None,
        parent_frontier_artifact_id: str | None = None,
        parent_frontier_digest: str | None = None,
        source_patch_artifact_ids: tuple[str, ...] = (),
        output_canon_frontier_artifact_id: str | None = None,
        quality_status: Literal["passed", "review_limit_reached", "review_error"] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactReference:
        if any(attempt.path.glob("artifact-ready.*.json")) or (attempt.path / "error.json").exists():
            raise RuntimeContractError("attempt already reached a terminal state")
        if quality_status == "review_error":
            raise RuntimeContractError("review_error candidates must not be committed as ready artifacts")
        payload_rel = _safe_relative(f"artifacts/{payload_name}")
        artifact_id = f"art_{uuid.uuid4().hex}"
        payload_path = attempt.path / payload_rel
        if isinstance(payload, bytes):
            content_digest = self.writer.write_bytes(payload_path, payload)
        elif isinstance(payload, str):
            content_digest = self.writer.write_text(payload_path, payload)
        else:
            content_digest = self.writer.write_json(payload_path, payload)
        manifest = ArtifactManifest(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            logical_key=logical_key,
            payload_path=str(payload_rel),
            content_digest=content_digest,
            input_artifact_ids=input_artifact_ids,
            prompt_digest=prompt_digest,
            schema_digest=schema_digest,
            canon_lineage_root_digest=canon_lineage_root_digest,
            input_canon_frontier_digest=input_canon_frontier_digest,
            parent_frontier_artifact_id=parent_frontier_artifact_id,
            parent_frontier_digest=parent_frontier_digest,
            source_patch_artifact_ids=source_patch_artifact_ids,
            output_canon_frontier_artifact_id=output_canon_frontier_artifact_id,
            quality_status=quality_status,
            metadata=metadata or {},
        )
        manifest_rel = _safe_relative(f"artifacts/{payload_name}.manifest.json")
        manifest_path = attempt.path / manifest_rel
        manifest_digest = self.writer.write_json(manifest_path, manifest.model_dump())
        _fsync_directory(attempt.path)
        ready = ArtifactReady(
            attempt_id=attempt.manifest.attempt_id,
            artifact_id=artifact_id,
            files=(
                ArtifactFile(relative_path=str(payload_rel), digest=content_digest),
                ArtifactFile(relative_path=str(manifest_rel), digest=manifest_digest),
            ),
            created_at=utc_now(),
        )
        self.writer.write_json(attempt.path / f"artifact-ready.{artifact_id}.json", ready.model_dump())
        _fsync_directory(attempt.path)
        self._append_run_event(
            attempt.path.parent.parent,
            "artifact.ready",
            {"attempt_id": attempt.manifest.attempt_id, "artifact_id": artifact_id},
        )
        self._append_run_event(
            attempt.path.parent.parent,
            "attempt.succeeded",
            {
                "attempt_id": attempt.manifest.attempt_id,
                "ended_at": utc_now(),
                "reason": "artifact_ready",
                "validation_outcome": "passed",
                "retryable": False,
            },
        )
        return ArtifactReference(artifact_id, attempt.manifest.attempt_id, attempt.path, manifest)

    def fail_attempt(
        self,
        attempt: AttemptHandle,
        *,
        error_code: str,
        retryable: bool,
        http_status: int | None = None,
        detail: str | None = None,
    ) -> None:
        if any(attempt.path.glob("artifact-ready.*.json")) or (attempt.path / "error.json").exists():
            raise RuntimeContractError("attempt already reached a terminal state")
        run = attempt.path.parent.parent
        verbose = self._read_run(run).verbose
        payload: dict[str, Any] = {
            "format_version": FORMAT_VERSION,
            "record_type": "attempt_error",
            "error_class": error_code,
            "error_code": error_code,
            "http_status": http_status,
            "retryable": retryable,
            "body_saved": bool(verbose and detail),
        }
        if verbose and detail:
            payload["sanitized_detail"] = sanitize_for_storage(detail)
        self.writer.write_json(attempt.path / "error.json", payload)
        _fsync_directory(attempt.path)
        self._append_run_event(
            run,
            "attempt.failed",
            {
                "attempt_id": attempt.manifest.attempt_id,
                "ended_at": utc_now(),
                "reason": error_code,
                "validation_outcome": "failed",
                "retryable": retryable,
            },
        )

    def create_selection_snapshot(
        self,
        *,
        slug: str,
        slots: dict[str, str],
        base_snapshot_id: str | None = None,
        reason: str,
    ) -> SelectionSnapshot:
        if not slots:
            raise RuntimeContractError("selection snapshot requires slots")
        for slot, artifact_id in slots.items():
            ref = self.verify_artifact(artifact_id)
            if slot == "canon.frontier":
                # Frontier artifacts keep a stable selection slot while their
                # artifact logical key encodes lineage (e.g. canon.frontier.root).
                if not ref.manifest.logical_key.startswith("canon.frontier"):
                    raise RuntimeContractError(
                        f"selection slot {slot!r} requires a canon.frontier* logical key, "
                        f"got {ref.manifest.logical_key!r}"
                    )
            elif ref.manifest.logical_key != slot:
                raise RuntimeContractError(
                    f"selection slot {slot!r} does not match referenced artifact logical key "
                    f"{ref.manifest.logical_key!r}"
                )
        if base_snapshot_id is not None:
            self.load_snapshot(slug, base_snapshot_id)
        self.verify_canon_snapshot(slots)
        ledger = self.ledger_root(slug)
        self.writer.mkdir(ledger)
        snapshots = ledger / "snapshots"
        self.writer.mkdir(snapshots)
        snapshot_id = f"sel_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:6]}"
        snapshot = SelectionSnapshot(
            selection_snapshot_id=snapshot_id,
            base_snapshot_id=base_snapshot_id,
            slots=dict(sorted(slots.items())),
            slots_digest=digest_json(dict(sorted(slots.items()))),
            created_at=utc_now(),
        )
        snapshot_path = snapshots / f"{snapshot_id}.json"
        snapshot_digest = self.writer.write_json(snapshot_path, snapshot.model_dump())
        _fsync_directory(snapshots)
        self._append_ledger_event(
            slug,
            "selection.snapshot.created",
            {
                "selection_snapshot_id": snapshot_id,
                "base_snapshot_id": base_snapshot_id,
                "slots": snapshot.slots,
                "slots_digest": snapshot.slots_digest,
                "snapshot_path": str(snapshot_path.relative_to(self.series_root(slug))),
                "snapshot_digest": snapshot_digest,
                "reason": reason,
            },
        )
        _fsync_directory(ledger)
        return snapshot

    def commit_pnca_series_acceptance(
        self, *, slug: str, acceptance: SeriesAcceptanceCommit
    ) -> SelectionSnapshot:
        """Atomically select the PNCA root without a legacy snapshot transition."""
        series = self.verify_artifact(acceptance.role_artifact_ids["series.contract"])
        seed = self.verify_artifact(acceptance.role_artifact_ids["canon.seed"])
        frontier = self.verify_artifact(acceptance.role_artifact_ids["canon.frontier.output"])
        if series.manifest.artifact_type != "pnca.series.contract":
            raise RuntimeContractError("PNCA series acceptance requires pnca.series.contract")
        if seed.manifest.artifact_type != "canon.seed" or seed.manifest.logical_key != "canon.seed":
            raise RuntimeContractError("PNCA series acceptance requires canon.seed")
        if frontier.manifest.artifact_type != "canon.event_set" or not frontier.manifest.logical_key.startswith("canon.frontier.root"):
            raise RuntimeContractError("PNCA series acceptance requires canon.frontier.root")
        if frontier.manifest.canon_lineage_root_digest != seed.manifest.content_digest:
            raise RuntimeContractError("PNCA root frontier must bind the selected canon.seed digest")
        slots = {
            series.manifest.logical_key: series.artifact_id,
            "canon.seed": seed.artifact_id,
            "canon.frontier": frontier.artifact_id,
        }
        self.verify_canon_snapshot(slots)
        ledger = self.ledger_root(slug)
        self.writer.mkdir(ledger)
        snapshots = ledger / "snapshots"
        self.writer.mkdir(snapshots)
        snapshot_id = f"sel_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:6]}"
        snapshot = SelectionSnapshot(
            selection_snapshot_id=snapshot_id,
            base_snapshot_id=None,
            slots=dict(sorted(slots.items())),
            slots_digest=digest_json(dict(sorted(slots.items()))),
            created_at=utc_now(),
        )
        snapshot_path = snapshots / f"{snapshot_id}.json"
        snapshot_digest = self.writer.write_json(snapshot_path, snapshot.model_dump())
        _fsync_directory(snapshots)
        self._append_ledger_event(
            slug,
            "pnca.series.acceptance.committed",
            {
                "acceptance_id": acceptance.acceptance_id,
                "selection_snapshot_id": snapshot_id,
                "slots": snapshot.slots,
                "slots_digest": snapshot.slots_digest,
                "snapshot_path": str(snapshot_path.relative_to(self.series_root(slug))),
                "snapshot_digest": snapshot_digest,
                "acceptance": acceptance.model_dump(mode="json"),
            },
        )
        _fsync_directory(ledger)
        return snapshot

    def commit_pnca_volume_acceptance(self, *, slug: str, acceptance: VolumeAcceptanceCommit) -> SelectionSnapshot:
        """Atomically publish one Volume Contract against its selected Series parent."""
        base = self.load_snapshot(slug, acceptance.base_snapshot_id)
        parent_id = next((artifact_id for key, artifact_id in base.slots.items() if key.startswith("pnca.series.contract.")), None)
        if parent_id is None:
            raise RuntimeContractError("Volume acceptance base snapshot requires series.contract")
        volume = self.verify_artifact(acceptance.role_artifact_ids["volume.contract"])
        if volume.manifest.artifact_type != "pnca.volume.contract":
            raise RuntimeContractError("Volume acceptance requires pnca.volume.contract")
        if parent_id not in volume.manifest.input_artifact_ids:
            raise RuntimeContractError("Volume acceptance requires exact selected Series Contract input")
        payload = self.read_payload(volume)
        ordinal = payload.get("volume_ordinal") if isinstance(payload, dict) else None
        if not isinstance(ordinal, int) or ordinal < 1:
            raise RuntimeContractError("Volume acceptance requires a positive volume_ordinal")
        slot = f"volume.contract.{ordinal:03d}"
        if slot in base.slots:
            raise RuntimeContractError("Volume acceptance must not overwrite an existing selected slot")
        slots = dict(base.slots)
        slots[slot] = volume.artifact_id
        self.verify_canon_snapshot(slots)
        ledger = self.ledger_root(slug)
        self.writer.mkdir(ledger)
        snapshots = ledger / "snapshots"
        self.writer.mkdir(snapshots)
        snapshot_id = f"sel_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:6]}"
        snapshot = SelectionSnapshot(selection_snapshot_id=snapshot_id, base_snapshot_id=acceptance.base_snapshot_id, slots=dict(sorted(slots.items())), slots_digest=digest_json(dict(sorted(slots.items()))), created_at=utc_now())
        snapshot_path = snapshots / f"{snapshot_id}.json"
        snapshot_digest = self.writer.write_json(snapshot_path, snapshot.model_dump())
        self._append_ledger_event(slug, "pnca.volume.acceptance.committed", {"acceptance_id": acceptance.acceptance_id, "selection_snapshot_id": snapshot_id, "base_snapshot_id": acceptance.base_snapshot_id, "slots": snapshot.slots, "slots_digest": snapshot.slots_digest, "snapshot_path": str(snapshot_path.relative_to(self.series_root(slug))), "snapshot_digest": snapshot_digest, "acceptance": acceptance.model_dump(mode="json")})
        _fsync_directory(ledger)
        return snapshot

    def commit_pnca_acceptance(
        self,
        *,
        slug: str,
        acceptance: AcceptanceCommit,
        frontier_binding: FrontierBinding,
    ) -> SelectionSnapshot:
        """Atomically make a complete prepared PNCA acceptance visible.

        Prepared artifacts may exist after a crash, but only the ledger event written
        here makes their complete role group selected.  This method deliberately does
        not delegate to ``create_selection_snapshot`` because PNCA needs the selection
        and operation record in one visibility event.
        """
        prior = self._pnca_operation_event(slug, acceptance.operation_key)
        if prior is not None:
            operation = OperationRecord.model_validate(prior.payload["operation"])
            if (
                operation.input_snapshot_id == acceptance.base_snapshot_id
                and prior.payload.get("acceptance_id") == acceptance.acceptance_id
                and prior.payload.get("frontier_binding") == frontier_binding.model_dump(mode="json")
            ):
                snapshot_id = prior.payload.get("selection_snapshot_id")
                if isinstance(snapshot_id, str):
                    return self.load_snapshot(slug, snapshot_id)
            self._append_ledger_event(
                slug,
                "pnca.operation.superseded",
                {
                    "operation_key": acceptance.operation_key,
                    "existing_acceptance_id": prior.payload.get("acceptance_id"),
                    "requested_acceptance_id": acceptance.acceptance_id,
                    "existing_base_snapshot_id": operation.input_snapshot_id,
                    "requested_base_snapshot_id": acceptance.base_snapshot_id,
                },
            )
            raise RuntimeContractError("PNCA operation key reuse is superseded")

        if acceptance.base_snapshot_id != frontier_binding.input_snapshot_id:
            raise RuntimeContractError("AcceptanceCommit base snapshot must equal FrontierBinding input snapshot")
        base = self.load_snapshot(slug, acceptance.base_snapshot_id)
        base_frontier_id = base.slots.get("canon.frontier")
        if base_frontier_id is None:
            raise RuntimeContractError("PNCA acceptance base snapshot requires canon.frontier")
        if base_frontier_id != frontier_binding.frontier_artifact_id:
            raise RuntimeContractError("PNCA acceptance requires the exact base snapshot frontier artifact")
        base_frontier = self.verify_artifact(base_frontier_id).manifest
        if base_frontier.content_digest != frontier_binding.frontier_digest:
            raise RuntimeContractError("PNCA acceptance requires the exact base snapshot frontier digest")
        base_seed_id = base.slots.get("canon.seed")
        if base_seed_id is None:
            raise RuntimeContractError("PNCA acceptance base snapshot requires canon.seed")
        base_seed = self.verify_artifact(base_seed_id).manifest
        if base_seed.content_digest != frontier_binding.lineage_root_digest:
            raise RuntimeContractError("PNCA FrontierBinding lineage root does not match base canon.seed")

        slots = dict(base.slots)
        scene_contract = self.verify_artifact(acceptance.role_artifact_ids["scene.contract"])
        for role, artifact_id in acceptance.role_artifact_ids.items():
            ref = self.verify_artifact(artifact_id)
            manifest = ref.manifest
            if role == "canon.frontier.output":
                if acceptance.canon_effect == "none":
                    if artifact_id != frontier_binding.frontier_artifact_id:
                        raise RuntimeContractError("eventless PNCA acceptance must preserve the exact input frontier artifact")
                    slots["canon.frontier"] = artifact_id
                    continue
                if manifest.artifact_type != "canon.event_set":
                    raise RuntimeContractError("PNCA output frontier role requires canon.event_set")
                if not manifest.logical_key.startswith("canon.frontier"):
                    raise RuntimeContractError("PNCA output frontier role requires canon.frontier logical key")
                if manifest.parent_frontier_artifact_id != frontier_binding.frontier_artifact_id:
                    raise RuntimeContractError("PNCA output frontier parent must equal exact input frontier")
                if manifest.parent_frontier_digest != frontier_binding.frontier_digest:
                    raise RuntimeContractError("PNCA output frontier parent digest must equal exact input frontier")
                if manifest.input_canon_frontier_digest != frontier_binding.frontier_digest:
                    raise RuntimeContractError("PNCA output frontier input digest must equal exact input frontier")
                metadata = manifest.metadata
                if metadata.get("source_scene_contract_artifact_id") != scene_contract.artifact_id:
                    raise RuntimeContractError("PNCA output frontier must bind its selected scene contract artifact")
                if metadata.get("source_scene_contract_digest") != scene_contract.manifest.content_digest:
                    raise RuntimeContractError("PNCA output frontier must bind its selected scene contract digest")
                slots["canon.frontier"] = artifact_id
                continue
            if manifest.input_canon_frontier_digest != frontier_binding.frontier_digest:
                raise RuntimeContractError(
                    f"PNCA role {role!r} does not bind to the exact input Canon frontier"
                )
            if manifest.canon_lineage_root_digest != frontier_binding.lineage_root_digest:
                raise RuntimeContractError(
                    f"PNCA role {role!r} does not bind to the exact Canon lineage root"
                )
            if manifest.logical_key in slots and slots[manifest.logical_key] != artifact_id:
                raise RuntimeContractError(f"PNCA role {role!r} overwrites an existing selected slot")
            slots[manifest.logical_key] = artifact_id

        self.verify_canon_snapshot(slots)
        ledger = self.ledger_root(slug)
        self.writer.mkdir(ledger)
        snapshots = ledger / "snapshots"
        self.writer.mkdir(snapshots)
        snapshot_id = f"sel_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:6]}"
        snapshot = SelectionSnapshot(
            selection_snapshot_id=snapshot_id,
            base_snapshot_id=acceptance.base_snapshot_id,
            slots=dict(sorted(slots.items())),
            slots_digest=digest_json(dict(sorted(slots.items()))),
            created_at=utc_now(),
        )
        snapshot_path = snapshots / f"{snapshot_id}.json"
        snapshot_digest = self.writer.write_json(snapshot_path, snapshot.model_dump())
        _fsync_directory(snapshots)
        operation = OperationRecord(
            operation_key=acceptance.operation_key,
            input_snapshot_id=acceptance.base_snapshot_id,
            state="committed",
            acceptance_id=acceptance.acceptance_id,
        )
        self._append_ledger_event(
            slug,
            "pnca.acceptance.committed",
            {
                "acceptance_id": acceptance.acceptance_id,
                "selection_snapshot_id": snapshot_id,
                "base_snapshot_id": acceptance.base_snapshot_id,
                "slots": snapshot.slots,
                "slots_digest": snapshot.slots_digest,
                "snapshot_path": str(snapshot_path.relative_to(self.series_root(slug))),
                "snapshot_digest": snapshot_digest,
                "acceptance": acceptance.model_dump(mode="json"),
                "frontier_binding": frontier_binding.model_dump(mode="json"),
                "operation": operation.model_dump(mode="json"),
            },
        )
        _fsync_directory(ledger)
        return snapshot

    def load_pnca_operation(self, slug: str, operation_key: str) -> OperationRecord:
        """Return the durable selected operation record for an idempotency key."""
        event = self._pnca_operation_event(slug, operation_key)
        if event is None:
            raise FileNotFoundError(f"PNCA operation not found: {operation_key}")
        return OperationRecord.model_validate(event.payload["operation"])

    def _pnca_operation_event(self, slug: str, operation_key: str) -> LedgerEvent | None:
        for event in self._ledger_events(slug):
            if event.event_type != "pnca.acceptance.committed":
                continue
            operation = event.payload.get("operation")
            if isinstance(operation, dict) and operation.get("operation_key") == operation_key:
                return event
        return None

    def current_snapshot_id(self, slug: str) -> str:
        """Return the latest *ledger-selected* snapshot, never a latest artifact."""
        selected = [
            event.payload.get("selection_snapshot_id")
            for event in self._ledger_events(slug)
            if event.event_type in {
                "selection.snapshot.created",
                "pnca.acceptance.committed",
                "pnca.series.acceptance.committed",
                "pnca.volume.acceptance.committed",
            }
        ]
        if not selected or not isinstance(selected[-1], str):
            raise FileNotFoundError(f"no selection snapshot found for series: {slug}")
        return selected[-1]

    def load_snapshot(self, slug: str, snapshot_id: str) -> SelectionSnapshot:
        event = next(
            (
                event for event in self._ledger_events(slug)
                if event.event_type in {
                "selection.snapshot.created",
                "pnca.acceptance.committed",
                "pnca.series.acceptance.committed",
                "pnca.volume.acceptance.committed",
            }
                and event.payload.get("selection_snapshot_id") == snapshot_id
            ),
            None,
        )
        if event is None:
            raise FileNotFoundError(f"selection snapshot not found: {snapshot_id}")
        path = self.series_root(slug) / _safe_relative(str(event.payload["snapshot_path"]))
        raw = path.read_bytes()
        if digest_bytes(raw) != event.payload["snapshot_digest"]:
            raise CorruptArtifactError(f"selection snapshot digest mismatch: {snapshot_id}")
        snapshot = SelectionSnapshot.model_validate_json(raw)
        if snapshot.selection_snapshot_id != snapshot_id:
            raise CorruptArtifactError(f"selection snapshot ID mismatch: {snapshot_id}")
        for artifact_id in snapshot.slots.values():
            self.verify_artifact(artifact_id)
        self.verify_canon_snapshot(snapshot.slots)
        return snapshot

    def resolve_artifact(self, artifact_id: str) -> ArtifactReference:
        candidates = list(self.runs_root.glob("*/attempts/*/artifacts/*.manifest.json"))
        for manifest_path in candidates:
            try:
                manifest = ArtifactManifest.model_validate_json(manifest_path.read_bytes())
            except Exception as exc:
                raise CorruptArtifactError(f"invalid artifact manifest: {manifest_path}") from exc
            if manifest.artifact_id == artifact_id:
                return ArtifactReference(
                    artifact_id=artifact_id,
                    attempt_id=manifest_path.parent.parent.name,
                    path=manifest_path.parent.parent,
                    manifest=manifest,
                )
        raise FileNotFoundError(f"artifact not found: {artifact_id}")

    def latest_ready_artifact(
        self, slug: str, artifact_type: str, logical_key: str
    ) -> ArtifactReference | None:
        """Return the most recently committed ready artifact for a logical key.

        Walks every attempt in the repository and picks the artifact whose
        ``artifact_type`` and ``logical_key`` match.  Ordering follows the
        attempt id (lexicographic == creation order), so the last committed
        artifact wins.  Returns ``None`` when no matching ready artifact exists.
        """
        del slug  # artifacts are repository-wide; logical_key disambiguates
        best: ArtifactReference | None = None
        for manifest_path in self.runs_root.glob("*/attempts/*/artifacts/*.manifest.json"):
            try:
                manifest = ArtifactManifest.model_validate_json(manifest_path.read_bytes())
            except Exception:
                continue
            if manifest.artifact_type != artifact_type or manifest.logical_key != logical_key:
                continue
            ready_marker = manifest_path.parent.parent / f"artifact-ready.{manifest.artifact_id}.json"
            if not ready_marker.exists():
                continue
            ref = ArtifactReference(
                artifact_id=manifest.artifact_id,
                attempt_id=manifest_path.parent.parent.name,
                path=manifest_path.parent.parent,
                manifest=manifest,
            )
            if best is None or ref.attempt_id > best.attempt_id:
                best = ref
        return best

    def read_payload(self, ref: ArtifactReference) -> Any:
        """Load a verified artifact payload; never trust a previously resolved path."""
        verified = self.verify_artifact(ref.artifact_id)
        payload_path = verified.path / _safe_relative(verified.manifest.payload_path)
        raw = payload_path.read_bytes()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw.decode("utf-8", errors="replace")

    def verify_artifact(self, artifact_id: str) -> ArtifactReference:
        ref = self.resolve_artifact(artifact_id)
        ready_path = ref.path / f"artifact-ready.{artifact_id}.json"
        if not ready_path.exists():
            raise CorruptArtifactError(f"artifact has no ready marker: {artifact_id}")
        try:
            ready = ArtifactReady.model_validate_json(ready_path.read_bytes())
        except Exception as exc:
            raise CorruptArtifactError(f"invalid ready marker: {artifact_id}") from exc
        if ready.artifact_id != artifact_id:
            raise CorruptArtifactError(f"ready marker points to another artifact: {artifact_id}")
        for file in ready.files:
            path = ref.path / _safe_relative(file.relative_path)
            if not path.is_file() or digest_bytes(path.read_bytes()) != file.digest:
                raise CorruptArtifactError(f"artifact file digest mismatch: {artifact_id}:{file.relative_path}")
        manifest_path = ref.path / _safe_relative(ref.manifest.payload_path + ".manifest.json")
        if not manifest_path.is_file():
            raise CorruptArtifactError(f"artifact manifest missing: {artifact_id}")
        payload_path = ref.path / _safe_relative(ref.manifest.payload_path)
        if digest_bytes(payload_path.read_bytes()) != ref.manifest.content_digest:
            raise CorruptArtifactError(f"artifact payload digest mismatch: {artifact_id}")
        return ref

    def verify_canon_snapshot(self, slots: dict[str, str]) -> None:
        frontier_id = slots.get("canon.frontier")
        if frontier_id is None:
            return
        frontier = self.verify_artifact(frontier_id).manifest
        if frontier.artifact_type != "canon.event_set":
            raise RuntimeContractError("canon.frontier must reference a canon.event_set artifact")
        root = slots.get("canon.seed")
        if root is None:
            raise RuntimeContractError("canon.frontier requires canon.seed in the same snapshot")
        root_manifest = self.verify_artifact(root).manifest
        root_digest = root_manifest.content_digest
        if frontier.canon_lineage_root_digest not in (None, root_digest):
            raise RuntimeContractError("canon.frontier lineage root does not match canon.seed")
        for artifact_id in slots.values():
            manifest = self.verify_artifact(artifact_id).manifest
            if manifest.input_canon_frontier_digest is None:
                continue
            if manifest.canon_lineage_root_digest != root_digest:
                raise RuntimeContractError("snapshot mixes different Canon lineage roots")
            if not self._is_frontier_ancestor(
                required_digest=manifest.input_canon_frontier_digest,
                frontier=frontier,
            ):
                raise RuntimeContractError("artifact input Canon frontier is not an ancestor of snapshot frontier")

    def _is_frontier_ancestor(self, *, required_digest: str, frontier: ArtifactManifest) -> bool:
        current = frontier
        seen: set[str] = set()
        while True:
            if current.content_digest == required_digest:
                return True
            if current.artifact_id in seen:
                raise CorruptArtifactError("Canon frontier parent cycle")
            seen.add(current.artifact_id)
            if current.parent_frontier_artifact_id is None:
                return False
            parent = self.verify_artifact(current.parent_frontier_artifact_id).manifest
            if current.parent_frontier_digest != parent.content_digest:
                raise CorruptArtifactError("Canon frontier parent digest mismatch")
            current = parent

    def read_run(self, run_id: str) -> RunHandle:
        path = self.runs_root / run_id
        manifest_path = path / "run.json"
        if not manifest_path.is_file():
            raise FileNotFoundError(f"run not found: {run_id}")
        return RunHandle(RunManifest.model_validate_json(manifest_path.read_bytes()), path)

    def read_attempt(self, attempt_id: str) -> AttemptHandle:
        candidates = list(self.runs_root.glob(f"*/attempts/{attempt_id}/attempt.json"))
        if len(candidates) != 1:
            raise FileNotFoundError(f"attempt not found: {attempt_id}")
        path = candidates[0]
        return AttemptHandle(AttemptManifest.model_validate_json(path.read_bytes()), path.parent)

    def llm_diff(self, attempt_a: str, attempt_b: str, *, metadata_only: bool = False) -> str:
        first, second = self.read_attempt(attempt_a), self.read_attempt(attempt_b)
        if metadata_only:
            keys = ("task_id", "model", "seed", "reason", "retry_number")
            return "\n".join(
                f"{key}: {getattr(first.manifest, key)!r} -> {getattr(second.manifest, key)!r}"
                for key in keys
                if getattr(first.manifest, key) != getattr(second.manifest, key)
            ) or "metadata: identical"
        required = ("llm/request.json", "llm/response.content.json", "llm/parsed.json")
        missing = [
            attempt.manifest.attempt_id
            for attempt in (first, second)
            if any(not (attempt.path / item).is_file() for item in required)
        ]
        if missing:
            raise RuntimeContractError(
                "complete verbose capture required for llm diff; missing: " + ", ".join(missing)
            )
        output: list[str] = []
        for relative in required:
            a_lines = (first.path / relative).read_text(encoding="utf-8").splitlines()
            b_lines = (second.path / relative).read_text(encoding="utf-8").splitlines()
            output.extend(difflib.unified_diff(a_lines, b_lines, fromfile=f"{attempt_a}/{relative}", tofile=f"{attempt_b}/{relative}", lineterm=""))
        return "\n".join(output) or "LLM captures: identical"

    def artifact_diff(self, artifact_a: str, artifact_b: str) -> str:
        first, second = self.verify_artifact(artifact_a), self.verify_artifact(artifact_b)
        a_path = first.path / _safe_relative(first.manifest.payload_path)
        b_path = second.path / _safe_relative(second.manifest.payload_path)
        return "\n".join(
            difflib.unified_diff(
                a_path.read_text(encoding="utf-8").splitlines(),
                b_path.read_text(encoding="utf-8").splitlines(),
                fromfile=artifact_a,
                tofile=artifact_b,
                lineterm="",
            )
        ) or "artifacts: identical"

    def _read_run(self, run_path: Path) -> RunManifest:
        return RunManifest.model_validate_json((run_path / "run.json").read_bytes())

    def _append_run_event(self, run_path: Path, event_type: str, payload: dict[str, Any]) -> LedgerEvent:
        event = self._event(event_type, payload)
        self.writer.append_jsonl(run_path / "events.jsonl", event.model_dump())
        return event

    def _append_ledger_event(self, slug: str, event_type: str, payload: dict[str, Any]) -> LedgerEvent:
        event = self._event(event_type, payload)
        self.writer.append_jsonl(self.ledger_root(slug) / "events.jsonl", event.model_dump())
        return event

    def _event(self, event_type: str, payload: dict[str, Any]) -> LedgerEvent:
        safe_payload = sanitize_for_storage(payload)
        return LedgerEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            timestamp=utc_now(),
            payload=safe_payload,
            payload_digest=digest_json(safe_payload),
        )

    def _ledger_events(self, slug: str) -> Iterator[LedgerEvent]:
        path = self.ledger_root(slug) / "events.jsonl"
        if not path.exists():
            return
        with path.open(encoding="utf-8") as stream:
            for index, line in enumerate(stream):
                if not line.strip():
                    continue
                try:
                    yield LedgerEvent.model_validate_json(line)
                except Exception:
                    # Only a final partial line is crash-tolerated.  Mid-file
                    # corruption is never silently repaired.
                    if index == sum(1 for _ in path.open(encoding="utf-8")) - 1:
                        return
                    raise CorruptArtifactError(f"invalid ledger event at {path}:{index + 1}") from None


class AttemptCapture:
    """Attempt-scoped immutable LLM evidence writer for every task execution."""

    def __init__(self, repository: RunRepository, attempt: AttemptHandle, verbose: bool) -> None:
        self.repository = repository
        self.attempt = attempt
        self.verbose = verbose
        self.llm_dir = attempt.path / "llm"
        repository.writer.mkdir(self.llm_dir)

    def request(self, payload: dict[str, Any]) -> None:
        self.repository.writer.write_json(self.llm_dir / "request.json", payload)

    def response_ndjson(self, lines: list[dict[str, Any]]) -> None:
        cleaned = [sanitize_for_storage(line) for line in lines]
        text = "".join(json.dumps(line, ensure_ascii=False, sort_keys=True) + "\n" for line in cleaned)
        self.repository.writer.write_text(self.llm_dir / "response.ndjson", text)

    def response_content(self, content: str) -> None:
        self.repository.writer.write_json(self.llm_dir / "response.content.json", {"content": content})

    def parsed(self, value: dict[str, Any]) -> None:
        self.repository.writer.write_json(self.llm_dir / "parsed.json", value)

    def validation(self, value: dict[str, Any]) -> None:
        self.repository.writer.write_json(self.llm_dir / "validation.json", value)


@dataclass(frozen=True, slots=True)
class ProcessIdentity:
    pid: int
    ppid: int
    process_start_time: str
    boot_id: str
    argv: tuple[str, ...]
    run_id: str
    phase: str
    started_at: str
    log_path: str

    @classmethod
    def current(cls, *, run_id: str, phase: str, log_path: Path) -> ProcessIdentity:
        return cls(
            pid=os.getpid(),
            ppid=os.getppid(),
            process_start_time=_linux_process_start_time(os.getpid()),
            boot_id=_linux_boot_id(),
            argv=tuple(sys.argv),
            run_id=run_id,
            phase=phase,
            started_at=utc_now(),
            log_path=str(log_path),
        )

    def as_json(self) -> dict[str, Any]:
        return {
            "format_version": FORMAT_VERSION,
            "record_type": "run_lock",
            "pid": self.pid,
            "ppid": self.ppid,
            "process_start_time": self.process_start_time,
            "boot_id": self.boot_id,
            "argv": list(self.argv),
            "run_id": self.run_id,
            "phase": self.phase,
            "started_at": self.started_at,
            "log_path": self.log_path,
        }


def _linux_boot_id() -> str:
    return Path("/proc/sys/kernel/random/boot_id").read_text(encoding="utf-8").strip()


def _linux_process_start_time(pid: int) -> str:
    fields = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()
    # proc(5): field 22, zero-based index 21.
    return fields[21]


class RunLock:
    def __init__(self, path: Path, identity: ProcessIdentity, writer: ImmutableWriter) -> None:
        self.path = path
        self.identity = identity
        self.writer = writer

    def release(self) -> None:
        try:
            current = json.loads(self.path.read_text(encoding="utf-8"))
        except OSError:
            return
        if current.get("run_id") != self.identity.run_id:
            raise RuntimeContractError("refusing to release another run's lock")
        self.path.unlink(missing_ok=True)


class RunManager:
    """Coordinates workspace/series ownership without PID-reuse false positives."""

    def __init__(self, repository: RunRepository) -> None:
        self.repository = repository
        self.writer = repository.writer

    @property
    def locks_root(self) -> Path:
        return self.repository.runtime_root / "locks"

    def acquire(
        self,
        *,
        scope: str,
        run: RunHandle,
        phase: str,
        wait: bool = False,
        timeout_seconds: float = 300,
    ) -> RunLock:
        self.writer.mkdir(self.locks_root)
        path = self.locks_root / f"{scope}.lock.json"
        identity = ProcessIdentity.current(run_id=run.manifest.run_id, phase=phase, log_path=run.path / "logs" / "run.log")
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                self.writer.write_json(path, identity.as_json())
                return RunLock(path, identity, self.writer)
            except FileExistsError:
                owner = self._read_lock(path)
                if self._is_stale(owner):
                    path.unlink(missing_ok=True)
                    continue
                if not wait or time.monotonic() >= deadline:
                    raise LockHeldError(
                        f"lock held: run={owner.get('run_id')} pid={owner.get('pid')} "
                        f"log={owner.get('log_path')}"
                    ) from None
                time.sleep(0.1)

    @contextmanager
    def side_effect_scope(
        self,
        *,
        scope: str,
        run: RunHandle,
        phase: str,
        wait: bool = False,
    ) -> Iterator[RunLock]:
        lock = self.acquire(scope=scope, run=run, phase=phase, wait=wait)
        try:
            yield lock
        finally:
            lock.release()

    def promote_plan_to_series(self, *, workspace_lock: RunLock, run: RunHandle, slug: str, wait: bool = False) -> RunLock:
        series_root = self.repository.series_root(slug)
        if (series_root / ".novel-forge" / "ledger").exists():
            raise SeriesSlugExistsError(slug)
        # The workspace lock remains held while this is acquired; callers release
        # it only after the first ledger snapshot is durable.
        return self.acquire(scope=f"series-{slug}", run=run, phase="plan", wait=wait)

    def _read_lock(self, path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise CorruptArtifactError(f"invalid lock file: {path}") from exc
        if not isinstance(value, dict):
            raise CorruptArtifactError(f"invalid lock file: {path}")
        return value

    def _is_stale(self, owner: dict[str, Any]) -> bool:
        try:
            if str(owner.get("boot_id")) != _linux_boot_id():
                return True
            pid = int(owner["pid"])
            return str(owner.get("process_start_time")) != _linux_process_start_time(pid)
        except (FileNotFoundError, ProcessLookupError, KeyError, ValueError, OSError):
            return True

def get_schema_resource(name: str) -> dict[str, Any]:
    """Return the canonical JSON schema for a registered task artifact.

    Thin wrapper that resolves the schema through :class:`TaskRegistry` so that
    prompt/schema ownership stays in one place (the destructive-redesign
    contract: no guessing by filename).
    """
    from novel_forge.task_registry import DEFAULT_TASK_REGISTRY

    spec = DEFAULT_TASK_REGISTRY.get(name)
    schema: dict[str, Any] = DEFAULT_TASK_REGISTRY.load_schema(spec.task_id)
    return schema


