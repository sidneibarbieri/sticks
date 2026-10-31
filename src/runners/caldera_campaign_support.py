"""Declared single-target transport scopes; execution qualification is separate."""

from types import MappingProxyType

from runners.caldera_lab_bootstrap import CalderaAgentIdentity

CALDERA_AGENT_IDENTITIES = MappingProxyType({
    "0.c0010": CalderaAgentIdentity(),
    "0.c0026": CalderaAgentIdentity(),
    "0.shadowray": CalderaAgentIdentity(principal="rayuser"),
})
SUPPORTED_CALDERA_CAMPAIGNS = frozenset(CALDERA_AGENT_IDENTITIES)
