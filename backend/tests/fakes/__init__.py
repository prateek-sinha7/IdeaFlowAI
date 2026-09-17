"""In-memory fakes for external services.

Fakes model enough of a provider's OBSERVABLE behaviour that production code can
run against them unmodified -- as opposed to mocks, which assert on calls. Only
the network boundary is replaced.
"""
