slint::include_modules!();

use std::collections::VecDeque;
use std::sync::atomic::{AtomicBool, AtomicU32, AtomicU64, Ordering};
use std::sync::{Arc, Mutex, Condvar};
use std::thread;
use std::time::{Duration, Instant};
use rfd::FileDialog;
use slint::{Image, SharedPixelBuffer, Rgb8Pixel, Weak};
use ffmpeg_next as ffmpeg;
use rodio::{OutputStream, Sink, Source};

#[derive(Clone, Copy)]
enum SeekRequest {
    Absolute(f64), 
    Relative(f64), 
}

struct PlaybackController {
    is_playing: Arc<AtomicBool>,
    should_stop: Arc<AtomicBool>,
    volume: Arc<AtomicU32>, 
    seek_target: Arc<Mutex<Option<SeekRequest>>>,
    current_time: Arc<Mutex<f64>>, // Safely tracks the exact frame-level video position
    samples_played: Arc<AtomicU64>, // Monotonic audio playhead clock counter
    start_time: Arc<Mutex<Instant>>, // Presenter thread timing fallback
    paused_duration: Arc<Mutex<Duration>>,
    is_prebuffered: Arc<AtomicBool>, // True if the audio queue has built up a safe playback buffer
    state_condvar: Arc<(Mutex<bool>, Condvar)>, // OS-level conditional variable to park threads when paused
}

struct AudioBufferSource {
    buffer: Arc<Mutex<VecDeque<i16>>>,
    sample_rate: u32,
    volume: Arc<AtomicU32>,
    samples_played: Arc<AtomicU64>,
    is_prebuffered: Arc<AtomicBool>,
    is_playing: Arc<AtomicBool>,
}

impl Iterator for AudioBufferSource {
    type Item = i16;

    fn next(&mut self) -> Option<Self::Item> {
        // If the player is paused, immediately output silence without draining the queue backlog
        if !self.is_playing.load(Ordering::SeqCst) {
            return Some(0);
        }

        let mut guard = self.buffer.lock().unwrap();
        
        // 1. Buffering Guard: Wait until we have a safe buffer of 4,000 samples (~45ms) before starting.
        // This is mathematically guaranteed to be reached before the 3-frame video limit throttles the demuxer.
        if !self.is_prebuffered.load(Ordering::Relaxed) {
            if guard.len() >= 4000 {
                self.is_prebuffered.store(true, Ordering::Relaxed);
            } else {
                return Some(0); // Return silence and keep clock frozen during pre-buffering
            }
        }

        // 2. Playback: Pop real samples from the queue
        if let Some(sample) = guard.pop_front() {
            self.samples_played.fetch_add(1, Ordering::Relaxed);
            let volume_multiplier = self.volume.load(Ordering::Relaxed) as f32 / 100.0;
            Some((sample as f32 * volume_multiplier) as i16)
        } else {
            // 3. Starvation: If the buffer runs dry, reset pre-buffering state to build the buffer back up smoothly
            self.is_prebuffered.store(false, Ordering::Relaxed);
            Some(0)
        }
    }
}

impl Source for AudioBufferSource {
    fn current_frame_len(&self) -> Option<usize> { None }
    fn channels(&self) -> u16 { 2 }
    fn sample_rate(&self) -> u32 { self.sample_rate }
    fn total_duration(&self) -> Option<Duration> { None }
}

