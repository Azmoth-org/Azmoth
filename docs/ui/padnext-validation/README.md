# The PADnext validation error screen

Reference screenshots for `ValidationErrorList` and the components it composes
(`ErrorDetail`, `ParsedPreview`, `FixSuggestion`). Two states — collapsed and expanded — at
1440 px and 390 px, in both themes.

| | 1440 px | 390 px |
|---|---|---|
| collapsed, light | `collapsed-1440-light.png` | `collapsed-390-light.png` |
| collapsed, dark | `collapsed-1440-dark.png` | `collapsed-390-dark.png` |
| expanded, light | `expanded-1440-light.png` | `expanded-390-light.png` |
| expanded, dark | `expanded-1440-dark.png` | `expanded-390-dark.png` |
| expanded, English | `expanded-1440-light-EN.png` | — |

## What the pictures are of

The real components, rendered against a real engine report: `validate_bytes` run over the bundled
synthetic delivery with four deliberate faults introduced (a `posanzahl` the schema refuses, the
`@echtdaten` attribute removed, a `@ziffer` emptied, the version set to 2.10). Two blocking errors
and four notes, one of which is `severity: "error"` with `blocking: false` — the case the two
fields exist to distinguish, and the reason the "nicht blockierend" badge is in the frame.

They were taken through a temporary route, because `/padnext` sits behind a session and an upload
and standing up Postgres, Better Auth and onboarding to photograph a component is more moving parts
than the picture is worth. The route was deleted; only these files remain. To retake them, render
`<ValidationErrorList report={…} />` on any reachable page with the output of

    apps/engine/.venv/bin/python -c "import json; from app.padnext import validate_file; \
        print(json.dumps(validate_file('<a broken delivery>').as_dict(), ensure_ascii=False))"

and screenshot at the four sizes with `document.documentElement.classList.toggle('dark')` for the
dark pair — the stylesheet is class-based (`@custom-variant dark (&:is(.dark *))`), so setting
`prefers-color-scheme` alone changes nothing and produces two identical files.

## What they are meant to show

**Collapsed is the default and it is one line per problem.** Icon, summary, code, location. The
point is not tidiness: before deciding what to do, a reader has to know whether they are looking at
one problem or four, and a wall of prose answers that only by being scrolled to the end of.
`summary_de` exists for this row and is capped at 120 characters — see
`app/padnext/validation.py`.

**Expanded is message → why → fix → command**, and the "why" is itself a closed `<details>`. The
reasoning is not decoration: `echtdaten="1"` is one character from `echtdaten="0"`, and an
instruction without a reason does not distinguish "declare what your file is" from "make the error
go away". Collapsing keeps that argument one click from the reader about to take the shortcut and
charges nothing to the reader who already knows.

**One language at a time, German by default.** The engine sends both halves; stacking them doubled
the height of a screen whose problem is height, by adding text that no single reader wanted.

**Notes are folded behind their count.** Usually the longer list, and by definition not what has to
change now.
