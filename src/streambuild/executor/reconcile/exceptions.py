"""Reconcile execution exceptions."""


class ReconcileError(RuntimeError):
    """Raised when verified reconcile state cannot be persisted safely."""
