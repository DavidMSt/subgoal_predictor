# extensions/control_gui/src/lib/widgets/video_widget.py

from typing import Any

from extensions.gui.src.lib.objects.objects import Widget


class VideoWidget(Widget):
    """
    Backend VideoWidget

    Config keys:
      - video_path (str): URL of the video to play
      - title (str|None): optional tooltip/text
      - fit (str): one of 'contain'|'cover'|'fill'.
        If you want no cropping and to see the entire video, choose contain.
        If you want to fill the widget and are okay with cropping off edges, choose cover.
        If you actually want to stretch (ignore aspect ratio), choose fill.
      - enable_enlarge (bool): show “enlarge” overlay button
      - enlarge_percentage (int): percent scale when enlarged
      - enable_fullscreen (bool): show “fullscreen” button
      - clickable (bool): if True, emit click events to Python via handleEvent
    """
    type = 'video'
    video_path: str = None

    def __init__(self, widget_id: str, path: str, stream_type: str = 'mjpeg', **kwargs):
        super().__init__(widget_id)

        default_config = {
            'title': None,
            'title_color': [1, 1, 1],
            'title_font_size': 12,
            'fit': 'contain',
            'enable_enlarge': True,
            'enlarge_size': 0.75,
            'enlarge_opacity': 0.85,
            'enable_fullscreen': True,
            'clickable': False,
        }

        # merge user overrides
        self.config = {**default_config, **kwargs}

        assert self.config['fit'] in ['contain', 'cover', 'fill']

        self.video_path = path
        self.stream_type = stream_type

    def getConfiguration(self) -> dict:
        # Called by the framework to serialize this widget to the client
        return {
            'video_path': self.video_path,
            'stream_type': self.stream_type,
            **self.config
        }

    def init(self, *args, **kwargs):
        # Called once after widget is created; parent will push getConfiguration()
        super().init(*args, **kwargs)

    def handleEvent(self, message, sender=None) -> Any:
        """
        Handle messages from the frontend:
          - event: 'click' if clickable
          - event: 'enlarge' when user taps the enlarge button
          - event: 'fullscreen' when user taps the fullscreen button
          - event: 'close' when user closes the overlay
        """
        mtype = message.get('type')
        data = message.get('data', {})
        if mtype == 'event':
            ev = data.get('event')
            # You can hook these into your app:
            if ev == 'click':
                self.handle_click()
            elif ev == 'enlarge':
                self.handle_enlarge()
            elif ev == 'fullscreen':
                self.handle_fullscreen()
            elif ev == 'close':
                self.handle_close()
        # pass to base in case it does something

    # Example stubs you might override in your app:
    def handle_click(self):
        print(f"[VideoWidget:{self.id}] clicked")

    def handle_enlarge(self):
        print(f"[VideoWidget:{self.id}] enlarge requested")

    def handle_fullscreen(self):
        print(f"[VideoWidget:{self.id}] fullscreen requested")

    def handle_close(self):
        print(f"[VideoWidget:{self.id}] close overlay")
