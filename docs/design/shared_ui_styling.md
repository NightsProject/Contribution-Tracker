# Shared UI Styling

## Decision

Use a cohesive, responsive visual system across all pages, managed from a
dedicated static stylesheet shared by the Jinja base template. Keep templates
limited to semantic classes for page-specific layout needs.

## Implementation

- The shared stylesheet defines colors, typography, card surfaces, form
  controls, buttons, tables, navigation, focus states, and status messages.
- Authentication pages use a narrow centered card. Dashboard transaction
  filters use a responsive grid that collapses to one column on small screens.
- Tables remain horizontally scrollable on narrow viewports. Summary cards,
  navigation, and forms adapt to mobile widths.
- Focus-visible styling, reduced-motion support, and distinct success/error
  message colors improve accessibility.
