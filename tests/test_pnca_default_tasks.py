from novel_forge.pnca.defaults import default_pnca_task_registry


def test_default_registry_defines_series_contract_from_a_pinned_request_artifact() -> None:
    spec = default_pnca_task_registry().get("pnca.series.contract")

    assert spec.task_kind == "authoring"
    assert [(item.role, item.variable) for item in spec.input_bindings] == [
        ("series.request", "request")
    ]
    assert spec.output.artifact_type == "pnca.series.contract.proposal"
    assert spec.prompt_digest.startswith("sha256:")
    assert spec.schema_digest.startswith("sha256:")
