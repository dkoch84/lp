"""Vinyl option catalog — the small, self-contained lists of what a user can
pick, used for validation and for enumerating UI controls.

This is the seed of the single source of truth for vinyl options. The large
style/colour/variant tables and rendering palettes still live in lp.display for
now; they move here alongside the renderer in the next step, at which point this
module also grows an ``enumerate_options()`` that both the web UI and lp-deck
read from instead of rebuilding lists.
"""

# Label text rendering modes.
LABEL_TEXT_MODES = ['none', 'curved', 'straight', 'blocky']

# Fonts available for the curved/straight/blocky label text.
LABEL_TEXT_FONTS = ['georgia', 'dejavuserif', 'dejavusans', 'dejavusansmono',
                    'oswald', 'bebasneue', 'notoserif', 'notosans', 'ubuntu',
                    'cantarell']

# Decorative critters for the label's empty spaces (rendered via the Noto Color
# Emoji font). Name → emoji; the names double as the valid decor values.
DECOR_EMOJI = {
    'bird': '🐦', 'dove': '🕊', 'owl': '🦉',
    'sun': '☀', 'moon': '🌙', 'star': '⭐',
    'octopus': '🐙', 'fish': '🐟',
    'beaver': '🦫', 'dog': '🐕', 'cat': '🐈',
}

# Valid values for a decor slot: a critter name, or these specials.
DECOR_VALUES = ('none', 'random', *DECOR_EMOJI.keys())
