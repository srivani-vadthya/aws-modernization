"""Local, declarative agent capability registry. Definitions do not start agents."""
from .models import AgentAvailability, AgentDefinition


_CATEGORIES = ("backend", "frontend", "database", "api", "integration", "configuration", "build", "testing", "documentation")


def _agent(category: str, name: str) -> AgentDefinition:
    return AgentDefinition(agentId=f"{category}-modernization-agent", name=name,
        description=f"Specialist for evidence-based {category} modernization planning and review.",
        taskCategories=[category], sourceTechnologies=[], targetTechnologies=[],
        requiredInputArtifacts=["module-context-package", "modernization-plan"],
        expectedOutputTypes=["implementation-proposal", "validation-findings"],
        requiredSkillsOrTemplates=[], dependencies=[],
        capabilityMetadata={"execution": "not-enabled", "mode": "proposal-only"}, availability=AgentAvailability.AVAILABLE)


_REGISTRY = [_agent(category, category.replace("-", " ").title() + " Agent") for category in _CATEGORIES]


def list_agents() -> list[AgentDefinition]:
    return list(_REGISTRY)


def candidates(category: str, source: list[str], target: list[str], templates_present: bool) -> list[AgentDefinition]:
    # Empty technology lists mean a generic specialist; it is not a claim of technology support.
    return [agent for agent in _REGISTRY if agent.availability is AgentAvailability.AVAILABLE
            and category in agent.taskCategories and (templates_present or not agent.requiredSkillsOrTemplates)]
