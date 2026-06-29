"""Build the deepagents research agent (Azure GPT-4.1). Heavy imports are function-local
so importing this module (or the backend) never pulls deepagents/langchain unless the
agent path actually runs — keeps the `agent` extra optional."""

import os
from datetime import datetime


def build_agent():
    """Construct the compiled deepagents graph. Requires the `agent` extra installed."""
    from deepagents import create_deep_agent
    from langchain_openai import AzureChatOpenAI

    from local_pdf.agent.prompts import (
        RESEARCH_WORKFLOW_INSTRUCTIONS,
        RESEARCHER_INSTRUCTIONS,
        SUBAGENT_DELEGATION_INSTRUCTIONS,
    )
    from local_pdf.agent.tools import azure_ai_search, think_tool

    current_date = datetime.now().strftime("%Y-%m-%d")

    model = AzureChatOpenAI(
        azure_endpoint=os.environ["AI_FOUNDRY_ENDPOINT"],
        azure_deployment=os.environ["CHAT_DEPLOYMENT_NAME"],
        api_key=os.environ["AI_FOUNDRY_KEY"],
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
        temperature=0.0,
    )

    research_sub_agent = {
        "name": "research-agent",
        "description": (
            "Delegate research to the sub-agent researcher. "
            "Only give this researcher one topic at a time."
        ),
        "system_prompt": RESEARCHER_INSTRUCTIONS.format(date=current_date),
        "tools": [azure_ai_search, think_tool],
    }

    instructions = (
        RESEARCH_WORKFLOW_INSTRUCTIONS
        + "\n\n"
        + "=" * 80
        + "\n\n"
        + SUBAGENT_DELEGATION_INSTRUCTIONS.format(
            max_concurrent_research_units=3,
            max_researcher_iterations=3,
        )
    )

    return create_deep_agent(
        model=model,
        tools=[azure_ai_search, think_tool],
        system_prompt=instructions,
        subagents=[research_sub_agent],
    )


def _build_model():
    """Azure GPT-4.1 chat model from our AI_FOUNDRY_* env (shared by the verifier)."""
    from langchain_openai import AzureChatOpenAI

    return AzureChatOpenAI(
        azure_endpoint=os.environ["AI_FOUNDRY_ENDPOINT"],
        azure_deployment=os.environ["CHAT_DEPLOYMENT_NAME"],
        api_key=os.environ["AI_FOUNDRY_KEY"],
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
        temperature=0.0,
    )


def build_verifier_agent():
    """Flat (no sub-agents) step-by-step provenance verifier. Requires the `agent` extra.

    Flat on purpose: every step streams from the main loop instead of being hidden in a
    delegated sub-agent (the opposite of the research agent's design).
    """
    from deepagents import create_deep_agent

    from local_pdf.agent.tools import azure_ai_search, record_step
    from local_pdf.agent.verify_prompts import PROVENANZ_VERIFY

    current_date = datetime.now().strftime("%Y-%m-%d")
    return create_deep_agent(
        model=_build_model(),
        tools=[azure_ai_search, record_step],
        system_prompt=PROVENANZ_VERIFY.format(date=current_date),
    )
