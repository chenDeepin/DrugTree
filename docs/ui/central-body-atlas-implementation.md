# DrugTree — Central Body Atlas Implementation Guide

> Purpose: give OpenCode / Codex / manual implementation a concrete, copy-paste-friendly target for the next UI round.

---

## 1. Goal

Refactor the current frontend from a **sidebar filter dashboard** into a **central body atlas**.

### Desired result
- The **human body is the hero visual** in the center of the page
- **ATC tags float around the body** and feel spatially anchored to tissues / disease zones
- **Drug cards appear below** the body atlas, not beside it
- The page feels like a **medical atlas / knowledge map**, not a CRUD dashboard

---

## 2. Visual hierarchy

### Priority order
1. **Body** = primary visual focus
2. **Floating ATC tags** = secondary navigation layer
3. **Results grid** = below, supporting exploration
4. **Detail modal/panel** = deep dive only on click

### Core rule
Do not let cards or filters compete with the body.

---

## 3. Wireframe

```text
┌──────────────────────────────────────────────────────────────────────┐
│  🌳 DrugTree            [ Search drugs / disease / target ]  Public ▾ │
│                         [ Clear ]                         [Scientist] │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│                        ATLAS HERO SECTION                            │
│                                                                      │
│         [N Nervous]                              [S Sensory]         │
│                                                                      │
│                [R Respiratory]    [C Cardiovascular]                 │
│                                                                      │
│                          ┌──────────────┐                            │
│         [L Antineoplastic]   HUMAN BODY  [B Blood/Immune]           │
│                          │    CENTER    │                            │
│          [D Skin]        │              │        [H Hormones]       │
│                          └──────────────┘                            │
│                                                                      │
│            [A Alimentary]   [E/Metabolic-ish zone]  [G GU/Breast]   │
│                                                                      │
│          [M Musculoskeletal]              [Kidney/Urinary zone]      │
│                                                                      │
│              [P Antiparasitic]            [V Various]                │
│                                                                      │
│      Hover tag/region → preview • Click → lock • Results below      │
├──────────────────────────────────────────────────────────────────────┤
│  ACTIVE FILTERS: [L Antineoplastic ×] [Brain/CNS ×]                 │
├──────────────────────────────────────────────────────────────────────┤
│  RESULTS                                                              │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐         │
│  │ Drug Card  │ │ Drug Card  │ │ Drug Card  │ │ Drug Card  │         │
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘         │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 4. Suggested DOM structure

```html
<body>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand">🌳 DrugTree</div>

      <div class="search-wrap">
        <input type="text" placeholder="Search drug, disease, target..." />
      </div>

      <div class="topbar-actions">
        <button class="clear-btn">Clear</button>

        <div class="mode-switch">
          <button class="mode-btn active">Public</button>
          <button class="mode-btn">Scientist</button>
        </div>
      </div>
    </header>

    <main class="page-main">
      <section class="atlas-hero">
        <div class="atlas-stage">

          <div class="atlas-body-wrap">
            <img src="assets/human-body.svg" class="atlas-body" />
            <div class="body-hotspots">
              <!-- optional absolute-position organ hotspots -->
            </div>
          </div>

          <div class="atc-orbit-layer">
            <button class="atc-tag atc-n">N Nervous</button>
            <button class="atc-tag atc-c">C Cardio</button>
            <button class="atc-tag atc-r">R Respiratory</button>
            <button class="atc-tag atc-a">A Alimentary</button>
            <button class="atc-tag atc-l">L Oncology</button>
            <button class="atc-tag atc-b">B Blood</button>
            <button class="atc-tag atc-d">D Skin</button>
            <button class="atc-tag atc-g">G GU/Breast</button>
            <button class="atc-tag atc-h">H Hormones</button>
            <button class="atc-tag atc-m">M Musculoskeletal</button>
            <button class="atc-tag atc-p">P Parasites</button>
            <button class="atc-tag atc-s">S Sensory</button>
            <button class="atc-tag atc-v">V Various</button>
            <button class="atc-tag atc-j">J Anti-infectives</button>
          </div>

          <div class="atlas-hint">
            Hover tag/region to preview · Click to lock
          </div>
        </div>
      </section>

      <section class="active-filters-bar">
        <div class="filter-chip">L Antineoplastic ×</div>
        <div class="filter-chip">Brain/CNS ×</div>
      </section>

      <section class="results-section">
        <div class="results-header">
          <h2>Matching Drugs</h2>
          <span class="result-count">24 results</span>
        </div>

        <div class="drug-grid">
          <!-- cards -->
        </div>
      </section>
    </main>

    <div class="drug-detail-modal hidden">
      <!-- detail view -->
    </div>
  </div>
