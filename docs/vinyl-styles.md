# Vinyl styles

Every album gets a random style until you pick one. Pick from the vinyl page in the web UI (for every album, or just the one playing) or in lp-deck (for an album, an artist, or everything). Star the ones you like to show only those.

## Styles

- **Black**
- **Colored**: 24 colours.
- **Clear**: with platter shimmer and a rainbow sheen.
- **Album art**: a picture disc of the cover.
- **Mandelbrot**: 7 zoom spots in 12 colour schemes.
- **Nebula**: 46 smoke and cloud styles, among them 15 translucent marbles (teal, purple, pink, crimson, oxblood, copper, amber, mustard, olive, emerald, seafoam, aqua, cobalt, magenta and smoke).
- **Munafo deep zoom**: three Mandelbrot renders zoomed to `2.7×10⁻²²`. The full-size archives and the GPU engine that made them live in [bongsweat](https://github.com/dkoch84/bongsweat).
- **Pattern disc**: any Mandelbrot, Nebula or Munafo style as the whole disc.

## Labels

- Album art, one of 10 plain colours, or any Mandelbrot, Nebula or Munafo style.
- Artist and album on the label: none, curved, straight or blocky, with your own font and colours.

## On top of any style

- **Effects**: glass, deep edge, rim light.
- **Grooves**: auto, shine, shadow or smooth.
- **Brightness**.
- **Frame and panel colours**: the background around the cover and the record. Pure black suits a cover with a dark edge.

The grooves mark each track on the album, and the needle follows them as it plays.

## The images

The fractal styles are rendered once and committed under `lpcore/cache/` (mandelbrot, nebula, munafo), so nothing is rendered on the kiosk. After changing a style, `make prerender` re-renders just that one; commit the image with the code.

## Making a style

New styles are designed in lp-studio (`make studio`).

- **Smoke colours need a ramp.** A smoke style only reads as smoke on a big screen when its colours step down in brightness: body light, body deep at about 72% of it, smoke ink at about 25%, accent ink at about 9%. With the ramp linked (the default), you pick the light colour and the rest follow. lp-studio warns when a ramp or a render is too flat.
- **Ship writes a style file.** Smoke, clouds and nebula styles live as JSON in `lpcore/vinyl/styles/nebula/`, one file per style. Ship writes the file and renders its image; commit both. The `order` field sets where the style sits in the catalog (the marbles run round the colour wheel).
- **Mandelbrot and colour styles** still go into `lpcore/vinyl/catalog.py`: Export gives you the lines to paste.
