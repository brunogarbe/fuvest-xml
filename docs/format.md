# XML format reference

Source of truth: `xsd/fuvest_xml.xsd`. Validate every edit with
`uv run fuvest-xml-validate <file>`. Allowed classification values: `docs/classifications.md`.

## Root

```xml
<exam name="FUVEST" year="2026" phase="objective" day="1" variation="V1" date="2025-11-23" lang="pt-br">
```

All seven attributes are required. Children: any mix of `<question_group>` and `<subject name="...">`
(a `<subject>` wraps one or more `<question_group>`, used for per-subject phase-2 exams).

## question_group

```text
question_group
├─ context?            shared text/images for several questions (StatementChilds)
└─ (objective_question | discursive_question | essay_question)+
```

## Questions

| Element | Attributes | Children (in order) |
|---|---|---|
| `objective_question` | `number`* `cancelled` `success_rate` | `classification`+, `statement`, `options` or `options_table`, `assumptions`? |
| `discursive_question` | `number`* `null` `success_rate` | `classification`+, `statement`, `parts`, `assumptions`? |
| `essay_question` | `number`* `null` | `statement`, `assumptions`? |

`*` required. `success_rate` is 0–100 with at most one decimal.

Extra validator rules (`src/fuvest_xml/validate.py`): `number` of an objective question must be an
integer; each objective question needs exactly 5 options (4 for UNICAMP).

## Options and parts

```xml
<options>
  <option label="A" is_correct="false"><p>...</p></option>   <!-- label, is_correct required -->
</options>
<options_table class="...">                                   <!-- options whose answers are table rows -->
  <header><cell><p>...</p></cell></header>
  <option label="A" is_correct="true"><cell><p>...</p></cell></option>
</options_table>
<parts><part><p>a) ...</p></part></parts>
```

`part` contains only `<p>` and `<image>`. `option` (in `<options>`) may also contain `<verse>` and `<cite>`.

## Statement content (StatementChilds)

Used by `context`, `statement`, `assumptions`. Allowed children, any order:
`p`, `header`, `caption`, `cite`, `quote`, `verse`, `footnote`, `image`, `list`, `ordered_list`, `table`.

- `quote`: optional `title`, then `p`/`image`.
- `verse`: optional `title`, then `stanza`+ each containing `l`+ (lines).
- `list` (attr `symbol`) and `ordered_list` (attr `type`: `arabic`, `alpha`, `roman`): `item`+ containing `p`/`image`.
- `table` (attrs `width` 0–100, `columns`): optional `header`, then `row`+; each is `cell`+ with a single `p` or `image`; `align` = `left|center|right`.
- `footnote` requires `id`; referenced inline with `<ref id="..."/>`.

## Inline content (inside p, l, cite, header, caption, b, i, u, q)

`b`, `i`, `u`, `q` (quotation marks), `style color="..."`, `m` (inline LaTeX math), `math` (display math,
optional `end`), `c` (inline chemistry), `chem` (display chemistry), `ref`.
`p`/`l`/`cite`/`header`/`caption` accept `align="left|center|right"`.

Math goes in `m`/`math` as LaTeX text, not Unicode symbols or plain-text approximations.

## Images

```xml
<image src="fuvest/2026/01/q05.png" width="..." html_width="..." size="..." wrap="true"/>
```

`src` is relative to the top-level `images/` folder: `images/<exam>/<year>/<phase-or-semester>/<file>`.
Only `src` is required. Some exams (Enem 2025, ITA/Unesp/Unicamp 2026, Fuvest 1999) reference images not yet in the repo.

## Minimal example

```xml
<exam name="FUVEST" year="2026" phase="objective" day="1" variation="V1" date="2025-11-23" lang="pt-br">
  <question_group>
    <context><p>Texto de apoio com <q>citação</q> e <m>x^2</m>.</p></context>
    <objective_question number="1">
      <classification subject="Math:Algebra:Functions"/>
      <statement><p>Qual é o valor de <m>f(2)</m>?</p></statement>
      <options>
        <option label="A" is_correct="false"><p>1</p></option>
        <option label="B" is_correct="true"><p>4</p></option>
        <option label="C" is_correct="false"><p>5</p></option>
        <option label="D" is_correct="false"><p>6</p></option>
        <option label="E" is_correct="false"><p>8</p></option>
      </options>
    </objective_question>
  </question_group>
</exam>
```
