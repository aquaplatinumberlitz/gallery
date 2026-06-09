# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: tests/perf/lightbox.perf.spec.ts >> lightbox opens first photo within budget
- Location: tests/perf/lightbox.perf.spec.ts:35:1

# Error details

```
Error: expect(received).toBe(expected) // Object.is equality

Expected: true
Received: false
```

# Page snapshot

```yaml
- generic [ref=e1]:
  - generic [ref=e2]:
    - generic [ref=e3]:
      - complementary [ref=e4]:
        - generic [ref=e5]:
          - generic [ref=e6]: ROOT PATH
          - generic [ref=e7]:
            - img [ref=e8]
            - textbox "ROOT PATH" [ref=e10]:
              - /placeholder: Enter folder path...
              - text: /home/ubuntu/gallery-repo
            - button "Reset path" [ref=e11] [cursor=pointer]:
              - img [ref=e12]
          - paragraph [ref=e15]:
            - img [ref=e16]
            - text: Press Enter to load
        - generic [ref=e18]:
          - generic [ref=e20]: Folder Tree
          - generic [ref=e21]:
            - generic [ref=e23] [cursor=pointer]:
              - button [ref=e24]:
                - img [ref=e25]
              - img [ref=e27]
              - generic [ref=e29]: backend
            - generic [ref=e31] [cursor=pointer]:
              - button [ref=e32]:
                - img [ref=e33]
              - img [ref=e35]
              - generic [ref=e37]: docs
            - generic [ref=e39] [cursor=pointer]:
              - button [ref=e40]:
                - img [ref=e41]
              - img [ref=e43]
              - generic [ref=e45]: frontend
            - generic [ref=e47] [cursor=pointer]:
              - button [ref=e48]:
                - img [ref=e49]
              - img [ref=e51]
              - generic [ref=e53]: scripts
            - generic [ref=e55] [cursor=pointer]:
              - button [ref=e56]:
                - img [ref=e57]
              - img [ref=e59]
              - generic [ref=e61]: test mika
            - generic [ref=e63] [cursor=pointer]:
              - button [ref=e64]:
                - img [ref=e65]
              - img [ref=e67]
              - generic [ref=e69]: test-images
      - button "Hide Sidebar" [ref=e70] [cursor=pointer]:
        - img [ref=e71]
      - generic [ref=e73]:
        - generic [ref=e74]:
          - button "Change Intro Page" [ref=e76] [cursor=pointer]:
            - img [ref=e77]
          - generic [ref=e80]:
            - img [ref=e82]
            - generic [ref=e84]:
              - paragraph [ref=e85]: Local collections
              - heading "Museum Art Gallery" [level=1] [ref=e86]:
                - img [ref=e87]
                - text: Museum Art Gallery
          - generic [ref=e89]:
            - button "Switch to Dark mode" [ref=e90] [cursor=pointer]:
              - generic [ref=e91]:
                - img [ref=e93]
                - img [ref=e95]
                - img [ref=e97]
            - generic [ref=e99]:
              - img [ref=e100]
              - searchbox "Photos, albums, prompts" [ref=e103]
              - combobox "Search scope" [ref=e104] [cursor=pointer]:
                - option "This folder" [selected]
                - option "All indexed"
        - generic [ref=e106]:
          - generic [ref=e107]:
            - generic [ref=e108]:
              - button "Back" [ref=e109] [cursor=pointer]:
                - img [ref=e110]
              - button "Forward" [disabled] [ref=e112]:
                - img [ref=e113]
            - navigation [ref=e115]:
              - list [ref=e116]:
                - listitem [ref=e117]:
                  - img [ref=e118]
                - listitem [ref=e121]:
                  - button "home" [ref=e122] [cursor=pointer]:
                    - generic [ref=e123]: home
                - listitem [ref=e124]:
                  - img [ref=e126]
                - listitem [ref=e128]:
                  - button "ubuntu" [ref=e129] [cursor=pointer]:
                    - generic [ref=e130]: ubuntu
                - listitem [ref=e131]:
                  - img [ref=e133]
                - listitem [ref=e135]:
                  - button "gallery-repo" [ref=e136] [cursor=pointer]:
                    - generic [ref=e137]: gallery-repo
                - listitem [ref=e138]:
                  - img [ref=e140]
                - listitem [ref=e142]:
                  - button "test mika" [disabled] [ref=e143]:
                    - generic [ref=e144]: test mika
            - button "Open current folder in file explorer" [ref=e145] [cursor=pointer]:
              - img [ref=e146]
            - button "Name" [ref=e150] [cursor=pointer]:
              - img [ref=e151]
              - generic [ref=e154]: Name
              - img [ref=e155]
            - button "6 cols" [ref=e158] [cursor=pointer]:
              - img [ref=e159]
              - generic [ref=e164]: 6 cols
              - img [ref=e165]
          - generic [ref=e168]:
            - button "Expand albums" [ref=e170] [cursor=pointer]:
              - generic [ref=e171]:
                - heading "Albums" [level=3] [ref=e172]
                - generic [ref=e173]:
                  - img [ref=e174]
                  - text: "2"
                  - img [ref=e176]
            - generic [ref=e178]:
              - heading "Photos" [level=3] [ref=e179]
              - generic [ref=e180]:
                - img [ref=e181]
                - text: "50"
            - generic [ref=e186]:
              - generic [ref=e187]:
                - img "0 (1).png" [ref=e189] [cursor=pointer]
                - img "0 (2).png" [ref=e191] [cursor=pointer]
                - img "0 (3).png" [ref=e193] [cursor=pointer]
                - img "0 (4).png" [ref=e195] [cursor=pointer]
                - img "1 (2).png" [ref=e197] [cursor=pointer]
                - img "1bae29ccb0d89b736d225feb7a1b8646.jpg" [ref=e199] [cursor=pointer]
              - generic [ref=e200]:
                - img "2f05bfe4-0cf8-42af-97ab-e18a8dd58188.png" [ref=e202] [cursor=pointer]
                - img "3dfde158-a11b-4fa1-810c-daa078adabe3.png" [ref=e204] [cursor=pointer]
                - img "3ffa50b4-ad18-4102-ad38-2745f7c706c6.png" [ref=e206] [cursor=pointer]
                - img "4.png" [ref=e208] [cursor=pointer]
                - img "4a2339ff-2692-4cc4-94de-dbe1319d2954.png" [ref=e210] [cursor=pointer]
                - img "4c09d540-b341-4e12-9479-c70d3243e16f.png" [ref=e212] [cursor=pointer]
              - generic [ref=e213]:
                - img "32211c9c-aab8-4b52-8eab-7721d4b9c5a1 - Copy (2).jpg" [ref=e215] [cursor=pointer]
                - img "32211c9c-aab8-4b52-8eab-7721d4b9c5a1 - Copy (3).jpg" [ref=e217] [cursor=pointer]
                - img "32211c9c-aab8-4b52-8eab-7721d4b9c5a1 - Copy.jpg" [ref=e219] [cursor=pointer]
                - img "32211c9c-aab8-4b52-8eab-7721d4b9c5a1.jpg" [ref=e221] [cursor=pointer]
                - img "5853242a-772f-4475-8d69-3744926f88f1 - Copy (2).png" [ref=e223] [cursor=pointer]
                - img "5853242a-772f-4475-8d69-3744926f88f1 - Copy (3).png" [ref=e225] [cursor=pointer]
              - generic [ref=e226]:
                - img "5853242a-772f-4475-8d69-3744926f88f1 - Copy.png" [ref=e228] [cursor=pointer]
                - img "5853242a-772f-4475-8d69-3744926f88f1.png" [ref=e230] [cursor=pointer]
                - img "a6d97ef5-fbb8-4b6f-804e-9ad45fc7b081 - Copy (2).png" [ref=e232] [cursor=pointer]
                - img "a6d97ef5-fbb8-4b6f-804e-9ad45fc7b081 - Copy (3).png" [ref=e234] [cursor=pointer]
                - img "a6d97ef5-fbb8-4b6f-804e-9ad45fc7b081 - Copy.png" [ref=e236] [cursor=pointer]
                - img "a6d97ef5-fbb8-4b6f-804e-9ad45fc7b081.png" [ref=e238] [cursor=pointer]
              - generic [ref=e239]:
                - img "a111.png" [ref=e241] [cursor=pointer]
                - img "a (1) - Copy.png" [ref=e243] [cursor=pointer]
                - img "a (1).png" [ref=e245] [cursor=pointer]
                - img "a (2) - Copy.png" [ref=e247] [cursor=pointer]
                - img "a (3) - Copy.png" [ref=e249] [cursor=pointer]
                - img "a (4) - Copy.png" [ref=e251] [cursor=pointer]
              - generic [ref=e252]:
                - img "a (4).png" [ref=e254] [cursor=pointer]
                - img "a (5) - Copy.png" [ref=e256] [cursor=pointer]
                - img "a (6) - Copy.png" [ref=e258] [cursor=pointer]
                - img "ai meta (2) - Copy.png" [ref=e260] [cursor=pointer]
                - img "ai meta (2).png" [ref=e262] [cursor=pointer]
                - img "ai meta (3) - Copy.png" [ref=e264] [cursor=pointer]
              - generic [ref=e265]:
                - img "ai meta (3).png" [ref=e267] [cursor=pointer]
                - img "ai meta (4) - Copy.png" [ref=e269] [cursor=pointer]
                - img "c33cfb59-e304-4f64-ba33-482b70058007.jpeg" [ref=e271] [cursor=pointer]
                - img "ComfyUI_00002_.png" [ref=e273] [cursor=pointer]
                - img "ComfyUI_00004_.png" [ref=e275] [cursor=pointer]
                - img "d4dbd258-8f47-4848-8231-ef624d864e46.jpg" [ref=e277] [cursor=pointer]
              - generic [ref=e278]:
                - img "db5503da-2519-4475-bb4d-cdd7225e925a.png" [ref=e280] [cursor=pointer]
                - img "f71c447d-1245-41ed-af95-44da8e763757.jpg" [ref=e282] [cursor=pointer]
                - img "forge.png" [ref=e284] [cursor=pointer]
                - img "pexels-ahmetyuksek-34961714.jpg" [ref=e286] [cursor=pointer]
                - img "pexels-alex-ning-523843601-34919500.jpg" [ref=e288] [cursor=pointer]
                - img "pexels-pixabay-326055.jpg" [ref=e290] [cursor=pointer]
              - generic [ref=e291]:
                - img "pexels-qtaibs-9200614.jpg" [ref=e293] [cursor=pointer]
                - generic [ref=e294] [cursor=pointer]:
                  - img "tumblr_ku2pvuJkJG1qz9qooo1_r1_400.webp" [ref=e295]
                  - generic: GIF
    - generic [ref=e298]:
      - img [ref=e300]
      - button "Open Tanstack query devtools" [ref=e348] [cursor=pointer]:
        - img [ref=e349]
  - generic [ref=e397]:
    - dialog [active] [ref=e399]:
      - generic [ref=e401]:
        - generic [ref=e402]:
          - group [ref=e403]:
            - img [ref=e404]
          - group [ref=e405]:
            - img "0 (1).png" [ref=e406]
          - group [ref=e407]:
            - img [ref=e408]
        - generic:
          - generic [ref=e409]: 1 / 50
          - generic [ref=e410]:
            - img
        - button "Previous" [ref=e411] [cursor=pointer]:
          - img
        - button "Next" [ref=e412] [cursor=pointer]:
          - img
    - generic: 1 / 50
    - generic [ref=e413]: Image 1 of 50
    - complementary [ref=e414]:
      - generic [ref=e415]:
        - generic [ref=e416]:
          - heading "0 (1).png" [level=3] [ref=e417]
          - generic [ref=e418]:
            - button "Toggle fullscreen" [ref=e419] [cursor=pointer]:
              - img [ref=e420]
            - button "Close lightbox" [ref=e425] [cursor=pointer]:
              - img [ref=e426]
        - generic [ref=e429]:
          - generic [ref=e430]:
            - img [ref=e431]
            - text: 850 x 565
          - generic [ref=e436]:
            - generic [ref=e437]: SOURCE
            - generic [ref=e438]: Unknown
      - generic [ref=e439]:
        - generic [ref=e440]:
          - heading "Prompt" [level=4] [ref=e442]:
            - img [ref=e443]
            - text: Prompt
          - paragraph [ref=e445]: No prompt metadata
        - generic [ref=e446]:
          - heading "Negative" [level=4] [ref=e448]:
            - img [ref=e449]
            - text: Negative
          - paragraph [ref=e453]: No negative prompt
        - generic [ref=e454]:
          - button "Generation Data" [disabled]:
            - heading "Generation Data" [level=4]:
              - img
              - text: Generation Data
          - paragraph [ref=e455]: No generation parameters
        - generic [ref=e456]:
          - button "Model & Resources" [disabled]:
            - heading "Model & Resources" [level=4]:
              - img
              - text: Model & Resources
          - paragraph [ref=e457]: No model/resource metadata found
```

