"""Self-contained deepagents agents (Azure GPT-4.1 + AI Search) for the Agent tab spike."""

from local_pdf.agent.build import build_agent, build_verifier_agent

__all__ = ["build_agent", "build_verifier_agent"]
