# Library Inspector UX Pattern Research

Research date: 2026-06-14

Research conducted during Phase 3 planning.

## 1. Executive Summary

PhotoPrism has the most relevant overall pattern for this gallery app because it is a web photo library with separate cards, mosaic, and list result views, lightweight search filters, visible index state, and metadata available through a details/edit surface. Lightroom is the best reference for metadata density, filtering concepts, and right-sidebar inspection, but most of its Library module is too broad for a personal read-only AI art gallery. digiKam is the clearest validation that a table-style inspector with thumbnail rows and metadata columns is useful for comparison work. Immich is less relevant for table design because its UX is primarily timeline/grid/detail oriented, but it is useful as a reference for keeping search simple while exposing richer metadata only in a detail panel.

## 2. Key Findings by App

### Adobe Lightroom — Library Module

Applicable patterns:

- Lightroom treats the grid as the main browsing workspace. The center area shows thumbnail cells; side panels and bottom filmstrip provide context and navigation around that selected set.
- Grid cells can show compact or expanded metadata. Expanded cells can show filename and several configurable metadata labels, while icons, rating, color labels, and flags sit around the thumbnail. This supports the idea that a visual thumbnail plus a small set of high-value fields is enough for fast scanning.
- The Library Filter bar is a strong model for separating filter types:
  - Text searches indexed metadata.
  - Attribute filters by flags, ratings, color labels, copy status, and similar state.
  - Metadata displays a column browser where each column lists values and counts, such as date, camera, lens, or location.
- The Metadata filter's value-count pattern is useful, but only as a future facet model. For this gallery, model and sampler are the only obvious high-value facets in Phase 3.
- The right sidebar groups Quick Develop, Keywording, Keyword List, Metadata, and Comments. For a read-only metadata list, the relevant pattern is field/value inspection in a collapsible right-side panel, not edit controls.
- The filmstrip provides persistent access to the current source/collection while users move between modules or detail modes. It is useful in Lightroom because Library, Develop, and other modules share selection state.
- Lightroom Classic's documented Library views are Grid, Loupe, Compare, Survey, and People. It does not present a spreadsheet-style Library List as a core view; table/list behavior is better modeled by PhotoPrism or digiKam.

Overkill for this app:

- Full Text/Attribute/Metadata filter modes with multi-column metadata browsers.
- Filter presets and complex saved filters.
- Quick Develop editing controls.
- Keyword taxonomy panels, batch metadata writing, metadata sync, color labels, flags, and star workflows unless the app later adds curation workflows.
- Filmstrip navigation. The GalleryGrid already owns primary browsing, and duplicating a persistent thumbnail strip in a secondary table would add visual weight.

Key screenshot descriptions:

- Library Grid layout: a dark workspace with source panels on the left, a large central thumbnail grid, a right sidebar with Quick Develop and Metadata sections, a toolbar/filter area above the grid, and a horizontal filmstrip at the bottom.
- Expanded grid cell: thumbnail centered in a cell, small metadata labels above or below it, rating/label/flag indicators near the edges, and small badges for state. The visual image remains dominant.
- Library Filter bar: a horizontal strip above the grid with Text, Attribute, Metadata, and None modes. Metadata mode expands into adjacent value columns with counts, functioning like a compact faceted browser.
- Metadata panel: a right-sidebar accordion with a preset selector and dense field/value rows. It is optimized for inspection and editing, but the same field/value structure works read-only.

### PhotoPrism — Search & Explore

Relevant patterns for metadata list:

- PhotoPrism's search results support multiple display modes: cards, mosaic, and list. This is the clearest reference for separating an immersive browsing view from a metadata-heavy utility view.
- Cards show image previews with selected metadata such as title, time, and location. Mosaic prioritizes visual browsing. List mode is the most relevant pattern for Phase 3 because it trades visual richness for scanability.
- Search uses a simple global query field with structured filters such as field:value terms. The advanced/expanded search form exposes common facets without forcing every user into a dense filter builder.
- PhotoPrism shows library and indexing state, including counts and indexing progress. For this gallery, a small "N indexed photos" and "last indexed" line would be more useful than a full indexing dashboard.
- Metadata is available through photo details/edit surfaces rather than forcing every field into result cards. This supports keeping `MetadataList.vue` columns narrow and moving long metadata into a detail panel or existing preview.
- Browse categories such as albums, calendar, labels, folders, places, and moments show that navigation can be categorical without every category becoming a table column.

