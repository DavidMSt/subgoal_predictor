# # pygame_utils.py
#
# import os
# os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
# import pygame
#
# # Hide the Pygame support prompt (Optional)
#
#
# _initialized = False
#
#
# def initialize_pygame():
#     global _initialized
#     if not _initialized:
#         if not pygame.get_init():
#             pygame.init()  # Initialize all of Pygame
#         if pygame.mixer.get_init() is None:
#             try:
#                 pygame.mixer.init()  # Initialize the mixer for sound
#             except pygame.error:
#                 pass
#         _initialized = True
#     else:
#         # Pygame is already initialized, so we don't do anything
#         pass
#
#
# # Ensure that Pygame is initialized immediately upon importing this module
# initialize_pygame()
#
# # Make pygame available for import
# import pygame

# pygame_utils.py

import os
import sys
from contextlib import redirect_stderr

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
# Force ALSA driver for RPi (optional, usually default)
os.environ.setdefault("SDL_AUDIODRIVER", "alsa")

# -------------------------
# AUDIO CONFIG (TWEAK HERE)
# -------------------------
AUDIO_FREQUENCY = 44100     # try 22050 if Pi is weak
AUDIO_SIZE = -16            # signed 16-bit
AUDIO_CHANNELS = 2          # 1 = mono, 2 = stereo
AUDIO_BUFFER = 4096         # 2048–8192 recommended
# -------------------------

_initialized = False

# Silence ALSA spam only during init (NOT runtime)
# This prevents lines like:
# ALSA lib pcm.c:8772:(snd_pcm_recover) underrun occurred
class _NullWriter:
    def write(self, *_): pass
    def flush(self): pass

_null = _NullWriter()


def initialize_pygame():
    """Initialize pygame with pre_init() and a large audio buffer."""
    global _initialized

    if _initialized:
        return

    try:
        # Silence ALSA warnings only during init
        with redirect_stderr(_null):
            import pygame

            # PRE-INIT must come BEFORE pygame.init()
            pygame.mixer.pre_init(
                frequency=AUDIO_FREQUENCY,
                size=AUDIO_SIZE,
                channels=AUDIO_CHANNELS,
                buffer=AUDIO_BUFFER,
            )

            # Initialize pygame
            if not pygame.get_init():
                pygame.init()

            # Initialize mixer if needed
            if pygame.mixer.get_init() is None:
                pygame.mixer.init()

        _initialized = True

    except Exception as e:
        # Log normal errors if something else goes wrong
        print(f"[pygame_utils] Error initializing pygame: {e}")


# Initialize immediately on import
initialize_pygame()

# Re-export pygame
import pygame