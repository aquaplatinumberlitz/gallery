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
     diffusion model identity, and optional ComfyUI/raw-workflow extensions.
3. [Related Assets and Generation Discovery Plan](RELATED_ASSETS_IMPLEMENTATION_PLAN.md)
   - Prompt ingredients, generation families, explainable metadata relations,
     and optional Pillow-only visual-variant fingerprints.

The discovery plan starts only after all hardening gates pass. Related Assets
starts after the D0-D2 discovery foundations and their applicable validation
gates pass. ComfyUI property and raw-workflow extensions require explicit user
approval and do not block Related Assets. No semantic ML, model sidecar, vector
database, or hybrid ranking is planned.

Completed or superseded plans live in [Archived Documentation](../archived/README.md).
