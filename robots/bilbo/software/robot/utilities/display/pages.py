from PIL import ImageFont

from robot.utilities.display.display import Page, DISPLAY_HEIGHT, DISPLAY_WIDTH

# class StatusPage(Page):
#     def __init__(self):
#         """
#         Initialize the Status page with dynamic elements.
#         """
#         super().__init__(width=DISPLAY_WIDTH, height=DISPLAY_HEIGHT, name="Status", border=True, show_title=False)
#         self.battery_level = "full"  # Options: "empty", "half", "full"
#         self.battery_voltage = "16.8V"
#         self.internet_connected = False  # circle icon; crossed if False
#         self.signal_strength = "none"  # "none", "low", "medium", "high" (3 bars)
#         self.joystick = True  # gamepad connected?
#         self.server_connection = False  # fourth icon: empty/filled square
#         self.user = "user"
#         self.hostname = "hostname"
#         self.ip_address = "0.0.0.0"
#         self.ssid = "SSID"
#         self.mode = "Idle"
#
#         # Layout tuning
#         self._EXTRA_TOP_BAR = 5  # increase top bar height by ~5px
#
#     # ----------------------- setters -----------------------
#
#     def set_battery(self, level, voltage: float):
#         """Set the battery level and voltage."""
#         self.battery_level = level
#         self.battery_voltage = f"{voltage:.1f} V"
#
#     def set_internet_status(self, connected: bool):
#         """Set the internet connection status."""
#         self.internet_connected = connected
#
#     def set_signal_strength(self, strength: str):
#         """Set signal strength: 'none', 'low', 'medium', or 'high'."""
#         if strength not in ("none", "low", "medium", "high"):
#             strength = "none"
#         self.signal_strength = strength
#
#     def set_joystick_status(self, connected: bool):
#         """Set the joystick (gamepad) connection status."""
#         self.joystick = connected
#
#     def set_server_connection(self, connected: bool):
#         """Set the server connection status (empty/filled square)."""
#         self.server_connection = connected
#
#     def set_user_and_hostname(self, user, hostname):
#         """Set the user and hostname."""
#         self.user = user
#         self.hostname = hostname
#
#     def set_ip_address(self, ip):
#         """Set the IP address."""
#         if ip is not None:
#             self.ip_address = ip
#         else:
#             self.ip_address = ""
#
#     def set_ssid(self, ssid):
#         """Set the WiFi SSID."""
#         if ssid is not None:
#             self.ssid = ssid
#         else:
#             self.ssid = ''
#
#     def set_mode(self, mode):
#         """Set the current mode."""
#         if mode is not None:
#             self.mode = mode
#         else:
#             self.mode = ''
#
#     # ----------------------- rendering -----------------------
#
#     def draw_page(self):
#         """Draw the Status page."""
#         font = ImageFont.load_default()
#
#         # Header Bar
#         sep_y = self._draw_status_bar(font)
#
#         # Move the text block UP by 1px (per your note) from previous placement
#         start_y = 19  # was 20; lifting by one pixel
#         line = 11  # compact but readable
#
#         self.draw.text((5, start_y + 0 * line), f"{self.user}@{self.hostname}", font=font, fill=255)
#         self.draw.text((5, start_y + 1 * line), f"IP: {self.ip_address}", font=font, fill=255)
#         self.draw.text((5, start_y + 2 * line), f"SSID: {self.ssid}", font=font, fill=255)
#         self.draw.text((5, start_y + 3 * line), f"Mode: {self.mode}", font=font, fill=255)
#
#     def _draw_status_bar(self, font):
#         """
#         Draw the header bar with battery, internet, signal bars, gamepad, and server icons.
#
#         Returns:
#             separator_y (int): the y coordinate where the horizontal separator line is drawn.
#         """
#         # --- Bar geometry ---
#         bar_top = 0
#         battery_y = 2  # anchor for battery; others will be centered to the bar
#         battery_height = 8
#         base_separator_y = battery_y + battery_height + 2  # original
#         separator_y = base_separator_y + self._EXTRA_TOP_BAR  # increased height (~+5px)
#
#         # Helper to center an icon of height h within the bar [bar_top, separator_y)
#         def center_y(h: int) -> int:
#             return max(bar_top, (bar_top + separator_y - h) // 2)
#
#         # --- Battery Icon (kept 16x8, left-aligned) ---
#         battery_x = 2
#         battery_width = 16
#         terminal_width = 2
#         by = center_y(battery_height)
#
#         # Battery outline
#         self.draw.rectangle(
#             (battery_x, by, battery_x + battery_width, by + battery_height),
#             outline=255, fill=0
#         )
#         # Battery terminal
#         self.draw.rectangle(
#             (battery_x + battery_width, by + 2, battery_x + battery_width + terminal_width, by + battery_height - 2),
#             outline=255, fill=255
#         )
#         # Battery fill
#         if self.battery_level == "empty":
#             fill_width = 0
#         elif self.battery_level == "half":
#             fill_width = (battery_width - 2) // 2
#         elif self.battery_level == "full":
#             fill_width = battery_width - 2
#         else:
#             fill_width = 0
#
#         if fill_width > 0:
#             self.draw.rectangle(
#                 (battery_x + 1, by + 1, battery_x + 1 + fill_width, by + battery_height - 1),
#                 outline=255, fill=255
#             )
#
#         # Battery voltage text
#         text_x = battery_x + battery_width + terminal_width + 4
#         self.draw.text((text_x, by - 1), self.battery_voltage, font=font, fill=255)
#
#         # --- Internet status icon (8x8 circle) ---
#         internet_x = battery_x + battery_width + terminal_width + 50
#         internet_size = 8
#         iy = center_y(internet_size)
#         if self.internet_connected:
#             self.draw.ellipse((internet_x, iy, internet_x + internet_size, iy + internet_size), outline=255, fill=255)
#         else:
#             self.draw.ellipse((internet_x, iy, internet_x + internet_size, iy + internet_size), outline=255, fill=0)
#             self.draw.line((internet_x, iy, internet_x + internet_size, iy + internet_size), fill=255, width=1)
#
#         # --- Signal strength (three bars) ---
#         signal_x = internet_x + 11
#         # Bars will use up to 11px height now (was 7)
#         bar_heights = [5, 8, 11]
#         bar_w, gap = 2, 2
#         total_height = max(bar_heights)
#         sy = center_y(total_height + 1)  # +1 to include baseline thickness
#         self._draw_signal_bars(signal_x, sy, heights=bar_heights, bar_w=bar_w, gap=gap,
#                                strength=self.signal_strength, connected=self.internet_connected)
#
#         # --- Gamepad icon (enlarged & more elaborate; ~20x14) ---
#         pad_x = signal_x + 14
#         pad_h = 14  # previously ~8–9; enlarged by ~5–6px
#         pad_y = center_y(pad_h)
#         self._draw_gamepad_icon(pad_x, pad_y, height=pad_h, connected=self.joystick)
#
#         # --- Server connection icon (square; centered vertically) ---
#         server_size = 9  # slightly bigger, crisp odd size
#         server_x = pad_x + 22
#         server_y = center_y(server_size)  # centered vertically in the taller bar
#         self._draw_server_icon(server_x, server_y, size=server_size, connected=self.server_connection)
#
#         # --- Separator line under the (taller) status bar ---
#         self.draw.line((0, separator_y, self.width, separator_y), fill=255)
#
#         return separator_y
#
#     # ----------------------- icon helpers -----------------------
#
#     def _draw_signal_bars(self, x: int, y: int, heights=(5, 8, 11), bar_w=2, gap=2,
#                           strength: str = "none", connected: bool = True):
#         """
#         Draw three vertical signal bars at (x,y). y is the TOP of the tallest bar area.
#         Bars are outlined; filled up to the 'strength' level when connected.
#         'strength' in {'none','low','medium','high'}.
#         """
#         levels = {"none": 0, "low": 1, "medium": 2, "high": 3}
#         fill_count = levels.get(strength, 0)
#         if not connected:
#             fill_count = 0  # keep outlines only when not connected
#
#         max_h = max(heights)
#         baseline = y + max_h - 1  # bottom pixel row for bars
#
#         for i, h in enumerate(heights):
#             bx0 = x + i * (bar_w + gap)
#             bx1 = bx0 + bar_w
#             by0 = baseline - (h - 1)
#             by1 = baseline
#             self.draw.rectangle((bx0, by0, bx1, by1), outline=255, fill=255 if i < fill_count else 0)
#
#         if not connected:
#             total_w = (bar_w + gap) * 3 - gap
#             self.draw.line((x - 1, baseline - max_h + 1, x + total_w + 1, baseline), fill=255, width=1)
#
#     def _draw_gamepad_icon(self, x: int, y: int, height: int = 14, connected: bool = True):
#         """
#         Draw a more elaborate PS-style gamepad in approximately (width ~ 20, given height).
#         Features:
#           - rounded central body with pronounced grips
#           - tiny D-pad (left), two face buttons (right)
#           - tiny start/select dots in the middle
#         If disconnected, draw as outline and strike-through.
#         """
#         # Proportional dimensions
#         h = max(12, height)  # ensure minimum room
#         w = 20
#         body_top = y
#         body_bottom = y + h
#         body_left = x
#         body_right = x + w
#
#         # Main body: rounded rectangle via center rect + left/right ellipses (grips)
#         # Inner body thicknesses
#         inset_x = 4
#         inset_y = 3
#
#         if connected:
#             # central body
#             self.draw.rectangle((body_left + inset_x, body_top + inset_y, body_right - inset_x, body_bottom - inset_y),
#                                 outline=255, fill=255)
#             # left/right grips as filled ellipses
#             self.draw.ellipse((body_left, body_top + inset_y, body_left + inset_x + 2, body_bottom - inset_y),
#                               outline=255, fill=255)
#             self.draw.ellipse((body_right - inset_x - 2, body_top + inset_y, body_right, body_bottom - inset_y),
#                               outline=255, fill=255)
#         else:
#             self.draw.rectangle((body_left + inset_x, body_top + inset_y, body_right - inset_x, body_bottom - inset_y),
#                                 outline=255, fill=0)
#             self.draw.ellipse((body_left, body_top + inset_y, body_left + inset_x + 2, body_bottom - inset_y),
#                               outline=255, fill=0)
#             self.draw.ellipse((body_right - inset_x - 2, body_top + inset_y, body_right, body_bottom - inset_y),
#                               outline=255, fill=0)
#
#         # D-pad (left): small plus
#         dcx = body_left + 6
#         dcy = (body_top + body_bottom) // 2
#         self.draw.line((dcx - 2, dcy, dcx + 2, dcy), fill=255)
#         self.draw.line((dcx, dcy - 2, dcx, dcy + 2), fill=255)
#
#         # Face buttons (right): two slightly separated
#         b1x = body_right - 7
#         b1y = dcy - 2
#         b2x = body_right - 4
#         b2y = dcy + 2
#         self.draw.ellipse((b1x - 1, b1y - 1, b1x + 1, b1y + 1), outline=255, fill=255 if connected else 0)
#         self.draw.ellipse((b2x - 1, b2y - 1, b2x + 1, b2y + 1), outline=255, fill=255 if connected else 0)
#
#         # Start / Select tiny dots
#         s1x = (body_left + body_right) // 2 - 2
#         s2x = (body_left + body_right) // 2 + 2
#         sy = dcy
#         self.draw.point((s1x, sy), fill=255)
#         self.draw.point((s2x, sy), fill=255)
#
#         if not connected:
#             # strike-through diagonal
#             self.draw.line((body_left, body_top, body_right, body_bottom), fill=255, width=1)
#
#     def _draw_server_icon(self, x: int, y: int, size: int = 9, connected: bool = False):
#         """
#         Draw a simple server connection square (size x size), centered vertically by caller.
#         - Filled if connected
#         - Empty if not
#         """
#         x0, y0 = x, y
#         x1, y1 = x + size, y + size
#         if connected:
#             self.draw.rectangle((x0, y0, x1, y1), outline=255, fill=255)
#         else:
#             self.draw.rectangle((x0, y0, x1, y1), outline=255, fill=0)

