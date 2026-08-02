"""Semantic implementation for workflow authority rules."""

from __future__ import annotations

from typing import Any

from fensu import (
    AssignmentReferenceFact,
    ClassDeclarationFact,
    Fault,
    ImportFact,
    NamedCallFact,
    QualifiedReferenceFact,
    RuleContext,
    SyntaxHandle,
)

from scripts.fensu_policy.constants import (
    ADAPTER_CLASS_RECEIVER_NAMES,
    ADAPTER_CONNECTION_MODULE_PARTS,
    ADAPTER_CONNECTION_SYMBOL,
    ANNOTATED_ASSIGNMENT_CHILD_COUNT,
    BUILD_WORKFLOW_EXECUTION_FUNCTION,
    BUILD_WORKFLOW_EXECUTION_PARAMETERS,
    BUILD_WORKFLOW_EXECUTION_PATH,
    BUILD_WORKFLOW_PUBLICATION_PATH,
    CLICKHOUSE_ADAPTER_PATH_PREFIX,
    CLICKHOUSE_CONNECTION_MODULE_PARTS,
    CLICKHOUSE_CONNECTION_PATH,
    CLICKHOUSE_CONNECTION_SYMBOL,
    FUNCTION_DEFINITION_SYNTAX_KINDS,
    METHOD_REFERENCE_MINIMUM_PARTS,
    PRODUCT_SCOPE_NAME,
    PUBLISHED_WORKFLOW_CONSTRUCTOR_NAME,
    RETIRED_ADAPTER_MUTATION_METHODS,
    WORKFLOW_ASSEMBLER_PATHS,
    WORKFLOW_CONSUMER_PATHS,
    WORKFLOW_CONSUMER_PROHIBITED_CALLS,
    WORKFLOW_GATEWAY_CALL_NAME,
    WORKFLOW_GATEWAY_PATH,
    WORKFLOW_MODELS_MODULE_PARTS,
    WORKFLOW_PLAN_CALL_PREFIX,
    WORKFLOW_RENDER_CALL_PREFIX,
    WORKFLOW_STATEMENT_CONSTRUCTOR_NAME,
    WORKFLOW_TOPOLOGICAL_CALL_FRAGMENT,
)


