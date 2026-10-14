# Widget definition reference

For installation, controls, screenshots, themes and reports, see the
[user guide](../README.md). Definitions use safe YAML and version 2 of the widget
language. Duplicate or non-string mapping keys, unknown fields and unsupported
YAML tags are errors. Quote strings beginning with `@` or containing `: `.

## Documents and pages

Every document requires `schema_version: 2` and a non-empty `name`. Supply either
a non-empty `widgets` list or a `pages` list, never both. Pages belong only to
the root document; include files contain ordinary widget lists. A root may have
1–9 pages with distinct names of at most 24 characters. Each page has `name`,
optional `sources` and `widgets`.

```yaml
# yaml-language-server: $schema=../src/hctui/widget_schema.json
schema_version: 2
name: My dashboard
intervals:
  cpu: 2
  memory: 4
pages:
  - name: Summary
    sources: [cpu, memory]
    widgets:
      - type: text
        properties:
          value: "@f'CPU {cpu.usage:.1f}% | RAM {memory.usage:.1f}%'"
  - name: Storage
    sources: [disk]
    widgets:
      - type: text
        properties:
          value: "@f'Free: {format_bytes(disk.free)}'"
```

`sources` declares namespaces used in expressions; it defaults to an empty
list. Root sources are available to every page. Includes declare their own
sources. Only active-page dependencies are sampled, with alert dependencies
kept active when the dashboard includes alerts. Switching pages keeps widgets
and scroll positions. Reloading recreates them from the edited definitions.

Optional root `intervals` maps source names to sampling seconds, from 0 to 3600;
0 requests foreground sampling each UI refresh. Background sources have a
minimum effective interval of one second. `alerts` is derived and cannot have
an interval. Faster UI refreshes do not override slower source cadences.
Intervals in included documents are validated but the root controls scheduling.

Default intervals:

| Source | Seconds | Collection |
| --- | --- | --- |
| cpu, network | 1 | Foreground, non-blocking counters |
| memory, load | 2 | Foreground |
| disk, monitor | 5 | Foreground |
| temperature, processes | 5 | Background |
| filesystems, services, wifi | 10 | Background |
| system | 30 | Background |
| alerts | Derived each refresh | CPU, memory, disk, temperature, services |

## Node types

Nodes have `type`, optional `properties`, and the structure shown below.
Numbers, lists and booleans are native YAML values. Strings beginning with `@`
are expressions. Required properties are marked **required**.

| Type | Properties and defaults | Structure |
| --- | --- | --- |
| text | `value: ''`, `align: left` (left/center/right) | Leaf; string value |
| box | `title: ''` | Exactly one child; theme-colored frame |
| stack | None | Non-empty children, vertically stacked |
| columns | `spacing: 1` | Non-empty children in equal-width columns |
| responsive | `min_width: 80`, `spacing: 1` | Columns at/above width; stack below |
| conditional | `visible: true` | Children shown when true; structural change when toggled |
| progress | `value: 0`, `max: 100`, `normal: progress_normal`, `complete: progress_complete` | Value clamped to 0–max |
| graph | `value: []`, `max: 100`, `height: 4` | Multi-row graph, finite numeric samples |
| sparkline | `value: []`, optional `max`, `label: ''`, `ascii: false` | One-row history, automatic scale without max |
| status | `value: ''`, `state: unknown` | Badge: ok/warning/critical/unknown |
| table | **headers**, `rows: []`, optional widths/compact_columns, `compact_width: 60`, `max_rows: 128`, `empty: No data` | See below |
| divider | `char: ' '`, `top: 0`, `bottom: 0` | Divider with optional blank rows |
| repeat | **stop**, `start: 0`, `variable: i`, `columns: 1`, `spacing: 1`, optional column_order | One template; exclusive stop |
| include | **literal path** | Includes a widget document relative to its own file |

All nodes produce flow widgets inside a scrollable page. Containers have a
non-empty `children` list, while a repeat has one `template` node. Includes have
neither. Positive maxima and finite numbers are required. Graph heights and
column counts are 1–256; spacing/padding cannot be negative. The `conditional`
placeholder occupies one empty row while hidden.

## Tables and compact layouts

```yaml
type: table
properties:
  headers: [PID, Name, CPU%, RAM]
  rows: '@processes.cpu_rows'
  widths: [7, 0, 7, 10]
  compact_columns: [1, 2, 3]
  compact_width: 60
  max_rows: 5
  empty: Waiting for a second CPU sample
```

Headers contain 1–16 strings. Rows have matching column counts and scalar
cells, with at most 128 rows and 16 cells per row. `widths` matches headers:
positive values request fixed widths and zero shares remaining space.
`compact_columns` chooses zero-based columns to retain below `compact_width`;
indices must be unique and in range. Cells clip with an ellipsis, sanitize
control characters and are bounded to 512 displayed characters.

Use `responsive` to stack panels on narrow screens. Width includes the content
area offered to that container, so an 80-column terminal inside the outer frame
has 78 columns of content. The bundled CPU/System layouts switch at 72 columns.
Sparklines preserve peaks when downsampling history to available width.
Set `ascii: true` for a simpler character set if Unicode blocks look wrong.

See [examples/pages.yaml](../examples/pages.yaml) for complete responsive,
table and conditional examples, and [examples/compact.yaml](../examples/compact.yaml)
for a small single-page dashboard.

## Expressions and repetition

