# Vinyl styles

Every album gets a random style until you pick one. Pick from the vinyl page in the web UI (for every album, or just the one playing) or in lp-deck (for an album, an artist, or everything). Star the ones you like to show only those.

## Styles

- **Black**
- **Colored**: 24 colours.
- **Clear**: with platter shimmer and a rainbow sheen.
- **Album art**: a picture disc of the cover.
- **Mandelbrot**: 7 zoom spots in 12 colour schemes.
- **Nebula**: 32 smoke and cloud styles, teal-marble among them.
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

The fractal styles are rendered once and committed under `lpcore/cache/` (mandelbrot, nebula, munafo), so nothing is rendered on the kiosk. After changing a style, `make prerender` re-renders just that one; commit the image with the code. New styles are designed in lp-studio (`make studio`).
