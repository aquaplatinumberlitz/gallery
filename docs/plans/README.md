# Plans

Status: Maintained index

Last reviewed: 2026-07-13

This directory is reserved for proposed, active, or blocked implementation
plans.

Proposed plans, in required execution order:

1. [Search Hardening Implementation Plan](SEARCH_HARDENING_IMPLEMENTATION_PLAN.md)
   - P0-P1 correctness, query-plan, latency, ranking, pagination, FastAPI
     contracts, and Vue search UX.
2. [Search Discovery Evolution Implementation Plan](SEARCH_DISCOVERY_EVOLUTION_IMPLEMENTATION_PLAN.md)
   - Search V2, shareable/saved queries, index lifecycle, prompt usage,
     diffusion model identity, ComfyUI properties, and opt-in raw workflow search.
3. [Semantic Search Implementation Plan](SEARCH_SEMANTIC_IMPLEMENTATION_PLAN.md)
   - Optional local ML sidecar, semantic and similar-image retrieval, and
     experimental hybrid ranking.

The discovery plan starts only after all hardening gates pass. The semantic
plan starts only after hardening and the discovery index-lifecycle foundation
pass. Raw workflow, semantic, and hybrid modes are implemented by their plans
but remain disabled by default.

Completed or superseded plans live in [Archived Documentation](../archived/README.md).
