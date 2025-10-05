import os
import sys
import threading

# --- CRITICAL: Set the Kivy video provider ---
os.environ['KIVY_VIDEO'] = 'ffpyplayer'

# --- THE DEFINITIVE FIX FOR THE 'register' ImportError ---
from kivy.core.text import LabelBase

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# Register the font file with a simple name
LabelBase.register(
    name='FontAwesome',
    fn_regular=resource_path('Font Awesome 7 Free-Solid-900.otf')
)
# --- END OF FONT FIX ---


from kivy.app import App
from kivy.uix.floatlayout import FloatLayout
from kivy.core.window import Window
from kivy.properties import ObjectProperty, StringProperty, BooleanProperty, ListProperty, NumericProperty
from kivy.clock import Clock
from kivy.animation import Animation
from kivy.logger import Logger
from plyer import filechooser
from kivy.uix.dropdown import DropDown
from kivy.uix.button import Button
from kivy.metrics import dp

Logger.setLevel('INFO')

class PlayerLayout(FloatLayout):
    # (The rest of the Python code remains exactly the same)
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
        super().__init__(**kwargs)
        Window.bind(on_drop_file=self._on_file_drop)
        Window.bind(on_key_down=self._on_key_down)
        Window.bind(mouse_pos=self.on_mouse_move)
        Clock.schedule_interval(self.update_ui, 1.0 / 30.0)

    def _on_file_drop(self, window, file_path_bytes: bytes, *args) -> None:
        try:
            self.load_file(file_path_bytes.decode('utf-8'))
        except Exception as e:
            self.display_error(f"Could not read dropped file: {e}")

    def _on_key_down(self, window, key: int, *args) -> None:
        if self.view_mode == 'player':
            if key == 32: self.toggle_play_pause()
            elif key == 276: self.seek_relative(-10)
            elif key == 275: self.seek_relative(10)
            elif key == 102: self.toggle_fullscreen()
            elif key == 109: self.toggle_mute()

    def load_file(self, file_path: str) -> None:
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
        self.error_message = message
        self.view_mode = 'welcome'
        self.video.source = ''

    def on_video_source_change(self, instance, new_source: str) -> None:
        if new_source:
            App.get_running_app().title = os.path.splitext(os.path.basename(new_source))[0]
            self._audio_tracks_populated = False
            self.show_controls()
        else:
            self.audio_tracks = []

    def populate_audio_tracks(self):
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
        if not self.audio_tracks: return
        if self.audio_dropdown: self.audio_dropdown.dismiss()
        
        self.audio_dropdown = DropDown()
        for i, track in enumerate(self.audio_tracks):
            track_name = f"{track['language'].upper()}: {track['title']}"
            btn = Button(text=track_name, size_hint_y=None, height=dp(44))
            btn.bind(on_release=lambda b, t=track['index']: self.set_audio_track(t))
            self.audio_dropdown.add_widget(btn)
        
        self.audio_dropdown.open(button)

    def set_audio_track(self, track_index):
        if hasattr(self.video, '_player') and self.video._player and track_index != -1:
            try:
                self.video._player.set_streams(-1, track_index)
                self.active_audio_track_index = track_index
                if self.audio_dropdown: self.audio_dropdown.dismiss()
            except Exception as e:
                Logger.error(f"Failed to set audio track to {track_index}: {e}")
    
    def on_video_state_change(self, instance, new_state: str) -> None:
        self.is_playing = (new_state == 'play')

    def open_file_dialog(self) -> None:
        was_playing = self.is_playing
        if was_playing: self.video.state = 'pause'

        def on_selection_thread_safe(selection):
            if selection:
                Clock.schedule_once(lambda dt: self.load_file(selection[0]))
            elif was_playing:
                Clock.schedule_once(lambda dt: setattr(self.video, 'state', 'play'))

        thread = threading.Thread(target=lambda: filechooser.open_file(on_selection=on_selection_thread_safe))
        thread.daemon = True
        thread.start()

    def toggle_play_pause(self) -> None:
        self.video.state = 'pause' if self.is_playing else 'play'

    def stop_playback(self) -> None:
        self.video.state = 'stop'
        self.video.source = ''
        self.view_mode = 'welcome'
        App.get_running_app().title = "KV Player"

    def on_video_eos(self, instance, value: bool) -> None:
        if value: self.stop_playback()

    def seek(self, normalized_value: float) -> None:
        if self.video.duration > 0: self.video.seek(normalized_value)

    def seek_relative(self, seconds: int) -> None:
        if self.video.duration > 0:
            self.video.seek((self.video.position + seconds) / self.video.duration)

    def format_time(self, seconds: float) -> str:
        if not isinstance(seconds, (int, float)) or seconds < 0: return "00:00"
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        return f"{int(h):02d}:{int(m):02d}:{int(s):02d}" if h > 0 else f"{int(m):02d}:{int(s):02d}"

    def update_ui(self, dt: float) -> None:
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
        self.is_muted = not self.is_muted
        if self.is_muted:
            self.volume_before_mute = self.video.volume
            self.video.volume = 0
        else:
            self.video.volume = getattr(self, 'volume_before_mute', 1.0)
        self.update_volume_icon(self.video.volume)

    def on_volume_change(self, value: float) -> None:
        self.video.volume = value
        self.is_muted = (value == 0)
        if not self.is_muted: self.volume_before_mute = value
        self.update_volume_icon(value)

    def update_volume_icon(self, volume: float) -> None:
        if self.is_muted or volume == 0: self.volume_icon = '\uf6a9'
        elif volume < 0.5: self.volume_icon = '\uf027'
        else: self.volume_icon = '\uf028'

    def toggle_fullscreen(self) -> None:
        self.is_fullscreen = not self.is_fullscreen
        Window.fullscreen = 'auto' if self.is_fullscreen else False

    def on_mouse_move(self, window, pos: tuple) -> None:
        if self.view_mode != 'player': return
        y_coord_normalized = pos[1] / self.height
        if y_coord_normalized < 0.15 or self.controls.collide_point(*pos):
            self.show_controls()
        else:
            if self.hide_controls_trigger is None:
                self.hide_controls_trigger = Clock.schedule_once(self.hide_controls, 3)

    def show_controls(self) -> None:
        Animation(y=0, d=0.2, t='out_quad').start(self.controls)
        if self.hide_controls_trigger:
            self.hide_controls_trigger.cancel()
            self.hide_controls_trigger = None

    def hide_controls(self, *args) -> None:
        Animation(y=-self.controls.height, d=0.2, t='in_quad').start(self.controls)
        self.hide_controls_trigger = None

class KVPlayerApp(App):
    def build(self):
        self.title = "KV Player"
        return PlayerLayout()

if __name__ == '__main__':
    KVPlayerApp().run()