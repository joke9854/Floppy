"""OpenAPI schema class that publishes each operation's required token scope.

Lives apart from ``api.schema`` because DRF resolves ``DEFAULT_SCHEMA_CLASS``
while ``drf_spectacular.views`` is being imported, and ``api.schema`` imports
that module.
"""

from drf_spectacular.openapi import AutoSchema

from api.scopes import ANY_SCOPE, NEVER, resolve_required_scope


class ScopedAutoSchema(AutoSchema):
    """Annotate operations with the scope an integration token needs.

    Client authors otherwise have to guess which scopes to request, and a wrong
    guess only surfaces as a 403 at runtime.
    """

    def get_operation(self, *args, **kwargs):
        """Return the operation, annotated with its required scope."""
        operation = super().get_operation(*args, **kwargs)
        if not operation:
            return operation

        scope = resolve_required_scope(self.view, self.method)
        if scope == ANY_SCOPE:
            operation["x-required-scope"] = "any"
        elif scope == NEVER:
            operation["x-required-scope"] = "none (session or account token only)"
        elif scope:
            operation["x-required-scope"] = scope
        self._add_auth_error_responses(operation)
        return operation

    def _add_auth_error_responses(self, operation):
        """Document the 401 and 403 every authenticated operation can return.

        Spectacular adds an empty requirement to ``security`` when anonymous
        access is allowed, and omits ``security`` when the view has no
        authenticators, so neither public case gets a 401.
        """
        from drf_spectacular.utils import OpenApiResponse

        from api.authentication import HasScope
        from api.contract_serializers import DetailErrorSerializer

        security = operation.get("security")
        if not security or {} in security:
            return
        responses = operation["responses"]
        if "401" not in responses:
            responses["401"] = self._get_response_for_code(
                OpenApiResponse(
                    DetailErrorSerializer,
                    description="Credentials are missing, invalid, or expired.",
                ),
                "401",
            )
        has_scope_check = any(
            isinstance(permission, HasScope) for permission in self.view.get_permissions()
        )
        if has_scope_check and "403" not in responses:
            responses["403"] = self._get_response_for_code(
                OpenApiResponse(
                    DetailErrorSerializer,
                    description="The token does not hold the scope this operation requires.",
                ),
                "403",
            )