</body>
```

---

## 5. CSS skeleton

### Base shell

```css
body {
  margin: 0;
  font-family: Inter, system-ui, sans-serif;
  background: #0f172a;
  color: #e5eefc;
}

.app-shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}
```

### Top bar

```css
.topbar {
  display: grid;
  grid-template-columns: 180px 1fr auto;
  align-items: center;
  gap: 16px;
  padding: 16px 24px;
  position: sticky;
  top: 0;
  z-index: 20;
  background: rgba(10, 14, 30, 0.85);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid rgba(255,255,255,0.08);
}
```

### Main page

```css
.page-main {
  display: flex;
  flex-direction: column;
  gap: 18px;
}
```

### Hero atlas container

```css
.atlas-hero {
  min-height: 72vh;
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 20px 24px 8px;
}

.atlas-stage {
  width: min(1200px, 96vw);
  min-height: 68vh;
  position: relative;
  border-radius: 28px;
  background:
    radial-gradient(circle at center, rgba(68,120,255,0.18), transparent 35%),
    linear-gradient(180deg, #11182d 0%, #0b1020 100%);
  box-shadow: 0 20px 80px rgba(0,0,0,0.35);
  overflow: hidden;
}
```

### Center body

```css
.atlas-body-wrap {
  position: absolute;
  inset: 0;
  display: flex;
  justify-content: center;
  align-items: center;
  pointer-events: none;
}

.atlas-body {
  width: min(420px, 36vw);
  max-height: 78%;
  filter: drop-shadow(0 0 28px rgba(94, 160, 255, 0.22));
  pointer-events: auto;
}
```

### Floating ATC layer

```css
.atc-orbit-layer {
  position: absolute;
  inset: 0;
}

.atc-tag {
  position: absolute;
  padding: 10px 14px;
  border-radius: 999px;
  border: 1px solid rgba(255,255,255,0.12);
  background: rgba(255,255,255,0.08);
  color: white;
  font-weight: 600;
  cursor: pointer;
  backdrop-filter: blur(10px);
  transition: transform 0.2s ease, box-shadow 0.2s ease, opacity 0.2s ease;
}

.atc-tag:hover {
  transform: translateY(-2px) scale(1.03);
  box-shadow: 0 0 18px rgba(255,255,255,0.15);
}

.atc-tag.is-active {
  box-shadow: 0 0 22px currentColor;
  transform: scale(1.04);
}

.atc-tag.is-muted {
  opacity: 0.35;
}
```

### Results section

```css
.results-section {
  width: min(1200px, 96vw);
  margin: 0 auto 40px;
}

.drug-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
}
```

---

## 6. ATC floating-tag positioning map

Use an explicit config object in JS.

```js
const ATC_TAG_LAYOUT = {
  N: { top: '10%', left: '20%', anchorRegion: 'brain_cns' },
  S: { top: '12%', right: '18%', anchorRegion: 'eye_ear' },
  R: { top: '28%', right: '24%', anchorRegion: 'lung_respiratory' },
  C: { top: '30%', left: '26%', anchorRegion: 'heart_vascular' },
  B: { top: '40%', right: '14%', anchorRegion: 'blood_immune' },
  L: { top: '40%', left: '14%', anchorRegion: 'blood_immune' },
  D: { top: '52%', right: '20%', anchorRegion: 'skin' },
  H: { top: '52%', right: '8%', anchorRegion: 'endocrine_metabolic' },
  A: { top: '62%', left: '24%', anchorRegion: 'stomach_upper_gi' },
  G: { top: '66%', right: '20%', anchorRegion: 'reproductive_breast' },
  M: { bottom: '16%', left: '18%', anchorRegion: 'bone_joint_muscle' },
  P: { bottom: '10%', left: '26%', anchorRegion: 'systemic_multiorgan' },
  V: { bottom: '10%', right: '22%', anchorRegion: 'systemic_multiorgan' },
  J: { top: '44%', left: '72%', anchorRegion: 'lung_respiratory' }
};
```

### Positioning rule
- Position ATC tags by **dominant body relevance**, not perfect biology.
- Symbolic placement is acceptable if it improves readability.

---

## 7. Body region model

```js
const BODY_REGIONS = {
  brain_cns: { label: 'Brain / CNS', selector: '#region-brain' },
  eye_ear: { label: 'Eye / Ear', selector: '#region-eye-ear' },
  lung_respiratory: { label: 'Lung / Respiratory', selector: '#region-lungs' },
  heart_vascular: { label: 'Heart / Vascular', selector: '#region-heart' },
  blood_immune: { label: 'Blood / Immune', selector: '#region-blood' },
  stomach_upper_gi: { label: 'Stomach / Upper GI', selector: '#region-upper-gi' },
  intestine_colorectal: { label: 'Intestine / Colorectal', selector: '#region-lower-gi' },
  liver_biliary_pancreas: { label: 'Liver / Biliary / Pancreas', selector: '#region-liver-pancreas' },
  endocrine_metabolic: { label: 'Endocrine / Metabolic', selector: '#region-endocrine' },
  kidney_urinary: { label: 'Kidney / Urinary', selector: '#region-kidney' },
  reproductive_breast: { label: 'Reproductive / Breast', selector: '#region-pelvis' },
  bone_joint_muscle: { label: 'Bone / Joint / Muscle', selector: '#region-limbs' },
  skin: { label: 'Skin', selector: '#region-skin' },
  systemic_multiorgan: { label: 'Systemic / Multi-organ', selector: '#region-whole-body' }
};
```

---

## 8. State model

Use one clean state object.

```js
const state = {
  uiMode: 'public',
  selectedATC: null,
  hoveredATC: null,
  lockedRegion: null,
  hoveredRegion: null,
  searchQuery: '',
  selectedDrugId: null
};
```

---

## 9. Interaction rules

### Hover ATC tag
- highlight corresponding body region
- show quick preview count
- do not lock state

### Click ATC tag
- set `selectedATC`
- visually lock tag
- pre-highlight anchor region(s)
- clicking same tag again clears it

### Hover body region
- if no locked region: preview region intersection
- if locked region exists: glow only, do not override locked results

### Click body region
- set `lockedRegion`
- filter cards by `selectedATC ∩ lockedRegion`
- clicking same region again unlocks it

### Clear button
- reset selected ATC
- reset locked region
- clear search
- return to default result state

---

## 10. Public vs Scientist card design

### Public card
```text
[thumbnail]
Drug name
Treats: glioma / leukemia / reflux
ATC: L
Year: 2001
```

### Scientist card
```text
[thumbnail]
Drug name
Class: EGFR inhibitor
Targets: EGFR
ATC: L01
MW: 499.6
Year: 2015
```

### Rule
Do not change page structure between modes.
Only change **information density**.

---

## 11. Minimal implementation sequence

### Pass 1
- central body layout
- floating ATC tags
- results below

### Pass 2
- hover glow / click lock behavior
- tag ↔ body anchoring interaction

### Pass 3
- improved Public / Scientist cards
- empty-state polish

### Pass 4
- atmospheric background
- subtle motion
- optional connection halos/lines

---

## 12. Practical advice for OpenCode / Codex

### Do this
- keep layout with **absolute-positioned tag layer**
- use **one large atlas container**
- store tag positions in JS config
- use CSS variables for ATC colors
- keep body map center stage

### Avoid this
- sidebar-first layout
- results beside body
- too much anatomy detail in first pass
- overcomplicated SVG before layout hierarchy works

---

## 13. Fastest acceptable implementation target

If implementation time is limited, the next round should at minimum do these 4 edits:

1. make `main` vertical instead of two-column
2. create `.atlas-stage` with large centered body
3. convert ATC filters into absolutely positioned floating tags
4. move results grid below the atlas

If these four are done well, the page should already feel much closer to the intended vision.

---

## 14. Suggested prompt for OpenCode / Codex

```text
Refactor the DrugTree frontend into a central-body atlas layout.

