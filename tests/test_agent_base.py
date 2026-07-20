from __future__ import annotations

from dataclasses import asdict

from intelliticket_backend.services.agents.base import AgentCapability
from intelliticket_backend.services.agents.context import ContextRetrievalAgent
from intelliticket_backend.services.agents.diagnosis import DiagnosisAgent
from intelliticket_backend.services.agents.intake import IntakeAgent
from intelliticket_backend.services.agents.report import ReportAgent
from intelliticket_backend.services.agents.routing import RoutingAgent


def test_all_agent_metadata_is_serializable() -> None:
    expected = {
        "ticket_intake_agent": AgentCapability.TICKET_INTAKE,
        "context_retrieval_agent": AgentCapability.CONTEXT_RETRIEVAL,
        "diagnosis_agent": AgentCapability.DIAGNOSIS,
        "routing_agent": AgentCapability.ROUTING,
        "report_agent": AgentCapability.REPORT,
    }
    agents = [
        IntakeAgent(),
        ContextRetrievalAgent(),
        DiagnosisAgent(),
        RoutingAgent(),
        ReportAgent(),
    ]

    for agent in agents:
        metadata = agent.get_metadata()
        dumped = asdict(metadata)
        assert metadata.name in expected
        assert metadata.capabilities == [expected[metadata.name]]
        assert dumped["name"] == metadata.name
        assert dumped["description"]
        assert "repository" not in dumped
        assert "client" not in dumped
        assert "db" not in dumped