from PIL import ImageFont

from robot.utilities.display.display import Page, DISPLAY_HEIGHT, DISPLAY_WIDTH

#
# class StatusPage(Page):
#     def __init__(self):
#         """
#         Initialize the Status page with dynamic elements.
#         """
#         super().__init__(width=DISPLAY_WIDTH, height=DISPLAY_HEIGHT, name="Status", border=True, show_title=False)
#         self.battery_level = "full"  # Options: "empty", "half", "full"
#         self.battery_voltage = "16.8V"
#         self.internet_connected = False
#         self.signal_strength = "none"  # "none", "low", "medium", "high"
#         self.joystick = True
#         self.server_connection = False
#         self.user = "user"
#         self.hostname = "hostname"
#         self.ip_address = "0.0.0.0"
#         self.ssid = "SSID"
#         self.mode = "Idle"
#
#         # Layout tuning
#         self._EXTRA_TOP_BAR = 5
#
#     # ----------------------- setters -----------------------
#     def set_battery(self, level, voltage: float):
#         self.battery_level = level
#         self.battery_voltage = f"{voltage:.1f} V"
#
#     def set_internet_status(self, connected: bool):
#         self.internet_connected = connected
#
#     def set_signal_strength(self, strength: str):
#         if strength not in ("none", "low", "medium", "high"):
#             strength = "none"
#         self.signal_strength = strength
#
#     def set_joystick_status(self, connected: bool):
#         self.joystick = connected
#
#     def set_server_connection(self, connected: bool):
#         self.server_connection = connected
#
#     def set_user_and_hostname(self, user, hostname):
#         self.user = user
#         self.hostname = hostname
#
#     def set_ip_address(self, ip):
#         self.ip_address = ip or ""
#
#     def set_ssid(self, ssid):
#         self.ssid = ssid or ""
#
#     def set_mode(self, mode):
#         self.mode = mode or ""
#
#     # ----------------------- rendering -----------------------
#     def draw_page(self):
#         font = ImageFont.load_default()
#         sep_y = self._draw_status_bar(font)
#
#         start_y = 19
#         line = 11
#         self.draw.text((5, start_y + 0 * line), f"{self.user}@{self.hostname}", font=font, fill=255)
#         self.draw.text((5, start_y + 1 * line), f"IP: {self.ip_address}", font=font, fill=255)
#         self.draw.text((5, start_y + 2 * line), f"SSID: {self.ssid}", font=font, fill=255)
#         self.draw.text((5, start_y + 3 * line), f"Mode: {self.mode}", font=font, fill=255)
#
#     def _draw_status_bar(self, font):
#         bar_top = 0
#         battery_y = 2
#         battery_height = 8
#         base_separator_y = battery_y + battery_height + 2
#         separator_y = base_separator_y + self._EXTRA_TOP_BAR
#
#         def center_y(h: int) -> int:
#             return max(bar_top, (bar_top + separator_y - h) // 2)
#
#         # --- Battery ---
#         battery_x = 2
#         battery_width = 16
#         terminal_width = 2
#         by = center_y(battery_height)
#
#         self.draw.rectangle((battery_x, by, battery_x + battery_width, by + battery_height), outline=255, fill=0)
#         self.draw.rectangle(
#             (battery_x + battery_width, by + 2,
#              battery_x + battery_width + terminal_width, by + battery_height - 2),
#             outline=255, fill=255
#         )
#
#         if self.battery_level == "empty":
#             fill_width = 0
#         elif self.battery_level == "half":
#             fill_width = (battery_width - 2) // 2
#         elif self.battery_level == "full":
#             fill_width = battery_width - 2
#         else:
#             fill_width = 0
#
#         if fill_width > 0:
#             self.draw.rectangle(
#                 (battery_x + 1, by + 1, battery_x + 1 + fill_width, by + battery_height - 1),
#                 outline=255, fill=255
#             )
#
#         text_x = battery_x + battery_width + terminal_width + 4
#         self.draw.text((text_x, by - 1), self.battery_voltage, font=font, fill=255)
#
#         # Horizontal offset for icons after battery
#         offset_x = text_x + 40  # space after voltage text
#         shift_left = -4  # move icons 4px left
#
#         # --- Joystick ---
#         pad_x = offset_x + shift_left
#         pad_h = 14
#         pad_y = center_y(pad_h)
#         if self.joystick:
#             self._draw_gamepad_icon(pad_x, pad_y, height=pad_h)
#
#         # leave space for joystick whether drawn or not
#         after_joystick_x = pad_x + 22
#
#         # --- Signal Strength ---
#         signal_x = after_joystick_x + shift_left
#         bar_heights = [5, 8, 11]
#         bar_w, gap = 2, 2
#         total_height = max(bar_heights)
#         sy = center_y(total_height + 1)
#         self._draw_signal_bars(signal_x, sy, heights=bar_heights, bar_w=bar_w, gap=gap,
#                                strength=self.signal_strength, connected=self.internet_connected)
#
#         # --- Internet ---
#         internet_x = signal_x + 14 + shift_left
#         internet_size = 8
#         iy = center_y(internet_size)
#         if self.internet_connected:
#             self.draw.ellipse((internet_x, iy, internet_x + internet_size, iy + internet_size),
#                               outline=255, fill=255)
#         else:
#             self.draw.ellipse((internet_x, iy, internet_x + internet_size, iy + internet_size),
#                               outline=255, fill=0)
#             self.draw.line((internet_x, iy, internet_x + internet_size, iy + internet_size),
#                            fill=255, width=1)
#
#         # --- Server ---
#         server_size = 9
#         server_x = internet_x + 12 + shift_left
#         server_y = center_y(server_size)
#         self._draw_server_icon(server_x, server_y, size=server_size, connected=self.server_connection)
#
#         # Separator line
#         self.draw.line((0, separator_y, self.width, separator_y), fill=255)
#
#         return separator_y
#
#     # ----------------------- icon helpers -----------------------
#     def _draw_signal_bars(self, x: int, y: int, heights=(5, 8, 11), bar_w=2, gap=2,
#                           strength: str = "none", connected: bool = True):
#         levels = {"none": 0, "low": 1, "medium": 2, "high": 3}
#         fill_count = levels.get(strength, 0)
#         if not connected:
#             fill_count = 0
#
#         max_h = max(heights)
#         baseline = y + max_h - 1
#
#         for i, h in enumerate(heights):
#             bx0 = x + i * (bar_w + gap)
#             bx1 = bx0 + bar_w
#             by0 = baseline - (h - 1)
#             by1 = baseline
#             self.draw.rectangle((bx0, by0, bx1, by1),
#                                 outline=255, fill=255 if i < fill_count else 0)
#
#         if not connected:
#             total_w = (bar_w + gap) * 3 - gap
#             self.draw.line((x - 1, baseline - max_h + 1,
#                             x + total_w + 1, baseline), fill=255, width=1)
#
#     def _draw_gamepad_icon(self, x: int, y: int, height: int = 14):
#         """
#         Outline-only gamepad with analog stick and two face buttons.
#         """
#         h = max(12, height)
#         w = 20
#         body_top, body_bottom = y, y + h
#         body_left, body_right = x, x + w
#         inset_x, inset_y = 4, 3
#
#         # Outline body
#         self.draw.rectangle((body_left + inset_x, body_top + inset_y,
#                              body_right - inset_x, body_bottom - inset_y),
#                             outline=255, fill=0)
#         self.draw.ellipse((body_left, body_top + inset_y,
#                            body_left + inset_x + 2, body_bottom - inset_y),
#                           outline=255, fill=0)
#         self.draw.ellipse((body_right - inset_x - 2, body_top + inset_y,
#                            body_right, body_bottom - inset_y),
#                           outline=255, fill=0)
#
#         # Analog stick (left side, filled)
#         stick_cx = body_left + 6
#         stick_cy = (body_top + body_bottom) // 2
#         self.draw.ellipse((stick_cx - 2, stick_cy - 2,
#                            stick_cx + 2, stick_cy + 2), outline=255, fill=255)
#
#         # Two face buttons (right side, filled)
#         b1x, b1y = body_right - 7, stick_cy - 2
#         b2x, b2y = body_right - 4, stick_cy + 2
#         self.draw.ellipse((b1x - 1, b1y - 1, b1x + 1, b1y + 1), outline=255, fill=255)
#         self.draw.ellipse((b2x - 1, b2y - 1, b2x + 1, b2y + 1), outline=255, fill=255)
#
#     def _draw_server_icon(self, x: int, y: int, size: int = 9, connected: bool = False):
#         x0, y0 = x, y
#         x1, y1 = x + size, y + size
#         if connected:
#             self.draw.rectangle((x0, y0, x1, y1), outline=255, fill=255)
#         else:
#             self.draw.rectangle((x0, y0, x1, y1), outline=255, fill=0)