# Test source

```ts
  23  |   }
  24  | 
  25  |   const album = page.getByText(albumName, { exact: false }).first();
  26  |   await expect(album).toBeVisible({ timeout: 15000 });
  27  |   await album.click();
  28  | 
  29  |   const firstPhoto = page.getByTestId("photo-card").first();
  30  |   await expect(firstPhoto).toBeVisible({ timeout: 15000 });
  31  | 
  32  |   return firstPhoto;
  33  | }
  34  | 
  35  | test("lightbox opens first photo within budget", async ({ page }) => {
  36  |   const clickTime = { value: 0 };
  37  |   const tracker = installApiNetworkTracker(page, clickTime);
  38  | 
  39  |   await navigateToAlbum(page);
  40  | 
  41  |   const firstPhoto = page.getByTestId("photo-card").first();
  42  | 
  43  |   tracker.clear();
  44  |   clickTime.value = Date.now();
  45  | 
  46  |   await firstPhoto.click();
  47  | 
  48  |   const lightbox = page.getByTestId("lightbox");
  49  |   await expect(lightbox).toBeVisible({ timeout: 10000 });
  50  |   const lightboxVisibleAfterClickMs = Date.now() - clickTime.value;
  51  | 
  52  |   const lightboxImg = lightbox.locator(".pswp__img").first();
  53  |   await expect.poll(async () => {
  54  |     return await lightboxImg.evaluate((img: HTMLImageElement) => ({
  55  |       complete: img.complete,
  56  |       naturalW: img.naturalWidth,
  57  |       naturalH: img.naturalHeight,
  58  |     }));
  59  |   }, { timeout: 10000 }).toMatchObject({ complete: true });
  60  |   const mainImageLoadedAfterClickMs = Date.now() - clickTime.value;
  61  | 
  62  |   const allThumbnailSamples = tracker.thumbnailSamples();
  63  |   const imageSamples = tracker.imageSamples();
  64  |   const metadataSamples = tracker.metadataSamples();
  65  | 
  66  |   const highResThumbnailSamples = allThumbnailSamples.filter(s => {
  67  |     const maxSize = getQueryParam(s.search, "max_size");
  68  |     return maxSize && Number(maxSize) >= 800;
  69  |   });
  70  |   const firstThumbSample = highResThumbnailSamples.find(s => s.durationMs && s.durationMs > 0);
  71  |   const firstImageSample = imageSamples.find(s => s.durationMs && s.durationMs > 0);
  72  |   const usedFullImageEndpoint = firstImageSample?.pathname === "/api/image";
  73  | 
  74  |   const dims = await lightboxImg.evaluate((img: HTMLImageElement) => ({
  75  |     naturalW: img.naturalWidth,
  76  |     naturalH: img.naturalHeight,
  77  |     displayW: img.getBoundingClientRect().width,
  78  |     displayH: img.getBoundingClientRect().height,
  79  |   }));
  80  | 
  81  |   const viewport = page.viewportSize();
  82  | 
  83  |   const actualSrc = await lightboxImg.getAttribute("src");
  84  |   const srcIsFullImage = actualSrc?.startsWith("/api/image") ?? false;
  85  | 
  86  |   const report = {
  87  |     albumName,
  88  |     albumPath,
  89  |     open: {
  90  |       lightboxVisibleAfterClickMs,
  91  |       mainImageLoadedAfterClickMs,
  92  |       mainImageRequestStartAfterClickMs: Math.round((firstImageSample ?? firstThumbSample)?.startMs ?? 0),
  93  |       mainImageRequestDurationMs: Math.round((firstImageSample ?? firstThumbSample)?.durationMs ?? 0),
  94  |       metadataDurationMs: metadataSamples.length ? Math.round(Math.min(...metadataSamples.map(s => s.durationMs ?? 0))) : 0,
  95  |       usedFullImageEndpoint,
  96  |       srcIsFullImage,
  97  |       naturalWidth: dims.naturalW,
  98  |       naturalHeight: dims.naturalH,
  99  |       displayWidth: Math.round(dims.displayW),
  100 |       displayHeight: Math.round(dims.displayH),
  101 |       viewportWidth: viewport?.width ?? 0,
  102 |       viewportHeight: viewport?.height ?? 0,
  103 |     },
  104 |     budgets: {
  105 |       openVisibleMs: Number(process.env.GALLERY_PERF_LIGHTBOX_OPEN_BUDGET_MS ?? "1500"),
  106 |       openImageLoadedMs: Number(process.env.GALLERY_PERF_LIGHTBOX_IMAGE_BUDGET_MS ?? "4000"),
  107 |     },
  108 |     verdict: "pass",
  109 |   };
  110 | 
  111 |   console.log(JSON.stringify(report, null, 2));
  112 | 
  113 |   if (dims.displayW < (viewport?.width ?? 1920) * 0.5 && dims.displayH < (viewport?.height ?? 1080) * 0.5) {
  114 |     console.warn(`WARNING: Lightbox image (${Math.round(dims.displayW)}×${Math.round(dims.displayH)}px) is smaller than 50% of viewport (${viewport?.width}×${viewport?.height}px). Image may be displaying a thumbnail instead of full-res.`);
  115 |   }
  116 | 
  117 |   expect(lightboxVisibleAfterClickMs).toBeLessThanOrEqual(report.budgets.openVisibleMs);
  118 |   expect(mainImageLoadedAfterClickMs).toBeLessThanOrEqual(report.budgets.openImageLoadedMs);
  119 |   expect(dims.naturalW).toBeGreaterThan(0);
  120 |   expect(dims.naturalH).toBeGreaterThan(0);
  121 |   expect(dims.displayW).toBeGreaterThan(300);
  122 |   expect(dims.displayH).toBeGreaterThan(300);
> 123 |   expect(usedFullImageEndpoint).toBe(true);
      |                                 ^ Error: expect(received).toBe(expected) // Object.is equality
  124 |   expect(srcIsFullImage).toBe(true);
  125 | });
  126 | 
  127 | test("lightbox transitions to next image within budget", async ({ page }) => {
  128 |   const clickTime = { value: 0 };
  129 |   const tracker = installApiNetworkTracker(page, clickTime);
  130 | 
  131 |   await navigateToAlbum(page);
  132 | 
  133 |   const firstPhoto = page.getByTestId("photo-card").first();
  134 | 
  135 |   // Open lightbox by clicking first photo
  136 |   await firstPhoto.click();
  137 | 
  138 |   const lightbox = page.getByTestId("lightbox");
  139 |   await expect(lightbox).toBeVisible({ timeout: 10000 });
  140 | 
  141 |   // Wait for initial image loaded
  142 |   const lightboxImg = lightbox.locator(".pswp__img").first();
  143 |   await expect.poll(async () => {
  144 |     return await lightboxImg.evaluate((img: HTMLImageElement) => img.complete);
  145 |   }, { timeout: 10000 }).toBe(true);
  146 | 
  147 |   const beforeSrc = await lightboxImg.getAttribute("src");
  148 | 
  149 |   tracker.clear();
  150 |   clickTime.value = Date.now();
  151 | 
  152 |   await page.keyboard.press("ArrowRight");
  153 | 
  154 |   await expect.poll(async () => {
  155 |     const src = await lightboxImg.getAttribute("src");
  156 |     return src !== beforeSrc;
  157 |   }, { timeout: 5000 }).toBe(true);
  158 |   const nextVisibleAfterActionMs = Date.now() - clickTime.value;
  159 | 
  160 |   await expect.poll(async () => {
  161 |     return await lightboxImg.evaluate((img: HTMLImageElement) => img.complete);
  162 |   }, { timeout: 10000 }).toBe(true);
  163 |   const nextImageLoadedAfterActionMs = Date.now() - clickTime.value;
  164 | 
  165 |   const dims = await lightboxImg.evaluate((img: HTMLImageElement) => ({
  166 |     naturalW: img.naturalWidth,
  167 |     naturalH: img.naturalHeight,
  168 |     displayW: img.getBoundingClientRect().width,
  169 |     displayH: img.getBoundingClientRect().height,
  170 |   }));
  171 | 
  172 |   const viewport = page.viewportSize();
  173 | 
  174 |   const naturalRatio = dims.naturalW / dims.naturalH;
  175 |   const displayRatio = dims.displayW / dims.displayH;
  176 |   const ratioDiff = Math.abs(1 - naturalRatio / displayRatio);
  177 | 
  178 |   const report = {
  179 |     albumName,
  180 |     albumPath,
  181 |     transition: {
  182 |       nextVisibleAfterActionMs,
  183 |       nextImageLoadedAfterActionMs,
  184 |       naturalWidth: dims.naturalW,
  185 |       naturalHeight: dims.naturalH,
  186 |       displayWidth: Math.round(dims.displayW),
  187 |       displayHeight: Math.round(dims.displayH),
  188 |       viewportWidth: viewport?.width ?? 0,
  189 |       viewportHeight: viewport?.height ?? 0,
  190 |       ratioDiff: Math.round(ratioDiff * 1000) / 1000,
  191 |     },
  192 |     budgets: {
  193 |       transitionMs: Number(process.env.GALLERY_PERF_LIGHTBOX_TRANSITION_BUDGET_MS ?? "3000"),
  194 |     },
  195 |     verdict: "pass",
  196 |   };
  197 | 
  198 |   console.log(JSON.stringify(report, null, 2));
  199 | 
  200 |   if (dims.displayW < (viewport?.width ?? 1920) * 0.5 && dims.displayH < (viewport?.height ?? 1080) * 0.5) {
  201 |     console.warn(`WARNING: Lightbox image (${Math.round(dims.displayW)}×${Math.round(dims.displayH)}px) is smaller than 50% of viewport (${viewport?.width}×${viewport?.height}px). Image may be displaying a thumbnail instead of full-res.`);
  202 |   }
  203 | 
  204 |   expect(nextImageLoadedAfterActionMs)
  205 |     .toBeLessThanOrEqual(report.budgets.transitionMs);
  206 |   expect(dims.naturalW).toBeGreaterThan(0);
  207 |   expect(dims.naturalH).toBeGreaterThan(0);
  208 |   expect(ratioDiff).toBeLessThan(0.2);
  209 | });
  210 | 
```