Goals:
1. Make the human body the main hero visual centered on the page.
2. Replace sidebar/toolbar ATC buttons with floating ATC tags positioned around the body.
3. Keep ATC tags spatially anchored to their dominant body/tissue context.
4. Move the drug results grid below the atlas section.
5. Preserve existing filtering logic, Public/Scientist mode, and detail modal behavior.
6. Use a dark/atmospheric atlas hero background.
7. Keep implementation simple, clean, and desktop-first.

Implementation constraints:
- Use existing project structure where possible.
- Prefer config-driven ATC tag positions.
- Do not build a new framework layer.
- Keep interactions deterministic.

Deliver:
- updated HTML structure
- updated CSS for atlas hero layout
- updated JS state wiring for ATC tags and body regions
- no regressions in filtering/search/detail modal
```

---

## 15. File placement suggestion

If you want a clean implementation split, use:

```text
src/frontend/
  index.html
  css/
    style.css
    atlas.css
  js/
    app.js
    atlas.js
    body-map.js
    floating-tags.js
```

But if speed matters more than elegance, merging into existing files is acceptable.

---

## 16. Final principle

DrugTree should feel like:
- **an atlas first**
- **a filter tool second**
- **a chemistry explorer underneath**

If the body is not visually dominant, the implementation is not yet correct.

---

## 17. Visual Art Direction Brief

> This section is for OpenCode / Codex / manual implementation when the goal is not just correctness, but **feel**.

### Core aesthetic target
DrugTree should feel like:
- a **medical atlas**
- a **scientific constellation map**
- a **clean future-facing biotech interface**

It should **not** feel like:
- a CRUD dashboard
- an admin panel
- a left-sidebar enterprise tool
- a plain anatomy textbook page

---

## 18. Emotional / visual keywords

Use these words as design anchors:
- luminous
- precise
- calm
- clinical
- immersive
- spatial
- futuristic but not sci-fi cheesy
- elegant
- high-contrast
- body-centered

---

## 19. Hero scene art direction

### Main composition
The first thing the user should notice is:
1. a **large central human silhouette / body illustration**
2. subtle glowing anatomical emphasis
3. floating ATC tags orbiting / hovering around the body
4. a sense of spatial intelligence

### Scene balance
The scene should feel:
- open and breathable
- not cluttered
- not too many boxes competing for attention
- dark enough for glow effects to work
- bright enough for scientific clarity

### Body treatment
The body should feel:
- central
- slightly luminous
- clean and elegant
- more like an atlas illustration than clip art

Recommended look:
- soft blue-white glow
- subtle organ/tissue highlight overlays
- slightly translucent or haloed edges
- high visual separation from background

---

## 20. Background direction

### Preferred background
Use a layered dark background, for example:
- deep navy
- blue-black
- soft vignette
- subtle radial glow behind the body

### Optional texture ideas
Keep subtle. Avoid visual noise.
Possible accents:
- faint grid
- molecular-dot constellation pattern
- soft contour lines
- ultra-light network lines

### Avoid
- busy particle fields
- aggressive sci-fi neon
- overdone glassmorphism everywhere
- bright gradients that overpower the body

---

## 21. ATC tag visual style

ATC tags should feel like **floating medical markers**, not buttons from a form.

### Recommended tag characteristics
- pill-shaped or softly rounded
- semi-translucent
- category-colored border or glow
- short label with strong typography
- slight floating/shadow depth

### Tag states
#### Default
- visible, elegant, lightly glowing
- not too bright

#### Hover
- slightly enlarge
- stronger glow
- region highlight activates

#### Active / selected
- stronger outline/glow
- visually anchored/locked
- should feel “engaged” in the atlas

#### Muted
- faded but still legible
- never fully disappear unless intentionally filtered out

### Label style
Prefer compact labels such as:
- `L Oncology`
- `N Nervous`
- `C Cardio`
- `R Respiratory`

Not too verbose on the floating tags.
Details can appear elsewhere.

---

## 22. Motion design

Motion should be subtle and purposeful.

### Recommended motion
- soft hover lift on tags
- gentle glow pulse on active tissues
- smooth fade/scale transitions
- slight easing on filter updates

### Good motion principles
- 180–300ms transitions for UI interactions
- pulse/glow cycles should be slow and quiet
- body should feel stable, not animated like a game object

### Avoid
- bouncing tags
- spinning orbits
- heavy parallax
- flashy transitions that distract from information

---

## 23. Color direction

### Base palette
- background: deep navy / near-black blue
- foreground text: soft white / cool light gray
- secondary text: muted blue-gray
- hero glow: cool cyan / soft medical blue

### ATC category colors
Keep current category distinction, but tune them for harmony on a dark background.
They should be:
- saturated enough to differentiate
- not overly neon
- readable when used as glow/border accents

### Recommendation
Use color primarily in:
- ATC tag border/glow
- body region highlight
- active filter chips
- subtle card accents

Not in giant background blocks.

---

## 24. Typography direction

Typography should feel modern, clinical, and readable.

### Recommended style
- modern sans-serif
- medium to bold for labels
- restrained hierarchy
- avoid decorative fonts

### Hierarchy
- page title: bold, clean, not oversized
- ATC tags: compact bold
- cards: readable, dense but not cramped
- summaries: softer contrast

### Tone
It should feel like:
- biotech product
- knowledge tool
- atlas interface

Not like:
- marketing landing page
- casual consumer app

---

## 25. Spacing and composition rules

### Main rule
Whitespace is part of the design.

### Apply this by:
- keeping generous air around the body
- not packing too many tags too close
- leaving visual breathing room between hero and results
- avoiding dense card walls immediately under the body

### Recommended composition behavior
- body gets the center and largest quiet zone
- tags orbit at readable distances
- cards start below a clear dividing threshold

---

## 26. Card art direction

Cards should support the atlas, not overpower it.

### Public cards
- cleaner
- softer contrast
- summary-forward
- small structure thumbnail

### Scientist cards
- denser
- slightly sharper contrast
- technical metadata visible but disciplined

### Card style
- dark-surface cards or soft frosted panels
- rounded corners
- fine border
- gentle hover lift
- small accent glow on active/selected states

### Avoid
- heavy white cards if atlas section is dark
- thick borders
- visually loud card shadows

---

## 27. Detail modal art direction

The detail view should feel like opening a specimen / dossier.

### It should be
- larger structure view
- clean information grouping
- easy to scan
- mode-sensitive (Public vs Scientist)

### Visual tone
- dark or dark-light balanced panel
- restrained highlights
- scientific clarity over decoration

---

## 28. “Looks right” checklist

The implementation is visually on target only if most of these feel true:

- the body is clearly the first thing the eye sees
- ATC tags feel like part of the body scene
- the interface feels immersive, not dashboard-like
- hovering makes the atlas feel alive
- the layout feels premium and intentional
- cards support exploration without stealing the stage
- the whole scene feels biotech / scientific / elegant

---

## 29. “Looks wrong” checklist

The implementation has drifted if any of these happen:

- the body looks small or secondary
- tags feel like random floating buttons
- the page looks like a sidebar admin panel
- cards visually dominate the hero area
- too much bright color destroys focus
- motion feels flashy or game-like
- the scene feels crowded or noisy

---

## 30. Suggested prompt extension for OpenCode / Codex

Use this in addition to the implementation prompt if visual feel is the priority:

```text
In addition to implementing the central-body atlas layout, prioritize visual art direction.

The page should feel like a premium medical atlas / biotech knowledge interface.
Use a dark atmospheric hero background, a luminous centered body, and floating ATC tags that feel spatially anchored rather than form-like buttons.

Keep motion subtle and elegant. Avoid dashboard aesthetics, busy panels, and generic enterprise layout. The body must remain the visual focal point, with results supporting it from below.

Aim for: calm, clinical, immersive, luminous, high-contrast, spatial, elegant.
Avoid: cluttered, boxy, admin-like, noisy, flashy sci-fi.
```

---

## 31. Final instruction for implementation agents

When in doubt, choose:
- **clarity over complexity**
- **atmosphere over dashboard density**
- **body-centered composition over filter-panel convenience**
- **progressive disclosure over immediate data overload**

If the page feels like an atlas first, the design is moving in the right direction.
