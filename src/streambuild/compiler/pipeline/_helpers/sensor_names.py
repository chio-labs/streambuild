"""Logical names sensors must not reuse."""

from __future__ import annotations

from streambuild.compiler.compile.models import CompileProjectInputs


def reserved_sensor_names(*, compile_inputs: CompileProjectInputs) -> frozenset[str]:
    """Pipelines, models, tests, and audits share one namespace with sensors."""

    names: set[str] = set()
    for loaded_pipeline in compile_inputs.pipelines:
        names.add(loaded_pipeline.pipeline.name)
        names.update(transform.name for transform in loaded_pipeline.pipeline.transforms)
    names.update(test.name for test in compile_inputs.tests if test.name is not None)
    names.update(audit.name for audit in compile_inputs.audits if audit.name is not None)
    return frozenset(names)