What to avoid:

- Do not copy PhotoPrism's full media-management surface: albums, labels, people, places, review/archive/private state, bulk edit, and multi-file stacks are larger than the Phase 3 scope.
- Do not add cards/list/mosaic toggles inside the metadata list for MVP. The app already has `GalleryGrid` as the primary visual mode; the new list should be a separate utility view.
- Do not make the filter UI a full advanced search form initially. Start with one global search and add one or two high-value facets only if the data warrants it.

### Immich — Search & Metadata

Relevant patterns:

- Immich's search combines simple entry points with advanced filters for metadata such as filename, description, tags, location, camera make/model, lens, date range, media type, archive/favorite state, album presence, and rating.
- Immich keeps photo browsing visual-first: timeline/grid pages are the primary interaction model, while richer metadata appears in asset detail surfaces.
- Asset details expose metadata and related entities such as tags and faces in context, rather than trying to make a table carry every field.
- Immich's external library behavior reinforces a useful product cue: indexed libraries should communicate when the index is current and what content is included.
- Immich does not emphasize a spreadsheet-like list view for normal browsing. That supports treating this app's metadata list as a secondary inspector rather than a replacement for grid browsing.

What is over-engineered for this app:

- CLIP-style semantic search, OCR, people/faces, map/location browsing, reverse geocoding, and album/favorite/archive filters are not necessary for a read-only AI art metadata list.
- Mobile backup/storage-state indicators are not relevant unless this app later gains synchronization or multi-device ingestion.

### DigiKam / Darktable (brief)

Useful OSS patterns:

- digiKam's Table-View is the closest OSS pattern for Phase 3: rows contain thumbnails, and columns can show file and metadata fields for comparison. It validates the idea of a dense utility table alongside a primary thumbnail/icon view.
- digiKam's right sidebar metadata view uses filter modes, live search, and field/value metadata groups. That is a good reference for an optional selected-row inspector, but it is too much for Phase 3 unless the existing detail view cannot cover the need.
- digiKam's customizable columns are powerful, but they should be deferred. A fixed set of AI-art columns is enough for a personal gallery.
- darktable's lighttable view uses adjustable thumbnail density, collection filters, and side panels for filtering/tagging/metadata editing. The useful pattern is not the module complexity; it is the split between visual lighttable, collection filtering, and metadata side panels.
- darktable's collection filters are broad, including file path, filename, tag, metadata, time, camera, lens, exposure, and ISO. For this app, the equivalent should be a much smaller filter set: name, folder, model, sampler, seed, dimensions, and modified date.

## 3. Patterns to Adopt for Phase 3

### P0 — Must have

- Keep the metadata list as a secondary utility view. `GalleryGrid` remains the primary browsing UI.
- Use a dense table with stable row height, a square thumbnail, and fixed high-value columns.
- Show columns in this order: thumbnail, name, folder, model, sampler, seed, dimensions, modified date.
- Provide single-column sorting by clicking headers, with a visible sort direction indicator.
- Default sort to modified date descending so new imports are easy to inspect.
- Add one global search input above the table. Search across name, folder, model, sampler, and seed.
- Show a compact result/index count, for example "1,284 indexed photos" and "412 shown".
- Row click should open the existing preview/detail entry point or select the asset for detail inspection.
- Keep the view read-only. No inline metadata editing, no batch actions, no destructive row controls.

### P1 — Should have

- Add optional facet chips or dropdown filters for model, sampler, and folder if the data set is large enough to justify them.
- Add sticky column headers for long lists.
- Use table virtualization if the indexed result set regularly exceeds a few thousand rows.
- Add a selected-row detail drawer only if the existing photo detail surface does not expose model, sampler, seed, dimensions, and file metadata clearly.
- Provide copy actions for seed and filename/path through small icon buttons or a row action menu.
- Add keyboard navigation for up/down selection and Enter to open.
- Add a compact density mode if row height becomes a constraint on desktop.

### P2 — Nice to have

- Saved filters for repeated searches such as a specific model or folder.
- Column visibility preferences after users prove they need them.
- CSV export for offline auditing.
- Per-column filters.
- Multi-sort.
- Histogram/count facets for model and sampler.
- "Open in grid" behavior that jumps from a row to the same image in `GalleryGrid`.

## 4. Patterns to Explicitly Skip

