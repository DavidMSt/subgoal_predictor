#!/usr/bin/env python3
"""
UDP → Pygame timecode receiver with blink + forward integration

Listens for UDP packets (e.g. from your MTC sender that sends:
    "ZERO 00:01:23:00"
on each zero-frame callback).

On every packet:
  * Flashes the window briefly.
  * Parses the timecode.
  * Stores it as a base value with the receive timestamp.

Between packets:
  * Forward-integrates the timecode using a fixed FPS (TC_FPS),
    so the on-screen timecode keeps running like a simple PLL.

Before the first valid timecode is received:
  * Shows "Waiting for UDP..." as a placeholder.

Requires:
    pip install pygame
"""

import socket
import threading
import time

import pygame

# -----------------------
# Network config
# -----------------------
UDP_IP = "0.0.0.0"   # listen on all interfaces
UDP_PORT = 5005

# -----------------------
# Timecode config
# -----------------------
TC_FPS = 25.0  # <-- Set this to your project frame rate (e.g. 24.0, 25.0, 30.0)


def tc_to_frames(h: int, m: int, s: int, f: int, fps: float) -> int:
    """
    Convert (h, m, s, f) to total frames since 00:00:00:00 at given fps.
    """
    total_seconds = h * 3600 + m * 60 + s
    return int(round(total_seconds * fps + f))


def frames_to_tc(total_frames: int, fps: float) -> tuple[int, int, int, int]:
    """
    Convert total frames to (h, m, s, f) at given fps.
    Handles negative values by wrapping around 24 hours.
    """
    frames_per_day = int(round(24 * 3600 * fps))
    total_frames = total_frames % frames_per_day

    frames_per_second = int(round(fps))
    total_seconds = total_frames // frames_per_second
    f = total_frames % frames_per_second

    s = total_seconds % 60
    total_minutes = total_seconds // 60
    m = total_minutes % 60
    h = total_minutes // 60

    return h, m, s, f


class FlashState:
    """
    Shared state between the UDP listener thread and the pygame loop.
    Also holds base timecode and forward-integrated TC state.
    """
    def __init__(self):
        # Flash control
        self.active = False
        self.until = 0.0

        # Display / message
        self.last_msg = "Waiting for UDP..."
        self.lock = threading.Lock()

        # Timecode state
        self.has_tc = False
        self.base_h = 0
        self.base_m = 0
        self.base_s = 0
        self.base_f = 0
        self.base_mono = 0.0  # time.monotonic() at last update


def parse_zero_message(text: str):
    """
    Parse messages like: "ZERO 00:01:23:00"
    Returns (h, m, s, f) or None on failure.
    """
    parts = text.strip().split()
    if len(parts) < 2:
        return None

    # We ignore the first token (e.g. "ZERO") and parse the second as TC.
    tc_str = parts[1]
    fields = tc_str.split(":")
    if len(fields) != 4:
        return None

    try:
        h = int(fields[0])
        m = int(fields[1])
        s = int(fields[2])
        f = int(fields[3])
    except ValueError:
        return None

    return h, m, s, f


def udp_listener(flash_state: FlashState):
    """
    Background thread: listens for UDP packets and updates flash_state.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((UDP_IP, UDP_PORT))
    print(f"Listening for UDP on {UDP_IP}:{UDP_PORT}...")

    while True:
        data, addr = sock.recvfrom(1024)
        now = time.monotonic()

        try:
            text = data.decode("ascii", errors="replace").strip()
        except Exception:
            text = repr(data)

        tc = parse_zero_message(text)

        with flash_state.lock:
            # Update message
            flash_state.last_msg = f"{text}  (from {addr[0]}:{addr[1]})"

            # Flash
            flash_state.active = True
            flash_state.until = now + 0.05  # flash for 50 ms

            # Update base timecode if parsed successfully
            if tc is not None:
                h, m, s, f = tc
                flash_state.has_tc = True
                flash_state.base_h = h
                flash_state.base_m = m
                flash_state.base_s = s
                flash_state.base_f = f
                flash_state.base_mono = now


def run_pygame_window(flash_state: FlashState):
    """
    Main pygame UI loop: shows running timecode and flashes on packet arrival.
    Forward-integrates timecode based on last received value + elapsed time.
    """
    pygame.init()
    window_width, window_height = 800, 200
    screen = pygame.display.set_mode((window_width, window_height))
    pygame.display.set_caption("UDP Timecode Receiver")

    try:
        tc_font = pygame.font.SysFont("Menlo", 96)
    except Exception:
        tc_font = pygame.font.SysFont(None, 96)

    msg_font = pygame.font.SysFont(None, 24)

    clock = pygame.time.Clock()
    running = True

    while running:
        now = time.monotonic()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        with flash_state.lock:
            do_flash = flash_state.active and (now < flash_state.until)
            if not do_flash:
                flash_state.active = False

            msg = flash_state.last_msg
            has_tc = flash_state.has_tc
            base_h = flash_state.base_h
            base_m = flash_state.base_m
            base_s = flash_state.base_s
            base_f = flash_state.base_f
            base_mono = flash_state.base_mono

        # Background color
        if do_flash:
            screen.fill((255, 255, 255))  # white flash
        else:
            screen.fill((0, 0, 0))        # black idle

        # Compute current timecode (forward-integrated)
        if has_tc:
            elapsed = now - base_mono
            base_frames = tc_to_frames(base_h, base_m, base_s, base_f, TC_FPS)
            delta_frames = int(round(elapsed * TC_FPS))
            total_frames = base_frames + delta_frames
            h, m, s, f = frames_to_tc(total_frames, TC_FPS)
            tc_str = f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"
        else:
            tc_str = "--:--:--:--"

        # Draw large timecode
        tc_surface = tc_font.render(tc_str, True, (0, 255, 0))
        tc_rect = tc_surface.get_rect(center=(window_width // 2, window_height // 2))
        screen.blit(tc_surface, tc_rect)

        # Draw last message & fps at bottom
        info_lines = [msg, f"TC_FPS={TC_FPS}"]
        y = window_height - 10
        for line in reversed(info_lines):
            info_surface = msg_font.render(line, True, (0, 255, 0))
            info_rect = info_surface.get_rect(left=10, bottom=y)
            screen.blit(info_surface, info_rect)
            y -= info_rect.height + 2

        pygame.display.flip()
        clock.tick(60)  # high refresh for smoother capture

    pygame.quit()


def main():
    flash_state = FlashState()

    # Start UDP listener thread
    t = threading.Thread(target=udp_listener, args=(flash_state,), daemon=True)
    t.start()

    # Run pygame loop
    try:
        run_pygame_window(flash_state)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()