class WorkflowAuthorityPolicy:
    """Evaluate workflow authority invariants for one analysis context."""

    def __init__(self, *, ctx: RuleContext) -> None:
        self._ctx: RuleContext = ctx

    def check_workflow_mutation_gateway(self) -> list[Fault]:
        """Report real adapter mutation calls outside their approved owners."""
        if self._ctx.scope() != PRODUCT_SCOPE_NAME:
            return []
        path_parts: tuple[str, ...] = self._ctx.repo_relative_parts()
        imports: tuple[ImportFact, ...] = self._ctx.facts.references().imports
        adapter_types: frozenset[str] = self._imported_symbol_spellings(
            imports=imports,
            module_parts=ADAPTER_CONNECTION_MODULE_PARTS,
            symbol=ADAPTER_CONNECTION_SYMBOL,
        )
        clickhouse_types: frozenset[str] = self._proven_clickhouse_type_spellings(
            imports=imports,
        )
        all_adapter_types: frozenset[str] = adapter_types | clickhouse_types
        adapter_classes: frozenset[str] = self._adapter_class_names(
            adapter_type_spellings=all_adapter_types,
        )
        receiver_names, gateway_aliases = self._adapter_bindings(
            adapter_type_spellings=all_adapter_types,
        )
        faults: list[Fault] = []
        called: NamedCallFact
        for called in self._ctx.facts.named_calls():
            reference: QualifiedReferenceFact | None = called.reference
            base_name: str | None = reference.base_name if reference is not None else None
            calls_adapter_method: bool = self._is_adapter_method_call(
                called=called,
                adapter_type_spellings=all_adapter_types,
                adapter_classes=adapter_classes,
                receiver_names=receiver_names,
            )
            calls_gateway_alias: bool = self._call_scope_key(called=called) in gateway_aliases
            calls_gateway_outside_owner: bool = (
                (base_name == WORKFLOW_GATEWAY_CALL_NAME and calls_adapter_method)
                or calls_gateway_alias
            ) and path_parts != WORKFLOW_GATEWAY_PATH
            calls_retired_mutator: bool = (
                base_name in RETIRED_ADAPTER_MUTATION_METHODS
                and calls_adapter_method
                and path_parts[: len(CLICKHOUSE_ADAPTER_PATH_PREFIX)]
                != CLICKHOUSE_ADAPTER_PATH_PREFIX
            )
            if calls_gateway_outside_owner or calls_retired_mutator:
                faults.append(self._ctx.fault_at(location=called.location))
        return faults

    def check_published_workflow_capability(self) -> list[Fault]:
        """Report real capability construction and invalid execution signatures."""
        if self._ctx.scope() != PRODUCT_SCOPE_NAME:
            return []
        path_parts: tuple[str, ...] = self._ctx.repo_relative_parts()
        imports: tuple[ImportFact, ...] = self._ctx.facts.references().imports
        capability_spellings: frozenset[str] = self._imported_symbol_spellings(
            imports=imports,
            module_parts=WORKFLOW_MODELS_MODULE_PARTS,
            symbol=PUBLISHED_WORKFLOW_CONSTRUCTOR_NAME,
        )
        faults: list[Fault] = []
        called: NamedCallFact
        for called in self._ctx.facts.named_calls():
            if (
                self._call_matches_spellings(called=called, spellings=capability_spellings)
                and path_parts != BUILD_WORKFLOW_PUBLICATION_PATH
            ):
                faults.append(self._ctx.fault_at(location=called.location))
        if path_parts == BUILD_WORKFLOW_EXECUTION_PATH and not self._has_exact_execution_signature(
            capability_spellings=capability_spellings,
            imports=imports,
        ):
            faults.append(self._ctx.path_fault())
        return faults

    def check_workflow_consumer_purity(self) -> list[Fault]:
        """Report workflow derivation decisions in publication and execution consumers."""
        if self._ctx.scope() != PRODUCT_SCOPE_NAME:
            return []
        if self._ctx.repo_relative_parts() not in WORKFLOW_CONSUMER_PATHS:
            return []
        faults: list[Fault] = []
        called: NamedCallFact
        for called in self._ctx.facts.named_calls():
            base_name: str | None = (
                called.reference.base_name if called.reference is not None else None
            )
            calls_prohibited_decision: bool = (
                base_name in WORKFLOW_CONSUMER_PROHIBITED_CALLS
                or bool(
                    base_name
                    and (
                        base_name.startswith(WORKFLOW_PLAN_CALL_PREFIX)
                        or base_name.startswith(WORKFLOW_RENDER_CALL_PREFIX)
                        or WORKFLOW_TOPOLOGICAL_CALL_FRAGMENT in base_name
                    )
                )
            )
            if calls_prohibited_decision:
                faults.append(self._ctx.fault_at(location=called.location))
        return faults

    def check_workflow_statement_ownership(self) -> list[Fault]:
        """Report real workflow statement construction outside approved assemblers."""
        if self._ctx.scope() != PRODUCT_SCOPE_NAME:
            return []
        path_parts: tuple[str, ...] = self._ctx.repo_relative_parts()
        statement_spellings: frozenset[str] = self._imported_symbol_spellings(
            imports=self._ctx.facts.references().imports,
            module_parts=WORKFLOW_MODELS_MODULE_PARTS,
            symbol=WORKFLOW_STATEMENT_CONSTRUCTOR_NAME,
        )
        faults: list[Fault] = []
        called: NamedCallFact
        for called in self._ctx.facts.named_calls():
            if (
                self._call_matches_spellings(called=called, spellings=statement_spellings)
                and path_parts not in WORKFLOW_ASSEMBLER_PATHS
            ):
                faults.append(self._ctx.fault_at(location=called.location))
        return faults

    @staticmethod
    def _imported_symbol_spellings(
        *, imports: tuple[ImportFact, ...], module_parts: tuple[str, ...], symbol: str
    ) -> frozenset[str]:
        spellings: set[str] = set()
        imported: ImportFact
        for imported in imports:
            for alias in imported.aliases:
                imported_parts: tuple[str, ...] = (
                    imported.module_parts + alias.imported_parts
                    if imported.from_import
                    else alias.imported_parts
                )
                if imported_parts == module_parts + (symbol,):
                    spellings.add(alias.bound_name)
                if imported_parts == module_parts:
                    if imported.from_import or alias.bound_name != module_parts[-1]:
                        spellings.add(f"{alias.bound_name}.{symbol}")
                    spellings.add(".".join(module_parts + (symbol,)))
        return frozenset(spellings)

    def _proven_clickhouse_type_spellings(
        self, *, imports: tuple[ImportFact, ...]
    ) -> frozenset[str]:
        spellings: frozenset[str] = self._imported_symbol_spellings(
            imports=imports,
            module_parts=CLICKHOUSE_CONNECTION_MODULE_PARTS,
            symbol=CLICKHOUSE_CONNECTION_SYMBOL,
        )
        if not spellings:
            return frozenset()
        connection_analysis: Any = self._ctx.project.analysis(
            requester=self._ctx.path,
            path=self._ctx.repo_root.joinpath(*CLICKHOUSE_CONNECTION_PATH),
        )
        if connection_analysis is None:
            return frozenset()
        adapter_spellings: frozenset[str] = self._imported_symbol_spellings(
            imports=connection_analysis.facts.references().imports,
            module_parts=ADAPTER_CONNECTION_MODULE_PARTS,
            symbol=ADAPTER_CONNECTION_SYMBOL,
        )
        declaration: ClassDeclarationFact
        for declaration in connection_analysis.facts.class_declarations():
            if declaration.name == CLICKHOUSE_CONNECTION_SYMBOL and any(
                base_name in adapter_spellings for base_name in declaration.base_names
            ):
                return spellings
        return frozenset()

    def _adapter_class_names(self, *, adapter_type_spellings: frozenset[str]) -> frozenset[str]:
        class_names: set[str] = set()
        declaration: ClassDeclarationFact
        declarations: tuple[ClassDeclarationFact, ...] = self._ctx.facts.class_declarations()
        for _ in range(len(declarations) + 1):
            for declaration in declarations:
                if any(
                    base_name in adapter_type_spellings or base_name in class_names
                    for base_name in declaration.base_names
                ):
                    class_names.add(declaration.name)
        return frozenset(class_names)

    def _adapter_bindings(
        self, *, adapter_type_spellings: frozenset[str]
    ) -> tuple[frozenset[tuple[int, str]], frozenset[tuple[int, str]]]:
        receiver_names: set[tuple[int, str]] = set()
        handle: SyntaxHandle
        for handle in self._ctx.syntax.handles(kind="arg"):
            children: tuple[SyntaxHandle, ...] = self._ctx.relations.children(handle)
            if (
                children
                and self._ctx.text.slice(self._ctx.syntax.range(children[0]))
                in adapter_type_spellings
            ):
                parameter_name: str = (
                    self._ctx.text.slice(self._ctx.syntax.range(handle)).partition(":")[0].strip()
                )
                receiver_names.add((self._function_scope_line(handle=handle), parameter_name))
        for handle in self._ctx.syntax.handles(kind="AnnAssign"):
            children = self._ctx.relations.children(handle)
            if (
                len(children) >= ANNOTATED_ASSIGNMENT_CHILD_COUNT
                and self._ctx.text.slice(self._ctx.syntax.range(children[1]))
                in adapter_type_spellings
            ):
                receiver_names.add(
                    (
                        self._function_scope_line(handle=handle),
                        self._ctx.text.slice(self._ctx.syntax.range(children[0])),
                    )
                )
        gateway_aliases: set[tuple[int, str]] = set()
        assignments: tuple[AssignmentReferenceFact, ...] = self._ctx.facts.assignment_references()
        for _ in range(len(assignments) + 1):
            assignment: AssignmentReferenceFact
            for assignment in assignments:
                reference: QualifiedReferenceFact | None = assignment.value_reference
                if reference is None:
                    continue
                scope_line: int = (
                    assignment.owning_function.location.line
                    if assignment.owning_function is not None
                    else 0
                )
                source_is_receiver: bool = (
                    len(reference.parts) == 1 and (scope_line, reference.parts[0]) in receiver_names
                )
                source_is_gateway: bool = reference.base_name == WORKFLOW_GATEWAY_CALL_NAME and (
                    (scope_line, reference.receiver_base_name or "") in receiver_names
                    or ".".join(reference.parts[:-1]) in adapter_type_spellings
                )
                target_name: str
                for target_name in assignment.target_names:
                    if source_is_receiver:
                        receiver_names.add((scope_line, target_name))
                    if source_is_gateway:
                        gateway_aliases.add((scope_line, target_name))
        return frozenset(receiver_names), frozenset(gateway_aliases)

    def _function_scope_line(self, *, handle: SyntaxHandle) -> int:
        ancestor: SyntaxHandle
        for ancestor in self._ctx.relations.ancestors(handle):
            if self._ctx.syntax.kind(ancestor) in FUNCTION_DEFINITION_SYNTAX_KINDS:
                return self._ctx.syntax.range(ancestor).start.line
        return 0

    @staticmethod
    def _call_scope_key(*, called: NamedCallFact) -> tuple[int, str]:
        scope_line: int = called.owning_function.location.line if called.owning_function else 0
        base_name: str = (called.reference.base_name or "") if called.reference is not None else ""
        return scope_line, base_name

    @staticmethod
    def _is_adapter_method_call(
        *,
        called: NamedCallFact,
        adapter_type_spellings: frozenset[str],
        adapter_classes: frozenset[str],
        receiver_names: frozenset[tuple[int, str]],
    ) -> bool:
        reference: QualifiedReferenceFact | None = called.reference
        if reference is None or len(reference.parts) < METHOD_REFERENCE_MINIMUM_PARTS:
            return False
        scope_line: int = called.owning_function.location.line if called.owning_function else 0
        receiver_name: str = reference.receiver_base_name or ""
        static_receiver: str = ".".join(reference.parts[:-1])
        class_receiver: bool = bool(
            called.owning_class
            and called.owning_class.name in adapter_classes
            and receiver_name in ADAPTER_CLASS_RECEIVER_NAMES
        )
        return (
            (scope_line, receiver_name) in receiver_names
            or static_receiver in adapter_type_spellings
            or class_receiver
        )

    @staticmethod
    def _call_matches_spellings(*, called: NamedCallFact, spellings: frozenset[str]) -> bool:
        reference: QualifiedReferenceFact | None = called.reference
        return reference is not None and ".".join(reference.parts) in spellings

    def _has_exact_execution_signature(
        self,
        *,
        capability_spellings: frozenset[str],
        imports: tuple[ImportFact, ...],
    ) -> bool:
        function_line: int | None = None
        for function in self._ctx.facts.functions().top_level:
            if function.name == BUILD_WORKFLOW_EXECUTION_FUNCTION:
                function_line = function.location.line
        if function_line is None:
            return False
        function_handle: SyntaxHandle | None = None
        for handle in self._ctx.syntax.handles(kind="FunctionDef"):
            if self._ctx.syntax.range(handle).start.line == function_line:
                function_handle = handle
        if function_handle is None:
            return False
        parameter_contract: list[tuple[str, str]] = []
        for handle in self._ctx.syntax.handles(kind="arg"):
            if function_handle not in self._ctx.relations.ancestors(handle):
                continue
            children: tuple[SyntaxHandle, ...] = self._ctx.relations.children(handle)
            parameter_name: str = (
                self._ctx.text.slice(self._ctx.syntax.range(handle)).partition(":")[0].strip()
            )
            annotation: str = (
                self._ctx.text.slice(self._ctx.syntax.range(children[0])) if children else ""
            )
            parameter_contract.append((parameter_name, annotation))
        adapter_spellings: frozenset[str] = self._imported_symbol_spellings(
            imports=imports,
            module_parts=ADAPTER_CONNECTION_MODULE_PARTS,
            symbol=ADAPTER_CONNECTION_SYMBOL,
        )
        return (
            tuple(name for name, _ in parameter_contract) == BUILD_WORKFLOW_EXECUTION_PARAMETERS
            and parameter_contract[0][1] in capability_spellings
            and parameter_contract[1][1] in adapter_spellings
        )