from PIL import ImageFont

from robot.utilities.display.display import Page, DISPLAY_HEIGHT, DISPLAY_WIDTH

from PIL import ImageFont

from robot.utilities.display.display import Page, DISPLAY_HEIGHT, DISPLAY_WIDTH


class StatusPage(Page):
    def __init__(self):
        super().__init__(width=DISPLAY_WIDTH, height=DISPLAY_HEIGHT, name="Status", border=True, show_title=False)
        self.battery_level = "full"
        self.battery_voltage = "16.8V"
        self.internet_connected = False
        self.signal_strength = "none"
        self.joystick = True
        self.server_connection = False
        self.user = "user"
        self.hostname = "hostname"
        self.ip_address = "0.0.0.0"
        self.ssid = "SSID"
        self.mode = "Idle"
        self._EXTRA_TOP_BAR = 5

    def set_battery(self, level, voltage: float):
        self.battery_level = level
        self.battery_voltage = f"{voltage:.1f} V"

    def set_internet_status(self, connected: bool):
        self.internet_connected = connected

    def set_signal_strength(self, strength: str):
        if strength not in ("none", "low", "medium", "high"):
            strength = "none"
        self.signal_strength = strength

    def set_joystick_status(self, connected: bool):
        self.joystick = connected

    def set_server_connection(self, connected: bool):
        self.server_connection = connected

    def set_user_and_hostname(self, user, hostname):
        self.user = user
        self.hostname = hostname

    def set_ip_address(self, ip):
        self.ip_address = ip or ""

    def set_ssid(self, ssid):
        self.ssid = ssid or ''

    def set_mode(self, mode):
        self.mode = mode or ''

    def draw_page(self):
        font = ImageFont.load_default()
        sep_y = self._draw_status_bar(font)

        start_y = 18
        start_x = 4
        line = 11
        self.draw.text((start_x, start_y + 0 * line), f"{self.user}@{self.hostname}", font=font, fill=255)
        self.draw.text((start_x, start_y + 1 * line), f"IP: {self.ip_address}", font=font, fill=255)
        self.draw.text((start_x, start_y + 2 * line), f"SSID: {self.ssid}", font=font, fill=255)
        self.draw.text((start_x, start_y + 3 * line), f"Mode: {self.mode}", font=font, fill=255)

    def _draw_status_bar(self, font):
        bar_top = 0
        battery_y = 2
        battery_height = 8
        base_separator_y = battery_y + battery_height + 2
        separator_y = base_separator_y + self._EXTRA_TOP_BAR

        def center_y(h: int) -> int:
            return max(bar_top, (bar_top + separator_y - h) // 2)

        # Battery
        battery_x = 2
        battery_width = 16
        terminal_width = 2
        by = center_y(battery_height)

        self.draw.rectangle((battery_x, by, battery_x + battery_width, by + battery_height), outline=255, fill=0)
        self.draw.rectangle((battery_x + battery_width, by + 2,
                             battery_x + battery_width + terminal_width, by + battery_height - 2),
                            outline=255, fill=255)

        if self.battery_level == "empty":
            fill_width = 0
        elif self.battery_level == "half":
            fill_width = (battery_width - 2) // 2
        elif self.battery_level == "full":
            fill_width = battery_width - 2
        else:
            fill_width = 0

        if fill_width > 0:
            self.draw.rectangle((battery_x + 1, by + 1,
                                 battery_x + 1 + fill_width, by + battery_height - 1),
                                outline=255, fill=255)

        text_x = battery_x + battery_width + terminal_width + 4
        self.draw.text((text_x, by - 1), self.battery_voltage, font=font, fill=255)

        # Icon layout
        start_icons_x = battery_x + battery_width + terminal_width + 41  # was 46, now 5px left
        cursor_x = start_icons_x
        GAP = 5  # reduced gap

        # Joystick
        JOY_H, JOY_W = 14, 22
        joy_y = center_y(JOY_H)
        if self.joystick:
            self._draw_gamepad_icon(cursor_x, joy_y, height=JOY_H)
        cursor_x += JOY_W + GAP

        # Signal strength
        SIG_BAR_W, SIG_GAP = 2, 2
        SIG_HEIGHTS = [5, 8, 11]
        sig_total_w = SIG_BAR_W * 3 + SIG_GAP * 2
        sy = center_y(max(SIG_HEIGHTS) + 1)
        self._draw_signal_bars(cursor_x, sy, heights=SIG_HEIGHTS, bar_w=SIG_BAR_W, gap=SIG_GAP,
                               strength=self.signal_strength, connected=self.internet_connected)
        cursor_x += sig_total_w + GAP

        # Internet
        NET_SIZE = 8
        iy = center_y(NET_SIZE)
        if self.internet_connected:
            self.draw.ellipse((cursor_x, iy, cursor_x + NET_SIZE, iy + NET_SIZE), outline=255, fill=255)
        else:
            self.draw.ellipse((cursor_x, iy, cursor_x + NET_SIZE, iy + NET_SIZE), outline=255, fill=0)
            self.draw.line((cursor_x, iy, cursor_x + NET_SIZE, iy + NET_SIZE), fill=255, width=1)
        cursor_x += NET_SIZE + GAP

        # Server
        SRV_SIZE = 9
        server_y = center_y(SRV_SIZE)
        self._draw_server_icon(cursor_x, server_y, size=SRV_SIZE, connected=self.server_connection)

        self.draw.line((0, separator_y, self.width, separator_y), fill=255)
        return separator_y

    def _draw_signal_bars(self, x: int, y: int, heights=(5, 8, 11), bar_w=2, gap=2,
                          strength: str = "none", connected: bool = True):
        levels = {"none": 0, "low": 1, "medium": 2, "high": 3}
        fill_count = levels.get(strength, 0)
        if not connected:
            fill_count = 0

        max_h = max(heights)
        baseline = y + max_h

        for i, h in enumerate(heights):
            bx0 = x + i * (bar_w + gap)
            bx1 = bx0 + bar_w
            by0 = baseline - (h - 1)
            by1 = baseline
            self.draw.rectangle((bx0, by0, bx1, by1), outline=255, fill=255 if i < fill_count else 0)

        if not connected:
            total_w = (bar_w + gap) * 3 - gap
            self.draw.line((x - 1, baseline - max_h + 1,
                            x + total_w + 1, baseline), fill=255, width=1)

    # def _draw_gamepad_icon(self, x: int, y: int, height: int = 14):
    #     h = max(12, height)
    #     w = 20
    #     body_top, body_bottom = y, y + h
    #     body_left, body_right = x, x + w
    #     inset_x, inset_y = 4, 3
    #
    #     self.draw.ellipse((body_left, body_top + inset_y,
    #                        body_left + inset_x + 2, body_bottom - inset_y),
    #                       outline=255, fill=0)
    #     self.draw.ellipse((body_right - inset_x - 2, body_top + inset_y,
    #                        body_right, body_bottom - inset_y),
    #                       outline=255, fill=0)
    #
    #     self.draw.rectangle((body_left + inset_x, body_top + inset_y,
    #                          body_right - inset_x, body_bottom - inset_y),
    #                         outline=255, fill=0)
    #
    #     stick_cx = body_left + 6
    #     stick_cy = (body_top + body_bottom) // 2
    #     self.draw.ellipse((stick_cx - 2, stick_cy - 2,
    #                        stick_cx + 2, stick_cy + 2), outline=255, fill=255)
    #
    #     b1x, b1y = body_right - 7, stick_cy - 2
    #     b2x, b2y = body_right - 4, stick_cy + 2
    #     self.draw.ellipse((b1x - 1, b1y - 1, b1x + 1, b1y + 1), outline=255, fill=255)
    #     self.draw.ellipse((b2x - 1, b2y - 1, b2x + 1, b2y + 1), outline=255, fill=255)

    # def _draw_gamepad_icon(self, x: int, y: int, height: int = 14):
    #     """
    #     Outline-only gamepad with clean grips:
    #       - First draw the left/right grip ellipses (outlines),
    #       - Then "erase" any ellipse lines inside the body with a black-filled mask rectangle,
    #       - Finally draw the body outline rectangle,
    #       - Add the filled analog stick (left) and two filled face buttons (right).
    #     """
    #     h = max(12, height)
    #     w = 20
    #     body_top, body_bottom = y, y + h
    #     body_left, body_right = x, x + w
    #     inset_x, inset_y = 4, 3
    #
    #     # 1) Grips (ellipses) OUTLINES
    #     self.draw.ellipse(
    #         (body_left, body_top + inset_y, body_left + inset_x + 2, body_bottom - inset_y),
    #         outline=255, fill=0
    #     )
    #     self.draw.ellipse(
    #         (body_right - inset_x - 2, body_top + inset_y, body_right, body_bottom - inset_y),
    #         outline=255, fill=0
    #     )
    #
    #     # 2) Mask rectangle to remove inner halves of ellipses
    #     #    (fills the central body area with black, erasing any overlap lines)
    #     mask_rect = (body_left + inset_x, body_top + inset_y, body_right - inset_x, body_bottom - inset_y)
    #     self.draw.rectangle(mask_rect, outline=0, fill=0)
    #
    #     # 3) Body outline rectangle (no fill)
    #     # self.draw.rectangle(mask_rect, outline=255, fill=0)
    #
    #     # 4) Analog stick (left, filled)
    #     stick_cx = body_left + 6
    #     stick_cy = (body_top + body_bottom) // 2
    #     self.draw.ellipse(
    #         (stick_cx - 2, stick_cy - 2, stick_cx + 2, stick_cy + 2),
    #         outline=255, fill=255
    #     )
    #
    #     # 5) Two face buttons (right, filled)
    #     b1x, b1y = body_right - 7, stick_cy - 2
    #     b2x, b2y = body_right - 4, stick_cy + 2
    #     self.draw.ellipse((b1x - 1, b1y - 1, b1x + 1, b1y + 1), outline=255, fill=255)
    #     self.draw.ellipse((b2x - 1, b2y - 1, b2x + 1, b2y + 1), outline=255, fill=255)

    def _draw_gamepad_icon(self, x: int, y: int, height: int = 16):
        """
        Outline-only gamepad with clean grips:
          - Draw left/right grip ellipses,
          - Erase overlap with central body area,
          - Draw only the top and bottom edges of the body,
          - Add filled analog stick (left) and two filled buttons (right).
        """
        h = max(12, height)
        w = 20
        body_top, body_bottom = y, y + h
        body_left, body_right = x, x + w
        inset_x, inset_y = 4, 2

        # 1) Grips (ellipses) OUTLINES
        self.draw.ellipse(
            (body_left, body_top + inset_y, body_left + inset_x + 2, body_bottom - inset_y),
            outline=255, fill=0
        )
        self.draw.ellipse(
            (body_right - inset_x - 2, body_top + inset_y, body_right, body_bottom - inset_y),
            outline=255, fill=0
        )

        # 2) Mask rectangle to remove inner halves of ellipses
        mask_rect = (body_left + inset_x, body_top + inset_y, body_right - inset_x, body_bottom - inset_y)
        self.draw.rectangle(mask_rect, outline=0, fill=0)

        # 3) Draw only top and bottom edges of the body
        self.draw.line((body_left + inset_x, body_top + inset_y, body_right - inset_x, body_top + inset_y), fill=255)
        self.draw.line((body_left + inset_x, body_bottom - inset_y, body_right - inset_x, body_bottom - inset_y),
                       fill=255)

        # 4) Analog stick (left, filled)
        stick_cx = body_left + 6
        stick_cy = (body_top + body_bottom) // 2
        self.draw.ellipse(
            (stick_cx - 2, stick_cy - 2, stick_cx + 2, stick_cy + 2),
            outline=255, fill=255
        )

        # 5) Two face buttons (right, filled)
        b1x, b1y = body_right - 7, stick_cy - 2
        b2x, b2y = body_right - 4, stick_cy + 2
        self.draw.ellipse((b1x - 1, b1y - 1, b1x + 1, b1y + 1), outline=255, fill=255)
        self.draw.ellipse((b2x - 1, b2y - 1, b2x + 1, b2y + 1), outline=255, fill=255)

    def _draw_server_icon(self, x: int, y: int, size: int = 9, connected: bool = False):
        x0, y0 = x, y
        x1, y1 = x + size, y + size
        if connected:
            self.draw.rectangle((x0, y0, x1, y1), outline=255, fill=255)
        else:
            self.draw.rectangle((x0, y0, x1, y1), outline=255, fill=0)
