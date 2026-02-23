from luma.core.interface.serial import i2c, spi
from luma.oled.device import sh1106
from PIL import Image, ImageDraw, ImageFont
import time
import threading

DISPLAY_WIDTH = 128
DISPLAY_HEIGHT = 64


class Display:

    thread: threading.Thread | None = None

    def __init__(self, i2c_port=1, i2c_address=0x3C, fps=2, page_display_duration=2, page_border_thickness=3):
        """
        Initialize the SH1106 OLED display with multi-page support and optimized threading.
        """
        self.serial = i2c(port=i2c_port, address=i2c_address)
        self.device = sh1106(self.serial)
        self.width = self.device.width
        self.height = self.device.height
        self.pages = {}
        self.current_page = None
        self.previous_page = None
        self.running = False
        self.frame = 0
        self.fps = fps
        self.page_display_duration = page_display_duration
        self.page_border_thickness = page_border_thickness
        self.update_lock = threading.Lock()

        # Add the Default Page and start with it
        default_page = DefaultPage(self.width, self.height)
        self.add_page(default_page)
        self.change_page("Default Page", start_thread=False)

        # Add the Text Page
        text_page = TextPage(self.width, self.height)
        self.add_page(text_page)

        # Clear the display
        self._clear_display()

    def _clear_display(self):
        """Clear the display to ensure no residual content."""
        blank_image = Image.new("1", (self.width, self.height), 0)  # All black
        self.device.display(blank_image)

    def add_page(self, page):
        """Add a page to the display."""
        self.pages[page.name] = page
        if hasattr(page, "display_image"):
            page.display_image = self.display_image
        if self.current_page is None:
            self.current_page = page

    def change_page(self, name, return_time=None, start_thread=True):
        """Change the current page to the specified name."""
        if name not in self.pages:
            print(f"Page '{name}' does not exist.")
            return

        # Cancel any existing return timer if a new page change is requested
        with self.update_lock:
            if self.previous_page and self.previous_page.name == name:
                self.previous_page = None

            # Set the previous page only if switching to a different page
            if self.current_page and self.current_page.name != name:
                self.previous_page = self.current_page

            # Check if the page should show a title before rendering
            page = self.pages[name]
            if page.show_title:
                self._show_page_name(name)

            # Set the new page and force a redraw
            self.current_page = page
            self.current_page.update_page(self.frame)
            self.display_image(self.current_page.image)

            # Handle return timer if needed
            if return_time is not None:
                threading.Timer(return_time, self._return_to_previous_page).start()

        # Start the thread only if required
        if start_thread and not self.running:
            self.start()

    def _return_to_previous_page(self):
        """Return to the previous page."""
        if self.previous_page:
            self.change_page(self.previous_page.name)

    def _show_page_name(self, name):
        """Display the page name in the center of the screen with a border."""
        image = Image.new("1", (self.width, self.height))
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()

        # Draw the border
        for i in range(self.page_border_thickness):
            draw.rectangle((i, i, self.width - 1 - i, self.height - 1 - i), outline=255, fill=0)

        # Center the text
        text_bbox = draw.textbbox((0, 0), name, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]

        x = (self.width - text_width) // 2
        y = (self.height - text_height) // 2

        draw.text((x, y), name, font=font, fill=255)
        self.device.display(image)  # Display title directly to avoid threading issues

        # Wait for the title display duration
        time.sleep(self.page_display_duration)

    def update(self):
        """Always redraw the current page dynamically."""
        with self.update_lock:
            if self.current_page:
                self.current_page.update_page(self.frame)  # Perform dynamic updates
                self.display_image(self.current_page.image)  # Display the updated page
                self.frame += 1

    def display_image(self, image):
        """Render the given image to the display."""
        try:
            self.device.display(image)
        except Exception as e:
            ...

    def start(self):
        """Start the display thread."""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()

    def stop(self):
        """Stop the display thread."""
        self.running = False
        self.device.clear()
        self.device.cleanup()

    def _run(self):
        """Thread function to update the display at the specified FPS."""
        while self.running:
            start_time = time.time()
            self.update()
            time.sleep(max(0.0, 1 / self.fps - (time.time() - start_time)))

    def displayText(self, text, return_time=2):
        """Display the given text on the TextPage and switch to it."""
        text_page = self.pages.get("Text Page")
        if text_page:
            text_page.set_text(text)
            self.change_page("Text Page", return_time=return_time)


# Ensure to include the lowlevel for `DefaultPage` and `TextPage` for the code to function.


class Page:
    def __init__(self, width, height, name="Page", border=False, show_title=True):
        """
        Initialize a page with a specified width and height.
        :param width: Width of the page
        :param height: Height of the page
        :param name: Name of the page
        :param border: Whether to render a 1px border around the page
        :param show_title: Whether to show the page title before rendering
        """
        self.width = width
        self.height = height
        self.name = name
        self.border = border  # Enable or disable page border
        self.show_title = show_title  # Enable or disable showing the title screen
        self.image = Image.new("1", (self.width, self.height))
        self.draw = ImageDraw.Draw(self.image)

    def draw_page(self):
        """
        Draw the static components of the page.
        Child classes should override this method to draw their content.
        """
        raise NotImplementedError("Subclasses must implement draw_page")

    def update_page(self, frame):
        """
        Update the dynamic components of the page.
        The default behavior includes rendering a border if enabled.
        """
        # Clear the page before drawing
        self.image = Image.new("1", (self.width, self.height), 0)  # Clear screen
        self.draw = ImageDraw.Draw(self.image)  # Reinitialize draw object

        # Render border if enabled
        if self.border:
            self.draw.rectangle(
                (0, 0, self.width - 1, self.height - 1),
                outline=255,
                fill=0,
            )

        # Allow child classes to render their content
        self.draw_page()


class DefaultPage(Page):
    def __init__(self, width, height):
        """Initialize a blank default page."""
        super().__init__(width, height, name="Default Page", border=False, show_title=False)

    def draw_page(self):
        """Draw nothing, keeping the page blank."""
        pass


class TextPage(Page):
    def __init__(self, width, height):
        """Initialize a text page."""
        super().__init__(width, height, name="Text Page", border=False, show_title=False)
        self.text = ""

    def set_text(self, text):
        """Set the text to be displayed on the page."""
        self.text = text
        self.update_page(0)  # Force an update to render the new text

    def draw_page(self):
        """Draw the text dynamically scaled to fit within the screen."""
        # Define the font path and the range of font sizes to try
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"  # Adjust the path to a font file you have
        max_font_size = 48  # Start with a large font size
        min_font_size = 8  # Minimum font size

        for font_size in range(max_font_size, min_font_size - 1, -1):  # Start large, go smaller
            font = ImageFont.truetype(font_path, font_size)
            text_bbox = self.draw.textbbox((0, 0), self.text, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]

            # Check if the text fits within the screen
            if text_width <= self.width and text_height <= self.height:
                break  # Found the largest font size that fits

        # Calculate coordinates to center the text
        x = (self.width - text_width) // 2
        y = (self.height - text_height) // 2

        # Draw the text
        self.draw.text((x, y), self.text, font=font, fill=255)  # Draw the text centered
