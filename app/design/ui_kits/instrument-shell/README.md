# Loci — Instrument Shell

Third register, alongside the outer (memory palace) and inner (vault) shells. Where the user reads the topology of the vault as if from a planetarium console: dark navy canvas, bronze hairlines, Latin twins, Roman folios, reticle brackets and dotted meridians.

A paper variant of the same chrome (`canvas.paper`) keeps long-form reading on ivory ground while preserving every other ornament — same corners, same reticle, same Latin labels.

## Components

```jsx
<Corners
  tl={{label:'thesaurus',  value:'~/loci'}}
  tr={{label:'caelum',     value:'observatorium · v0.4'}}
  bl={{label:'fundatum',   value:'mmxxvi · iv'}}
  br={{label:'lat · long', value:'40.71 · -74.00'}}
/>
<Reticle/>
<Meridian/>
<Bezel size={420} rotate items={["nodi","nexus","loci","via"]}/>
<RomanIndex idx={3} of={17}/>
<L latin="topologia">Topology</L>
<TypeDot type="project" halo/>
<HeaderStrip label="All loci" latin="omnia loca" telemetry={…}/>
```

All atoms live in `components.jsx`. Static styling lives in
`../../instrument-shell.css` — opt in by either wrapping content in
`.instrument-shell` or by using `.canvas.instrument` directly.

## Tokens used (from `colors_and_type.css`)

`--t-bg`, `--t-bg-deep`, `--t-bg-soft`, `--t-rule`, `--t-rule-soft`,
`--t-fg`, `--t-fg-mute`, `--t-fg-faint`, `--t-bronze`, `--t-bronze-d`,
`--t-grid-step`, `--t-grid-line`, `--t-paper`, `--t-paper-2`, `--t-paper-3`.

## Modifiers

- `data-density="sparse | regular | dense"` on any wrapper — adjusts list/rail row padding.
- `data-motion="static | subtle | ambient"` on any wrapper — controls flow on edges, bezel rotation, meridian opacity.
- `--flow-dur`, `--bezel-dur`, `--meridian-opacity` for fine-tuning.

## Reading mode

Long-form surfaces (node detail body, composer body) flip to `canvas.paper`. Same Latin, same Roman folios, same reticle — ivory ground, ink type, terracotta drop cap.
