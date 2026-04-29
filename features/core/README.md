# core-llm-clients

Multi-vendor LLM client abstraction. Provides a single `LLMClient`
protocol with four backend implementations: Azure OpenAI, OpenAI
direct, Ollama local, Anthropic.

In Phase A.1 only the Azure OpenAI backend is fully implemented. The
other three are protocol-conformant skeletons; they are exercised by
HTTP-mocked tests but have no integration smoke until a real consumer
needs them.

See spec: `../../docs/superpowers/specs/2026-04-28-a1-llm-clients-design.md`.