- Lightroom-style Metadata Filter column browser. It is excellent for large professional catalogs, but too complex for a personal AI art gallery MVP.
- Lightroom Quick Develop and any editing controls. Phase 3 is read-only.
- A persistent filmstrip. It solves cross-module navigation in Lightroom, but duplicates the app's primary gallery navigation.
- Full DAM taxonomy: keywords, labels, flags, ratings, color classes, review/archive/private workflows, and batch metadata writing.
- Immich-style people, face, OCR, location, and semantic search features.
- PhotoPrism-style full advanced search form at launch.
- User-configurable table columns in MVP. Fixed columns reduce implementation cost and support a clear product opinion.
- Grid/list/card toggle inside `MetadataList.vue`. The app already has a grid. The list should do one job well.
- Multi-sort in MVP. Single-sort is easier to understand and enough for the planned columns.

## 5. Specific Recommendations for Our MetadataList.vue

Columns to show and why:

- Thumbnail: fast visual disambiguation between similar file names.
- Name: primary identifier and the field most likely to be searched.
- Folder: useful for understanding generation batches, imports, or project grouping.
- Model: high-value AI art metadata and likely a common comparison field.
- Sampler: important generation parameter, useful for quality/debug comparisons.
- Seed: useful for reproducibility and exact lookup; keep it copyable.
- Dimensions: quickly separates aspect ratios and resolutions.
- Modified date: supports recent-import review and troubleshooting.

Column ordering:

1. Thumbnail
2. Name
3. Folder
4. Model
5. Sampler
6. Seed
7. Dimensions
8. Modified date

Sorting UX:

- Use click-to-sort headers.
- Use a single active sort column.
- Show an arrow or chevron in the sorted header.
- Cycle ascending/descending on repeated clicks.
- Do not implement multi-sort for MVP.
- Default: modified date descending.

Filter/search UX:

- Use one global search field above the table.
- Search name, folder, model, sampler, and seed.
- Debounce input.
- Include a clear button.
- Show result counts next to the search field.
- Add model/sampler/folder facets later only if global search becomes insufficient.
- Avoid per-column filters for MVP.

Thumbnail size and density:

- Use 48 px or 56 px square thumbnails.
- Use `object-fit: cover` with a stable square container.
- Target row height around 64 to 72 px.
- Do not overlay metadata on thumbnails in the table. Keep metadata in columns.
- Truncate long names and folders with tooltips or a detail surface; do not let rows grow vertically by default.

Toggle between grid and list:

- Skip in MVP.
- `GalleryGrid` is already the visual browsing mode.
- `MetadataList.vue` should be an explicit inspector/list view entry point, not a mode toggle competing with the grid.

Row actions and entry points:

- Entry point: add a sidebar/nav item or toolbar entry labeled "Metadata" or "Library Inspector".
- Primary row action: click opens the existing photo preview/detail view.
- Secondary actions: copy seed, copy filename/path, and optionally reveal/open in grid.
- Avoid inline edit, delete, retag, batch select, and destructive actions in Phase 3.

## 6. Comparison: Our Plan vs Industry Patterns

| Feature               | Phase 3 Plan                                             | Lightroom                                            | PhotoPrism                                | Immich                            | Recommendation                             |
| --------------------- | -------------------------------------------------------- | ---------------------------------------------------- | ----------------------------------------- | --------------------------------- | ------------------------------------------ |
| Primary browsing      | Existing `GalleryGrid`                                   | Library Grid                                         | Mosaic/cards/search results               | Timeline/grid                     | Keep grid primary                          |
| Metadata list/table   | Planned lightweight list                                 | No core spreadsheet list; grid cell metadata instead | Has list view for results                 | Not a main concept                | Build a dedicated utility table            |
| Thumbnail in rows     | Planned                                                  | Grid thumbnails with overlays                        | List/cards include previews               | Timeline thumbnails               | Use 48-56 px stable thumbnails             |
| Core metadata columns | Name, folder, model, sampler, seed, dimensions, modified | Camera/IPTC/EXIF oriented                            | Title/time/location/camera/files          | Date/location/camera/tags         | Use AI-art-specific columns                |
| Sorting               | Header click                                             | Sort controls in Library                             | Search/order controls                     | Timeline/search ordering          | Single-sort headers, default modified desc |
| Global search         | Planned                                                  | Text filter                                          | Main search input with structured filters | Search page with advanced filters | P0 global search                           |
| Faceted filtering     | Not MVP                                                  | Metadata column browser with counts                  | Advanced filters/facets                   | Advanced metadata filters         | P1 model/sampler/folder only               |
| Metadata detail panel | Optional                                                 | Right Metadata panel                                 | Details/edit panels                       | Asset detail info                 | Reuse existing detail view first           |
| Index status/count    | Planned lightweight count                                | Catalog/source counts                                | Library/index counts and progress         | Library scan/job concepts         | Show indexed and visible counts            |
| Grid/list toggle      | Skip MVP                                                 | Grid/Loupe/Compare/Survey, not table toggle          | Cards/mosaic/list toggle                  | Grid-first                        | Skip toggle; separate view is enough       |
| Column customization  | Skip MVP                                                 | Configurable grid labels and metadata presets        | View choices, not table column config     | Not central                       | Defer                                      |
| Editing/batch actions | Skip                                                     | Extensive metadata/edit workflows                    | Edit, organize, review/archive            | Tags, albums, metadata features   | Keep read-only                             |
| Filmstrip             | Skip                                                     | Persistent bottom filmstrip                          | Not central                               | Not central                       | Skip                                       |

