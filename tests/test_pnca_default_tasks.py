from novel_forge.pnca.defaults import default_pnca_task_registry


def test_default_registry_defines_series_contract_from_a_pinned_request_artifact() -> None:
    spec = default_pnca_task_registry().get("pnca.series.contract")

    assert spec.task_kind == "authoring"
    assert [(item.role, item.variable) for item in spec.input_bindings] == [
        ("series.request", "request")
    ]
    assert spec.output.artifact_type == "pnca.series.contract.proposal"
    assert spec.prompt_digest.startswith("sha256:")


def test_default_registry_defines_volume_contract_from_pinned_parent_and_request_artifacts() -> None:
    spec = default_pnca_task_registry().get("pnca.volume.contract")

    assert spec.task_kind == "authoring"
    assert [(item.role, item.variable) for item in spec.input_bindings] == [
        ("parent.contract", "parent"),
        ("volume.request", "request"),
    ]
    assert spec.output.artifact_type == "pnca.volume.contract.proposal"
    assert spec.prompt_digest.startswith("sha256:")
    assert spec.schema_digest.startswith("sha256:")


def test_default_registry_defines_chapter_contract_from_pinned_parent_and_request_artifacts() -> None:
    spec = default_pnca_task_registry().get("pnca.chapter.contract")

    assert spec.task_kind == "authoring"
    assert [(item.role, item.variable) for item in spec.input_bindings] == [
        ("parent.contract", "parent"),
        ("chapter.request", "request"),
    ]
    assert spec.output.artifact_type == "pnca.chapter.contract.proposal"
    assert spec.prompt_digest.startswith("sha256:")
    assert spec.schema_digest.startswith("sha256:")


def test_default_registry_defines_scene_contract_from_pinned_chapter_frontier_and_request_artifacts() -> None:
    spec = default_pnca_task_registry().get("pnca.scene.contract")

    assert spec.task_kind == "authoring"
    assert [(item.role, item.variable) for item in spec.input_bindings] == [
        ("parent.contract", "parent"),
        ("canon.frontier", "frontier"),
        ("scene.request", "request"),
    ]
    assert spec.output.artifact_type == "pnca.scene.contract.proposal"
    assert spec.prompt_digest.startswith("sha256:")
    assert spec.schema_digest.startswith("sha256:")
