# Topic icons (Tabler, vendored)

Outline icons from [Tabler Icons](https://github.com/tabler/tabler-icons),
release tag `v3.49.0` (published 2026-10-05), MIT licence (full text in
`LICENSE` next to this file).

Source of each file:
`https://raw.githubusercontent.com/tabler/tabler-icons/v3.49.0/icons/outline/<name>.svg`

Licence source:
`https://raw.githubusercontent.com/tabler/tabler-icons/v3.49.0/LICENSE`

## Files

21 files: one per topic in `conversations/topics.py`, plus one for the
"Surprise me" button.

| File | Used by |
| --- | --- |
| `arrows-shuffle.svg` | "Surprise me" button (not a topic) |
| `ball-football.svg` | `sports-club` |
| `bread.svg` | `bakery` |
| `briefcase.svg` | `colleague-weekend` |
| `bus.svg` | `public-transport` |
| `cake.svg` | `birthday-party` |
| `car.svg` | `car-workshop` |
| `cloud-rain.svg` | `bus-stop-weather` |
| `dog.svg` | `dog-walk` |
| `flame.svg` | `landlord-heating` |
| `horse-toy.svg` | `playground` |
| `id.svg` | `registration-office` |
| `mail.svg` | `post-office` |
| `package.svg` | `neighbour-parcel` |
| `pill.svg` | `pharmacy` |
| `scissors.svg` | `hairdresser` |
| `shopping-cart.svg` | `supermarket` |
| `stairs.svg` | `neighbour-stairwell` |
| `stethoscope.svg` | `doctor-appointment` |
| `tools-kitchen-2.svg` | `restaurant` |
| `train.svg` | `train-delay` |

Substitution: the plan named `swing` for `playground`, but `swing` does not exist
in Tabler `v3.49.0`, so `playground` uses `horse-toy`.

## Changes to the original files

Only the `<svg>` root element is changed; the drawing children (`<path>`,
`<circle>`, ...) are copied unchanged. Every file:

- drops the leading HTML comment with Tabler's tags, category, version and unicode;
- drops `width="24"` and `height="24"` (the size comes from the `icon` class in CSS);
- keeps `xmlns`, `viewBox="0 0 24 24"`, `fill="none"`, `stroke="currentColor"`,
  `stroke-width="2"`, `stroke-linecap="round"` and `stroke-linejoin="round"`;
- adds `class="icon" aria-hidden="true" focusable="false"` (the icons are
  decorative; the text next to them carries the meaning);
- writes the root on one line in that same attribute order.

No colours and no inline styles: the icon takes its colour from the text through
`currentColor`. `tests/test_ui.py` scans these files like every other template, and
`tests/test_topics.py` checks the root attributes, that every topic's icon exists
and that no file is left unused.

How to add or change an icon: see the "UI: tokens and components" section of
`CLAUDE.md` in the repository root.