An expression starts with `@` and can read declared source attributes, index
sequences, perform arithmetic/comparisons, use conditional expressions and
construct f-strings. Helpers: `str`, `len`, `round`, `min`, `max`, `abs`, `int`,
`float`, `format_bytes`, `format_rate`, `format_duration`, `format_temperature`.
Byte/rate formatting uses binary units such as KiB and MiB.

```yaml
type: text
properties:
  value: >-
    @f'Download {format_rate(network.download_rate)} | Upload {format_rate(network.upload_rate)}'
```

```yaml
type: repeat
properties:
  variable: core
  stop: '@len(cpu.per_core)'
  columns: '@min(2, len(cpu.per_core))'
template:
  type: text
  properties:
    value: "@f'CPU {core}: {cpu.per_core[core]:.1f}%'"
```

Repeats use Python's exclusive `range(start, stop)` convention. Variables are
local to templates, cannot shadow sources/helpers, and nested repeats need
distinct variable names. Default column order distributes successive items
across columns. `column_order: [1, 0]` reverses two-column assignment.
An empty range creates an empty flow widget.

No imports, arbitrary method calls, comprehensions, assignments or private
attribute access are allowed. This is a restricted expression language for
trusted local configuration; it is not a security sandbox for untrusted files.
Dynamic structural properties (repeat ranges, column spacing, graph height,
responsive breakpoint and visibility) rebuild the active layout when changed.
Other properties update existing widgets only when their values change.

## Metric namespaces

| Namespace | Fields |
| --- | --- |
| cpu | usage, per_core, physical_count, frequency_mhz, history, rows |
| memory | total, used, available, usage, swap_total, swap_used, swap_usage |
| network | interface, download_rate, upload_rate, download_history, upload_history, history_max |
| disk | path, total, used, free, usage, read_rate, write_rate |
| load | one, five, fifteen, normalized, history, available |
| temperature | current, label, rows, history |
| system | hostname, uptime, rows, addresses |
| processes | cpu_rows, memory_rows, count, scanned, ready |
| filesystems | rows, count, skipped |
| services | rows, failed, message, available |
| wifi | interface, ssid, signal, quality, state, message |
| monitor | cpu_usage, rss, sample_ms, update_ms, render_ms, refreshes, missed, rows |
| alerts | level, summary, rows, events, active_count |

Usage is percent, capacity is bytes, rates are bytes/second, temperatures are
Celsius and uptime is seconds. Load `normalized` is one-minute load divided by
logical CPU count, expressed as percent; it may exceed 100%. Sequences are
immutable tuples. Physical core count, frequency and current temperature may
be `None`. Optional background snapshots initially contain loading/empty data.
Use `ready`, `available` or None checks where appropriate.

Table row shapes:

| Field | Cells |
| --- | --- |
| cpu.rows | CPU index, usage |
| temperature.rows | Sensor label, current temperature |
| system.rows / addresses | Field/value / interface/IPv4 |
| processes.cpu_rows / memory_rows | PID, process name, CPU%, formatted RSS |
| filesystems.rows | Mount, usage, free, inode usage |
| services.rows | Unit, state |
| monitor.rows | Stage, value |
| alerts.rows / events | Source/state/detail / elapsed time/source/state (newest first) |

Use the bundled YAML definitions for field formatting examples.

## Colors, loading and limits

Themes are in `src/hctui/themes.json`. Palette names include `body`, `border`,
`footer`, `table_header`, `tab_active`, `tab_normal`, `status_ok`, `status_warning`,
`status_critical`, `status_unknown`, `progress_normal`, `progress_complete`,
`graph_background`, `graph_complete`, `graph_smooth`. Changing themes recolors
the existing widgets without rebuilding their definitions.

Definitions load only at startup or on `r`. No file polling occurs. Failed
reloads retain the working dashboard. Includes are relative to their definition
file, regardless of the working directory. The optional VS Code YAML extension
uses the generated schema; runtime validation additionally checks expressions,
scoped names, include cycles and resolved values without importing jsonschema.

Limits protect small devices from accidentally oversized layouts:

- 256 KiB per definition, 32 distinct included files;
- 32 nesting levels for widgets/includes;
- 2,048 validated nodes or generated widgets across cached pages;
- 256 iterations per repeat, 256 columns;
- 600 samples per history, 4,096 characters per expression;
- 1–9 pages, 128 rows and 16 columns per table.

## Migration from the original JSON language

Version 1 JSON is replaced by YAML version 2 and is not interpreted by the new
composer. The bundled definitions have already been migrated.

| Original | YAML version 2 |
| --- | --- |
| definition.language_version and metadata | schema_version: 2 and name |
| content at root | widgets, or pages containing widgets |
| widget_type | type |
| properties: 'key=value;key=value' | Native properties mapping |
| pile with content | stack with children |
| box.content containing a node | box.children containing one node |
| widget with a filename | include with literal relative path |
| repeat_columns, inclusive from/to, no_columns, loop_in_columns | repeat, exclusive start/stop, columns, column_order |
| import_source, enable_cache | sources and shared immutable snapshots |
| @cpu_stats.cpu_usage_total() | '@cpu.usage' |
| @cpu_stats.cpu_usage_per_core()[i] | '@cpu.per_core[i]' |

Custom providers belong in the source registry/sampler; YAML definitions do not
import executable modules. Regenerate the editor schema after registry/property
changes with `python scripts/generate_widget_schema.py`.
