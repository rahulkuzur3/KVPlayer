import os
import sys
import threading

# --- FIX: Disable Kivy's default multitouch simulation ---
from kivy.config import Config
Config.set('input', 'mouse', 'mouse,disable_multitouch')

# --- CRITICAL: Set the Kivy video provider ---
os.environ['KIVY_VIDEO'] = 'ffpyplayer'

# --- THE DEFINITIVE FIX FOR THE 'register' ImportError ---
from kivy.core.text import LabelBase

def resource_path(relative_path: str) -> str:
    """
    Get the absolute path to a resource. This works for development,
    PyInstaller, and Snap packages.
    """
    # Check for PyInstaller's temporary folder (_MEIPASS)
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    # Check for Snap package environment
    elif "SNAP" in os.environ:
        base_path = os.path.join(os.environ["SNAP"], "assets")
    # Default to local directory for development
    else:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

# Register the Font Awesome font file with a simple, accessible name
LabelBase.register(
    name='FontAwesome',
    fn_regular=resource_path('font.otf')
)
# --- END OF FONT FIX ---


from kivy.app import App
from kivy.uix.floatlayout import FloatLayout
from kivy.core.window import Window
from kivy.properties import (
    ObjectProperty, StringProperty, BooleanProperty, ListProperty, NumericProperty
)
from kivy.clock import Clock
from kivy.animation import Animation
from kivy.logger import Logger
from plyer import filechooser
from kivy.uix.dropdown import DropDown
from kivy.uix.button import Button
from kivy.metrics import dp

Logger.setLevel('INFO')