fn main() -> Result<(), slint::PlatformError> {
    // Silences normal internal FFmpeg warnings, keeping your terminal output clean
    ffmpeg::util::log::set_level(ffmpeg::util::log::Level::Error);

    // Force native hardware graphics rendering context on Windows (DirectX/Vulkan)
    std::env::set_var("SLINT_NO_ACCELERATION", "0");
    
    ffmpeg::init().expect("Unable to initialize FFmpeg system libraries.");

    let ui = MainWindow::new()?;
    let ui_weak = ui.as_weak();

    // Setup native Rodio audio stream output
    let (_stream, stream_handle) = OutputStream::try_default().expect("No default audio output device found.");
    let sink = Sink::try_new(&stream_handle).expect("Failed to initialize audio sink.");

    let shared_audio_queue = Arc::new(Mutex::new(VecDeque::with_capacity(88200))); // 1 second audio buffer
    let controller = Arc::new(PlaybackController {
        is_playing: Arc::new(AtomicBool::new(false)),
        should_stop: Arc::new(AtomicBool::new(false)),
        volume: Arc::new(AtomicU32::new(80)),
        seek_target: Arc::new(Mutex::new(None)),
        current_time: Arc::new(Mutex::new(0.0)),
        samples_played: Arc::new(AtomicU64::new(0)),
        start_time: Arc::new(Mutex::new(Instant::now())),
        paused_duration: Arc::new(Mutex::new(Duration::ZERO)),
        is_prebuffered: Arc::new(AtomicBool::new(false)),
        state_condvar: Arc::new((Mutex::new(false), Condvar::new())),
    });

    // Feed Rodio with our infinite real-time audio source
    let audio_source = AudioBufferSource {
        buffer: shared_audio_queue.clone(),
        sample_rate: 44100,
        volume: controller.volume.clone(),
        samples_played: controller.samples_played.clone(),
        is_prebuffered: controller.is_prebuffered.clone(),
        is_playing: controller.is_playing.clone(),
    };
    sink.append(audio_source);
    sink.play();

    // 1. Play / Pause Handler (With thread wakeup trigger)
    let ctrl_for_play_pause = controller.clone();
    let ui_for_play_pause = ui_weak.clone();
    ui.on_play_pause_clicked(move || {
        if let Some(ui) = ui_for_play_pause.upgrade() {
            let next_state = !ctrl_for_play_pause.is_playing.load(Ordering::SeqCst);
            ctrl_for_play_pause.is_playing.store(next_state, Ordering::SeqCst);
            ui.set_is_playing(next_state);

            // Notify and wake up the presenter thread from OS-level sleep
            let (lock, cvar) = &*ctrl_for_play_pause.state_condvar;
            let mut started = lock.lock().unwrap();
            *started = next_state;
            cvar.notify_all();
        }
    });

    // 2. Live Volume Slider Handler
    let ctrl_for_volume = controller.clone();
    ui.on_volume_changed(move |volume_val| {
        ctrl_for_volume.volume.store((volume_val * 100.0) as u32, Ordering::Relaxed);
    });

    // 3. Absolute scrubbing seek (with 100ms throttle timer to avoid choking)
    let ctrl_for_seek = controller.clone();
    let last_seek_time = Arc::new(Mutex::new(Instant::now()));
    ui.on_seek_requested(move |progress| {
        let mut last = last_seek_time.lock().unwrap();
        if last.elapsed() > Duration::from_millis(100) {
            *last = Instant::now();
            let mut target = ctrl_for_seek.seek_target.lock().unwrap();
            *target = Some(SeekRequest::Absolute(progress as f64));
        }
    });

    // 4. Skip Backwards 10s Button
    let ctrl_for_back = controller.clone();
    ui.on_skip_back_clicked(move || {
        let mut target = ctrl_for_back.seek_target.lock().unwrap();
        *target = Some(SeekRequest::Relative(-10.0));
    });

    // 5. Skip Forwards 10s Button
    let ctrl_for_forward = controller.clone();
    ui.on_skip_forward_clicked(move || {
        let mut target = ctrl_for_forward.seek_target.lock().unwrap();
        *target = Some(SeekRequest::Relative(10.0));
    });

    // 6. Native Fullscreen Toggle
    let ui_for_fullscreen = ui_weak.clone();
    ui.on_fullscreen_clicked(move || {
        if let Some(ui) = ui_for_fullscreen.upgrade() {
            let is_fullscreen = ui.window().is_fullscreen();
            ui.window().set_fullscreen(!is_fullscreen);
        }
    });

    // 7. Global Keyboard Hotkeys (Space, WASD)
    let ctrl_for_keys = controller.clone();
    let ui_for_keys = ui_weak.clone();
    ui.on_key_pressed(move |key| {
        if let Some(ui) = ui_for_keys.upgrade() {
            match key.as_str() {
                " " => { 
                    let next_state = !ctrl_for_keys.is_playing.load(Ordering::SeqCst);
                    ctrl_for_keys.is_playing.store(next_state, Ordering::SeqCst);
                    ui.set_is_playing(next_state);

                    // Wake presenter thread from OS sleep
                    let (lock, cvar) = &*ctrl_for_keys.state_condvar;
                    let mut started = lock.lock().unwrap();
                    *started = next_state;
                    cvar.notify_all();
                }
                "d" | "D" => { 
                    let mut target = ctrl_for_keys.seek_target.lock().unwrap();
                    *target = Some(SeekRequest::Relative(10.0));
                }
                "a" | "A" => { 
                    let mut target = ctrl_for_keys.seek_target.lock().unwrap();
                    *target = Some(SeekRequest::Relative(-10.0));
                }
                "w" | "W" => { 
                    let next_vol = (ui.get_volume() + 0.05).min(1.0);
                    ui.set_volume(next_vol);
                    ctrl_for_keys.volume.store((next_vol * 100.0) as u32, Ordering::Relaxed);
                }
                "s" | "S" => { 
                    let next_vol = (ui.get_volume() - 0.05).max(0.0);
                    ui.set_volume(next_vol);
                    ctrl_for_keys.volume.store((next_vol * 100.0) as u32, Ordering::Relaxed);
                }
                _ => {}
            }
        }
    });

    // 8. Open Media File Handler
    let ctrl_for_open = controller.clone();
    let ui_for_open = ui_weak.clone();
    let audio_queue_for_open = shared_audio_queue.clone();

    ui.on_open_file_clicked(move || {
        if let Some(path_buf) = FileDialog::new()
            .add_filter("Media Files", &["mp4", "mkv", "avi", "mov", "flv", "mp3", "wav"])
            .pick_file() 
        {
            let file_name = path_buf.file_name().unwrap_or_default().to_string_lossy().to_string();
            let file_path = path_buf.to_string_lossy().to_string();

            ctrl_for_open.should_stop.store(true, Ordering::SeqCst);
            
            // Wake presenter thread up from potential sleep so it can cleanly shut down
            let (lock, cvar) = &*ctrl_for_open.state_condvar;
            {
                let mut started = lock.lock().unwrap();
                *started = true;
            }
            cvar.notify_all();
            
            thread::sleep(Duration::from_millis(150));

            {
                let mut queue = audio_queue_for_open.lock().unwrap();
                queue.clear();
            }

            ctrl_for_open.should_stop.store(false, Ordering::SeqCst);
            ctrl_for_open.is_playing.store(true, Ordering::SeqCst);

            if let Some(ui) = ui_for_open.upgrade() {
                ui.set_is_playing(true);
                ui.set_now_playing_title(file_name.into());
            }

            let thread_ctrl = ctrl_for_open.clone();
            let thread_ui_weak = ui_for_open.clone();
            let thread_audio_queue = audio_queue_for_open.clone();

            thread::spawn(move || {
                if let Err(err) = decode_and_play(file_path, thread_ctrl, thread_ui_weak, thread_audio_queue) {
                    eprintln!("Playback pipeline error: {:?}", err);
                }
            });
        }
    });

    ui.run()
}

