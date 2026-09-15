"""lp-studio: the vinyl-style authoring tool (PySide6) built on lpcore.

A bench for making new catalog styles. Tune a mandelbrot, colour, nebula,
clouds or layered-smoke style against a live preview drawn by lpcore's exact
production renderer, so what you see is what the kiosk and lp-deck will draw.

For smoke, the darker colours can follow the light one at teal-marble's
brightness steps (lpcore.vinyl.ramp), and the window warns about a ramp or a
render that will look flat on a big screen. Every change can be undone. A
finished smoke, clouds or nebula style ships as a style file
(lpcore.vinyl.styles) with its image rendered; mandelbrot and colour styles
export a snippet for lpcore/vinyl/catalog.py.
"""
__version__ = "0.1.0-dev"