class PlayerLayout(FloatLayout):
    """
    The root layout for the player, managing video playback, UI state,
    and all user interactions.
    """
    video = ObjectProperty(None)
    controls = ObjectProperty(None)
    view_mode = StringProperty('welcome')
    is_playing = BooleanProperty(False)
    is_muted = BooleanProperty(False)
    is_slider_touched = BooleanProperty(False)
    is_fullscreen = BooleanProperty(False)
    hide_controls_trigger = ObjectProperty(None, allownone=True)
    current_time_str = StringProperty("00:00")
    total_time_str = StringProperty("00:00")
    error_message = StringProperty('')
    volume_icon = StringProperty('\uf028')
    audio_tracks = ListProperty([])
    active_audio_track_index = NumericProperty(-1)
    audio_dropdown = ObjectProperty(None, allownone=True)
    _audio_tracks_populated = BooleanProperty(False)

    def __init__(self, **kwargs):
        """
        Constructor: Binds window events to methods and initializes properties.
        """
        super().__init__(**kwargs)
        self.volume_before_mute = 1.0

        Window.bind(on_drop_file=self._on_file_drop)
        Window.bind(on_key_down=self._on_key_down)
        Window.bind(mouse_pos=self.on_mouse_move)

        # --- PERFORMANCE FIX ---
        # Reduce the frequency of UI updates from 30fps to 4fps.
        Clock.schedule_interval(self.update_ui, 1.0 / 4.0)

    def _on_file_drop(self, window, file_path_bytes: bytes, *args) -> None:
        """Handles file drop events onto the window."""
        try:
            self.load_file(file_path_bytes.decode('utf-8'))
        except Exception as e:
            self.display_error(f"Could not read dropped file: {e}")
            Logger.error(f"File Drop Failed: {e}")

    def _on_key_down(self, window, key: int, *args) -> None:
        """Handles keyboard shortcuts for player control."""
        if self.view_mode == 'player':
            if key == 32: self.toggle_play_pause()
            elif key == 276: self.seek_relative(-10)
            elif key == 275: self.seek_relative(10)
            elif key == 102: self.toggle_fullscreen()
            elif key == 109: self.toggle_mute()

    def load_file(self, file_path: str) -> None:
        """Loads and starts playing a video file."""
        self.error_message = ''
        if not file_path or not os.path.exists(file_path):
            self.display_error(f"File not found:\n{file_path}")
            return
        try:
            self.video.source = file_path
            self.video.state = 'play'
            self.view_mode = 'player'
        except Exception as e:
            self.display_error(f"Could not play file (unsupported format?):\n{os.path.basename(file_path)}")
            Logger.error(f"FFPyplayer failed to load {file_path}: {e}")

    def display_error(self, message: str) -> None:
        """Shows an error message on the welcome screen."""
        self.error_message = message
        self.view_mode = 'welcome'
        self.video.source = ''

    def on_video_source_change(self, instance, new_source: str) -> None:
        """Triggered when the video source is changed."""
        if new_source:
            App.get_running_app().title = os.path.splitext(os.path.basename(new_source))[0]
            self._audio_tracks_populated = False
            self.show_controls()
        else:
            self.audio_tracks = []

    def populate_audio_tracks(self):
        """Inspects the loaded video for available audio streams."""
        self.audio_tracks = []
        if not hasattr(self.video, '_player') or not self.video._player:
            return

        try:
            metadata = self.video._player.get_metadata()
            streams = metadata.get('streams', [])
            for stream in streams:
                if stream.get('codec_type') == 'audio':
                    track_index = stream.get('index', -1)
                    tags = stream.get('tags', {})
                    lang = tags.get('language', 'und')
                    title = tags.get('title', f"Track {track_index}")
                    self.audio_tracks.append({'index': track_index, 'language': lang, 'title': title})
            
            current_streams = self.video._player.get_streams()
            if len(current_streams) > 1:
                self.active_audio_track_index = current_streams[1]
        except Exception as e:
            Logger.error(f"Could not get audio track metadata: {e}")

    def open_audio_track_menu(self, button):
        """Opens a dropdown menu to select an audio track."""
        if not self.audio_tracks: return
        if self.audio_dropdown: self.audio_dropdown.dismiss()
        
        self.audio_dropdown = DropDown()
        for i, track in enumerate(self.audio_tracks):
            track_name = f"{track['language'].upper()}: {track['title']}"
            btn = Button(text=track_name, size_hint_y=None, height=dp(44))
            btn.bind(on_release=lambda b, t=track['index']: self.set_audio_track(t))
            self.audio_dropdown.add_widget(btn)
        
        self.audio_dropdown.open(button)

    def set_audio_track(self, track_index: int):
        """Sets the active audio stream for the video."""
        if hasattr(self.video, '_player') and self.video._player and track_index != -1:
            try:
                self.video._player.set_streams(-1, track_index)
                self.active_audio_track_index = track_index
                if self.audio_dropdown: self.audio_dropdown.dismiss()
            except Exception as e:
                Logger.error(f"Failed to set audio track to {track_index}: {e}")
    
    def on_video_state_change(self, instance, new_state: str) -> None:
        """Updates the is_playing property based on the video's state."""
        self.is_playing = (new_state == 'play')

    def open_file_dialog(self) -> None:
        """
        Opens the native file chooser dialog in a separate thread to prevent
        the UI from freezing.
        """
        was_playing = self.is_playing
        if was_playing: self.video.state = 'pause'

        def on_selection_thread_safe(selection):
            """Callback that runs when the user selects a file."""
            if selection:
                Clock.schedule_once(lambda dt: self.load_file(selection[0]))
            elif was_playing:
                Clock.schedule_once(lambda dt: setattr(self.video, 'state', 'play'))

        thread = threading.Thread(target=lambda: filechooser.open_file(on_selection=on_selection_thread_safe))
        thread.daemon = True
        thread.start()

    def toggle_play_pause(self) -> None:
        """Toggles the video between play and pause states."""
        self.video.state = 'pause' if self.is_playing else 'play'

    def stop_playback(self) -> None:
        """Stops playback and returns to the welcome screen."""
        self.video.state = 'stop'
        self.video.source = ''
        self.view_mode = 'welcome'
        App.get_running_app().title = "KV Player"

    def on_video_eos(self, instance, value: bool) -> None:
        """Called when the video reaches its end (End of Stream)."""
        if value: self.stop_playback()

    def seek(self, normalized_value: float) -> None:
        """Seeks the video to a position based on a normalized value (0.0 to 1.0)."""
        if self.video.duration > 0:
            self.video.seek(normalized_value)

    def seek_relative(self, seconds: int) -> None:
        """Jumps forward or backward in the video by a number of seconds."""
        if self.video.duration > 0:
            new_position = self.video.position + seconds
            self.video.seek(new_position / self.video.duration)

    def format_time(self, seconds: float) -> str:
        """Converts seconds into a readable HH:MM:SS or MM:SS format."""
        if not isinstance(seconds, (int, float)) or seconds < 0: return "00:00"
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d}" if h > 0 else f"{int(m):02d}:{int(s):02d}"

    def update_ui(self, dt: float) -> None:
        """
        This method is called regularly to keep the UI in sync with the video.
        Its frequency is reduced to prevent performance issues.
        """
        if self.view_mode == 'player' and not self._audio_tracks_populated:
            if hasattr(self.video, '_player') and self.video._player:
                self.populate_audio_tracks()
                self._audio_tracks_populated = True

        if self.video.duration > 0 and self.view_mode == 'player':
            self.current_time_str = self.format_time(self.video.position)
            self.total_time_str = self.format_time(self.video.duration)
            if not self.is_slider_touched and self.video.duration > 0:
                self.ids.position_slider.value_normalized = self.video.position / self.video.duration

    def toggle_mute(self) -> None:
        """Toggles the video volume on and off."""
        self.is_muted = not self.is_muted
        if self.is_muted:
            self.volume_before_mute = self.video.volume
            self.video.volume = 0
        else:
            self.video.volume = self.volume_before_mute
        self.update_volume_icon(self.video.volume)

    def on_volume_change(self, value: float) -> None:
        """Called when the volume slider's value changes."""
        self.video.volume = value
        self.is_muted = (value == 0)
        if not self.is_muted: self.volume_before_mute = value
        self.update_volume_icon(value)

    def update_volume_icon(self, volume: float) -> None:
        """Changes the volume icon based on the current volume level."""
        if self.is_muted or volume == 0: self.volume_icon = '\uf6a9'
        elif volume < 0.5: self.volume_icon = '\uf027'
        else: self.volume_icon = '\uf028'

    def toggle_fullscreen(self) -> None:
        """Toggles the application window between fullscreen and windowed mode."""
        self.is_fullscreen = not self.is_fullscreen
        Window.fullscreen = 'auto' if self.is_fullscreen else False

    def on_mouse_move(self, window, pos: tuple) -> None:
        """
        Shows the controls when the mouse is near the bottom of the screen,
        and schedules them to hide after a delay.
        """
        if self.view_mode != 'player': return
        y_coord_normalized = pos[1] / self.height
        
        if y_coord_normalized < 0.15 or self.controls.collide_point(*pos):
            self.show_controls()
        else:
            if self.hide_controls_trigger is None:
                self.hide_controls_trigger = Clock.schedule_once(self.hide_controls, 3)

    def show_controls(self) -> None:
        """Animates the control panel into view and cancels any pending hide event."""
        Animation(y=0, d=0.2, t='out_quad').start(self.controls)
        if self.hide_controls_trigger:
            self.hide_controls_trigger.cancel()
            self.hide_controls_trigger = None

    def hide_controls(self, *args) -> None:
        """Animates the control panel out of view."""
        Animation(y=-self.controls.height, d=0.2, t='in_quad').start(self.controls)
        self.hide_controls_trigger = None

class KVPlayerApp(App):
    """The main Kivy application class."""
    def build(self):
        """Initializes the application and returns the root widget."""
        self.title = "KV Player"
        self.icon = resource_path('icon.png')
        return PlayerLayout()

if __name__ == '__main__':
    KVPlayerApp().run()