## 7. Appendix: URLs Referenced

Adobe Lightroom:

- https://helpx.adobe.com/lightroom-classic/help/library-module-basic-workflow.html
- https://helpx.adobe.com/lightroom-classic/help/finding-photos-catalog.html
- https://helpx.adobe.com/lightroom-classic/help/setting-library-view-options.html
- https://helpx.adobe.com/lightroom-classic/help/workspace-basics.html
- https://helpx.adobe.com/lightroom-classic/help/metadata-basics-actions.html
- https://helpx.adobe.com/lightroom-classic/help/using-quick-develop-panel.html
- https://community.adobe.com/t5/lightroom-classic-ideas/p-list-view-for-library/idi-p/12251117

PhotoPrism:

- https://docs.photoprism.app/user-guide/search/
- https://docs.photoprism.app/user-guide/search/views/
- https://docs.photoprism.app/user-guide/search/filters/
- https://docs.photoprism.app/user-guide/organize/browse/
- https://docs.photoprism.app/user-guide/organize/edit/
- https://docs.photoprism.app/user-guide/library/
- https://docs.photoprism.app/user-guide/library/originals/
- https://docs.photoprism.app/getting-started/first-steps/
- https://docs.photoprism.app/user-guide/settings/content/

Immich:

- https://docs.immich.app/features/searching/
- https://docs.immich.app/features/tags/
- https://docs.immich.app/features/facial-recognition/
- https://docs.immich.app/features/libraries/
- https://docs.immich.app/administration/jobs-workers/
- https://docs.immich.app/features/mobile-app/

digiKam and darktable:

- https://www.digikam.org/documentation/faq/
- https://docs.digikam.org/en/setup_application/views_settings.html
- https://docs.digikam.org/en/right_sidebar/metadata_view.html
- https://docs.darktable.org/usermanual/development/en/lighttable/lighttable-view-layout/
- https://docs.darktable.org/usermanual/development/en/lighttable/lighttable-modes/filemanager/
- https://docs.darktable.org/usermanual/development/en/module-reference/utility-modules/shared/collections/
- https://docs.darktable.org/usermanual/development/en/module-reference/utility-modules/shared/filmstrip/

## 8. Adopted/Rejected Outcomes

Verified against `frontend/src/components/LibraryInspector.vue` on 2026-06-18.
The implemented component is named `LibraryInspector.vue`; historical
`MetadataList.vue` references in this research describe the planning concept.

Adopted:

- A dedicated `/metadata` Library Inspector separate from the primary gallery
  grid.
- TanStack Table column definitions with TanStack Virtual row virtualization.
- Read-only rows with thumbnail/file identity, prompt preview, model/tool, seed,
  dimensions, modified time, and lazy detail/actions.
- Search, scope, model, prompt-presence, and sort controls.
- Indexed counts/status and detail-on-demand metadata rather than reparsing every
  original while rendering the table.

Rejected or deferred:

- A grid/list toggle inside the inspector.
- Lightroom-style multi-column metadata filter browser.
- Inline metadata editing, batch actions, ratings, flags, tags, and destructive
  actions.
- User-configurable columns and multi-sort.
- Persistent filmstrip and Immich-style people/face/OCR/location features.