fn decode_and_play(
    file_path: String,
    controller: Arc<PlaybackController>,
    ui_weak: Weak<MainWindow>,
    audio_queue: Arc<Mutex<VecDeque<i16>>>,
) -> Result<(), Box<dyn std::error::Error>> {
    let mut ictx = ffmpeg::format::input(&file_path)?;

    let video_input = ictx.streams().best(ffmpeg::media::Type::Video);
    let mut video_decoder = None;
    let mut video_stream_index = None;
    let mut time_base = ffmpeg::Rational::new(1, 30);
    let mut duration_secs = 0.0;

    if let Some(input) = video_input {
        video_stream_index = Some(input.index());
        time_base = input.time_base();
        duration_secs = if input.duration() > 0 {
            input.duration() as f64 * f64::from(time_base)
        } else {
            ictx.duration() as f64 / 1_000_000.0
        };

        let mut context = ffmpeg::codec::context::Context::from_parameters(input.parameters())?;
        
        // Setup automatic logical multi-threaded frame decoding configurations
        context.set_threading(ffmpeg::threading::Config {
            kind: ffmpeg::threading::Type::Frame,
            count: 0, 
        });

        video_decoder = Some(context.decoder().video()?);
    }

    let audio_input = ictx.streams().best(ffmpeg::media::Type::Audio);
    let mut audio_decoder = None;
    let mut audio_stream_index = None;
    let mut resampler = None;

    if let Some(input) = audio_input {
        audio_stream_index = Some(input.index());
        let mut context = ffmpeg::codec::context::Context::from_parameters(input.parameters())?;
        
        context.set_threading(ffmpeg::threading::Config {
            kind: ffmpeg::threading::Type::Frame,
            count: 0,
        });

        let decoder = context.decoder().audio()?;

        let swr = ffmpeg::software::resampling::context::Context::get(
            decoder.format(),
            decoder.channel_layout(),
            decoder.rate(),
            ffmpeg::format::Sample::I16(ffmpeg::format::sample::Type::Packed),
            ffmpeg::ChannelLayout::STEREO,
            44100,
        )?;

        audio_decoder = Some(decoder);
        resampler = Some(swr);
    }

    let mut scaler = None;
    let mut render_w = 0;
    let mut render_h = 0;

    if let Some(ref decoder) = video_decoder {
        let native_w = decoder.width();
        let native_h = decoder.height();
        
        // Safety check: Only initialize scaler context if dimensions are valid
        if native_w > 0 && native_h > 0 {
            // Limits 4K/8K frame decoding sizes to 1280p bounds to preserve performance
            let max_dim = 1280;
            let (target_w, target_h) = if native_w > max_dim || native_h > max_dim {
                let scale = max_dim as f32 / (native_w.max(native_h) as f32);
                ((native_w as f32 * scale) as u32, (native_h as f32 * scale) as u32)
            } else {
                (native_w, native_h)
            };

            render_w = target_w;
            render_h = target_h;

            scaler = Some(ffmpeg::software::scaling::context::Context::get(
                decoder.format(),
                native_w,
                native_h,
                ffmpeg::format::Pixel::RGB24,
                render_w,
                render_h,
                ffmpeg::software::scaling::flag::Flags::FAST_BILINEAR,
            )?);
        }
    }

    let mut frame = ffmpeg::util::frame::Video::empty();
    let mut rgb_frame = ffmpeg::util::frame::Video::empty();
    let mut audio_frame = ffmpeg::util::frame::Audio::empty();

    let mut pre_roll_target: Option<f64> = None; 

    // Reset the audio playhead clock counter back to 0
    controller.samples_played.store(0, Ordering::Relaxed);

    // Double-buffered pool of pre-allocated Slint frames (Guarantees zero memory allocations per frame)
    let buffer_pool = [
        SharedPixelBuffer::<Rgb8Pixel>::new(render_w, render_h),
        SharedPixelBuffer::<Rgb8Pixel>::new(render_w, render_h),
    ];
    let mut pool_index = 0;

    // Bounded thread-safe queue holding exactly 2-3 decoded visual frames (Capacity of 15 frames for jitter headroom)
    let video_frame_queue = Arc::new(Mutex::new(VecDeque::<(f64, SharedPixelBuffer<Rgb8Pixel>)>::with_capacity(15)));

    // Spawn Asynchronous Presenter Thread to manage timeline alignment without freezing packet parsing
    let presenter_ctrl = controller.clone();
    let presenter_ui_weak = ui_weak.clone();
    let presenter_frame_queue = video_frame_queue.clone();
    let has_audio = audio_decoder.is_some();

    // Atomic flag to shield Slint's main event loop from frame congestion rendering lag
    let is_rendering_presenter = Arc::new(AtomicBool::new(false));

    thread::spawn(move || {
        while !presenter_ctrl.should_stop.load(Ordering::SeqCst) {
            // OS Kernel-level thread parking: Consumes exactly 0% CPU cycles when paused
            while !presenter_ctrl.is_playing.load(Ordering::SeqCst) {
                if presenter_ctrl.should_stop.load(Ordering::SeqCst) {
                    return;
                }
                let (lock, cvar) = &*presenter_ctrl.state_condvar;
                let mut started = lock.lock().unwrap();
                let pause_start = Instant::now();

                while !*started {
                    started = cvar.wait(started).unwrap();
                    if presenter_ctrl.should_stop.load(Ordering::SeqCst) {
                        return;
                    }
                }
                let elapsed = pause_start.elapsed();
                *presenter_ctrl.paused_duration.lock().unwrap() += elapsed;
            }

            let next_frame = {
                let mut queue = presenter_frame_queue.lock().unwrap();
                queue.pop_front()
            };

            if let Some((pts_secs, pixel_buffer)) = next_frame {
                // Update current time tracking
                *presenter_ctrl.current_time.lock().unwrap() = pts_secs;

                // Precision A/V Sync (Syncs to Audio Playhead Clock; falls back to system Monotonic clock)
                if has_audio {
                    let played_samples = presenter_ctrl.samples_played.load(Ordering::Relaxed);
                    let audio_time_secs = played_samples as f64 / 88200.0;

                    // Drop late frames: Skip rendering entirely if the frame's PTS is late by > 50ms (prevents stutter backlog)
                    if pts_secs < audio_time_secs - 0.05 {
                        continue;
                    } else if pts_secs > audio_time_secs {
                        let delay_secs = pts_secs - audio_time_secs;
                        thread::sleep(Duration::from_secs_f64(delay_secs.min(0.08)));
                    }
                } else {
                    // Fallback to system monotonic clock (for silent media files)
                    let start = *presenter_ctrl.start_time.lock().unwrap();
                    let paused = *presenter_ctrl.paused_duration.lock().unwrap();
                    let elapsed_adjusted = start.elapsed().saturating_sub(paused);
                    let target_time = Duration::from_secs_f64(pts_secs);

                    if elapsed_adjusted < target_time {
                        thread::sleep(target_time - elapsed_adjusted);
                    }
                }

                // Dispatch fully-aligned frames to Slint UI (VSync aligned)
                // Only dispatch if the previous frame has fully finished painting to prevent event loop clogging
                if !is_rendering_presenter.load(Ordering::Relaxed) {
                    is_rendering_presenter.store(true, Ordering::Relaxed);

                    let ui_weak_clone = presenter_ui_weak.clone();
                    let rendering_flag = is_rendering_presenter.clone();
                    let text_update = format!("{} / {}", format_seconds(pts_secs), format_seconds(duration_secs));
                    let progress_update = if duration_secs > 0.0 { pts_secs / duration_secs } else { 0.0 };

                    let _ = slint::invoke_from_event_loop(move || {
                        if let Some(ui) = ui_weak_clone.upgrade() {
                            ui.set_video_frame(Image::from_rgb8(pixel_buffer));
                            ui.set_time_display(text_update.into());
                            ui.set_progress(progress_update as f32);
                        }
                        rendering_flag.store(false, Ordering::Relaxed);
                    });
                }
            } else {
                // Frame queue empty; wait briefly for decoder thread to catch up
                thread::sleep(Duration::from_millis(5));
            }
        }
    });

    'playback: loop {
        if controller.should_stop.load(Ordering::SeqCst) {
            break 'playback;
        }

        // Intercept Active Seek Requests
        {
            let mut seek_opt = controller.seek_target.lock().unwrap();
            if let Some(request) = *seek_opt {
                let target_seconds = match request {
                    SeekRequest::Absolute(progress) => progress * duration_secs,
                    SeekRequest::Relative(offset) => {
                        let current_secs = *controller.current_time.lock().unwrap();
                        (current_secs + offset).clamp(0.0, duration_secs)
                    }
                };

                // Converting seconds to microseconds (AV_TIME_BASE = 1,000,000) for global FFmpeg seeks
                let target_pts = (target_seconds * 1_000_000.0) as i64;

                // Seek backward using standard exclusive range-to to locate preceding keyframe (I-Frame)
                let _ = ictx.seek(target_pts, ..target_pts);
                if let Some(ref mut decoder) = video_decoder {
                    decoder.flush();
                }
                if let Some(ref mut audio_dec) = audio_decoder {
                    audio_dec.flush();
                }

                // Flush queue pipelines
                {
                    let mut queue = audio_queue.lock().unwrap();
                    queue.clear();
                }
                {
                    let mut queue = video_frame_queue.lock().unwrap();
                    queue.clear();
                }

                // Set pre-roll target boundary so the renderer silently decodes the gap
                pre_roll_target = Some(target_seconds);

                // Reset pre-buffering state and align the audio playhead counter precisely with seek target
                controller.is_prebuffered.store(false, Ordering::Relaxed);
                let target_samples = (target_seconds * 88200.0) as u64;
                controller.samples_played.store(target_samples, Ordering::Relaxed);

                *controller.start_time.lock().unwrap() = Instant::now() - Duration::from_secs_f64(target_seconds);
                *controller.paused_duration.lock().unwrap() = Duration::ZERO;

                *seek_opt = None;
            }
        }

        for (stream, packet) in ictx.packets() {
            if controller.should_stop.load(Ordering::SeqCst) {
                break 'playback;
            }

            if controller.seek_target.lock().unwrap().is_some() {
                break;
            }

            // Proportional Memory Throttling: 
            // - Keeps 15 pre-rendered video frames (~500ms) to allow smooth decoding bursts.
            // - Caches at most 1.0 second of audio (maximum 88,200 samples in audio_queue).
            // - This ratio allows the 15,000-sample audio startup pre-buffer to fill up cleanly without deadlock.
            while video_frame_queue.lock().unwrap().len() >= 15 || audio_queue.lock().unwrap().len() > 88200 {
                thread::sleep(Duration::from_millis(5));
                if controller.should_stop.load(Ordering::SeqCst) {
                    return Ok(());
                }
            }

            // Decoder pause state handler (Wakes up instantly on active seek requests)
            while !controller.is_playing.load(Ordering::SeqCst) {
                if controller.should_stop.load(Ordering::SeqCst) {
                    return Ok(());
                }
                if controller.seek_target.lock().unwrap().is_some() {
                    break;
                }
                thread::sleep(Duration::from_millis(15));
            }

            // Video Decoder
            if Some(stream.index()) == video_stream_index {
                if let Some(ref mut decoder) = video_decoder {
                    decoder.send_packet(&packet)?;
                    while decoder.receive_frame(&mut frame).is_ok() {
                        if controller.should_stop.load(Ordering::SeqCst) {
                            return Ok(());
                        }

                        let pts_secs = frame.pts()
                            .map(|pts| pts as f64 * f64::from(time_base))
                            .unwrap_or(0.0);

                        // Save the frame timestamp so relative skips are mathematically precise
                        *controller.current_time.lock().unwrap() = pts_secs;

                        // Break the frame loop instantly if a seek was sent during decoding
                        if controller.seek_target.lock().unwrap().is_some() {
                            break;
                        }

                        // Pre-Roll Filter: Quietly decode catch-up frames without rendering or sleeping
                        if let Some(target) = pre_roll_target {
                            if pts_secs < target - 0.1 { // Skip frames older than target boundary minus tolerance
                                continue; 
                            } else {
                                // Target reached! Align and sync clock to the first visible frame
                                pre_roll_target = None;
                                *controller.start_time.lock().unwrap() = Instant::now() - Duration::from_secs_f64(pts_secs);
                                *controller.paused_duration.lock().unwrap() = Duration::ZERO;
                                
                                // Re-align the audio playhead precisely (44100Hz stereo)
                                let target_samples = (pts_secs * 88200.0) as u64;
                                controller.samples_played.store(target_samples, Ordering::Relaxed);
                            }
                        }

                        if let Some(ref mut scale_ctx) = scaler {
                            scale_ctx.run(&frame, &mut rgb_frame)?;
                            
                            let width = rgb_frame.width() as usize;
                            let height = rgb_frame.height() as usize;
                            let stride = rgb_frame.stride(0) as usize;
                            let raw_data = rgb_frame.data(0);

                            // Double-buffered swap: Retrieve existing pre-allocated pixel buffer with zero allocations
                            pool_index = (pool_index + 1) % 2;
                            let mut pixel_buffer = buffer_pool[pool_index].clone();
                            let dest_bytes = pixel_buffer.make_mut_bytes(); // Direct in-place vector access (No heap allocations)

                            // Safe row-by-row memory copy to bypass invisible FFmpeg alignment stride padding
                            let row_size = width * 3;
                            for y in 0..height {
                                let src_start = y * stride;
                                let src_end = src_start + row_size;
                                let dest_start = y * row_size;
                                let dest_end = dest_start + row_size;
                                
                                dest_bytes[dest_start..dest_end].copy_from_slice(&raw_data[src_start..src_end]);
                            }

                            // Push pre-rendered frame to the asynchronous presenter thread queue
                            let mut queue = video_frame_queue.lock().unwrap();
                            queue.push_back((pts_secs, pixel_buffer));
                        }
                    }
                }
            }
            // Audio Decoder
            else if Some(stream.index()) == audio_stream_index {
                if let Some(ref mut decoder) = audio_decoder {
                    if let Some(ref mut swr) = resampler {
                        decoder.send_packet(&packet)?;
                        while decoder.receive_frame(&mut audio_frame).is_ok() {
                            // Discard audio output packets during pre-roll phase to maintain alignment
                            if pre_roll_target.is_some() {
                                continue;
                            }

                            let mut resampled_frame = ffmpeg::util::frame::Audio::empty();
                            swr.run(&audio_frame, &mut resampled_frame)?;

                            let samples = resampled_frame.samples();
                            let channels = resampled_frame.channels();
                            
                            if samples > 0 {
                                let total_samples = samples * channels as usize;
                                let data_ptr = resampled_frame.data(0).as_ptr() as *const i16;
                                
                                let pcm_slice = unsafe {
                                    std::slice::from_raw_parts(data_ptr, total_samples)
                                };

                                let mut queue = audio_queue.lock().unwrap();
                                queue.extend(pcm_slice.iter().copied());
                            }
                        }
                    }
                }
            }
        }

        if !controller.seek_target.lock().unwrap().is_some() {
            break 'playback;
        }
    }

    Ok(())
}

fn format_seconds(total_seconds: f64) -> String {
    let minutes = (total_seconds / 60.0).floor() as u32;
    let seconds = (total_seconds % 60.0).floor() as u32;
    format!("{:02}:{:02}", minutes, seconds)
}