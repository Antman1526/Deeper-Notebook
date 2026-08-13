# Responsive Working Desk Design

## Problem

At compact desktop window sizes such as 1020 by 631 CSS pixels, the Working Desk's primary column is narrowed by the navigation and Runtime Status columns. The Quick Actions layout still uses viewport breakpoints, so it can select four columns even when its own container is only wide enough for one or two. Action labels and descriptions are consequently clipped or rendered as unusably narrow word fragments. Short windows also consume excessive vertical space before the action area.

## Chosen approach

Use the actual Working Desk container as the responsive authority.

- Mark the Horizon page and action collection with stable, presentation-only data attributes.
- Give the Horizon page an inline-size containment context.
- Replace viewport-selected action columns with `repeat(auto-fit, minmax(...))`, so cards reflow from four to two to one based on available content width.
- Keep body and action text at the existing readable sizes; do not scale the whole application or use CSS zoom.
- Use bounded `clamp()` spacing and a short-height media query to reduce page, cover, and spread gaps without shrinking interaction targets below 44 CSS pixels.
- Preserve the existing nested vertical scroll region so content that cannot fit remains reachable.

## Alternatives rejected

1. **Scale the whole interface.** This fits more pixels but reduces legibility, changes pointer-target size, and produces inconsistent native-window behavior.
2. **Scrolling only.** The lower content would remain reachable, but the action cards would still be narrow because their column count is selected from the wrong width.
3. **JavaScript ResizeObserver.** It can calculate explicit layouts, but CSS container-aware grid sizing handles this presentation concern with less state, no hydration risk, and no resize listener.

## Accessibility and compatibility

- Preserve action names, element types, routes, callbacks, focus rings, and source order.
- Preserve the existing one-h1 hierarchy and Runtime Status semantics.
- Keep action controls at least 44 by 44 CSS pixels.
- Do not hide or truncate action copy.
- Avoid horizontal overflow at 320, 768, 1020, 1024, and 1440 CSS pixels.
- At 1020 by 631 and 800 by 600, all action text must be rendered and reachable through the Horizon scroll region.

## Verification

1. Add a component contract that proves the Horizon exposes container-aware presentation hooks without changing action semantics.
2. Add a Playwright compact-window regression at 1020 by 631 and 800 by 600. It must assert that action cards have readable width, their visible text boxes remain inside each card, the Horizon is vertically scrollable when required, and scrolling reveals the lower action content.
3. Re-run the existing Horizon unit suite, all-screen layout audit, lint, TypeScript, and the production build.
4. Capture an after screenshot at the user-provided 1020 by 631 size and inspect it for clean console output and no clipped text.

## Scope boundary

This change is limited to the Working Desk/Horizon responsive presentation and its direct tests. It does not change data fetching, navigation authority, Runtime Status behavior, Study APIs, native packaging identities, or feature-flag behavior.
