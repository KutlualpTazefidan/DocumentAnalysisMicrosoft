# Phases Overview

Status of the DocumentAnalysisMicrosoft rollout across implementation phases.

| Phase | Title | Branch | PR | Status |
|-------|-------|--------|----|---------
| A.0 | Local PDF pipeline (segmentation, extraction, review) | main | #26–#28 | ✅ Merged |
| A.1.0 | Coherence + Roles + UI Polish | feat/coherence-and-roles | #32 | In Review |

**A.0** delivered the core offline-first document analysis workflow with 2-pane PDF segmentation/extraction UI.

**A.1.0** splits the SPA into role-based shells (admin `/admin/*` in navy, curator `/curate/*` in green), adds token-based curator management, and refines UI/UX with Lucide icons, framer-motion transitions, and Radix form components.

Future phases (A-Plus, B, C, etc.) will add structured curation workflows, ML-assisted refinement, and automated evaluation pipelines.
