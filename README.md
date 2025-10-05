# KV Player

[![Python Version](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Platform](https://img.shields.io/badge/platform-windows%20%7C%20macos%20%7C%20linux-lightgrey.svg)]()

A modern, high-performance, cross-platform media player built with Python and the Kivy framework. It leverages the robust FFpyplayer backend to deliver smooth playback and fast seeking without external dependency headaches.

![KV Player Screenshot](screenshot.png)
*(Replace `screenshot.png` with a real screenshot of your application)*

---

## ✨ Key Features

*   **Sleek, Minimalist Interface:** A modern, dark-themed UI that gets out of your way. Controls are auto-hiding and appear only when needed.
*   **High-Performance Playback:** Utilizes **FFmpeg** via FFpyplayer with hardware acceleration (`hw_accel`) and fast seeking (`fastseek`) enabled for smooth playback and instantaneous skipping.
*   **Truly Cross-Platform:** Runs natively on Windows, macOS, and Linux from a single codebase.
*   **Multi-Audio Track Support:** Automatically detects and allows you to switch between multiple audio tracks in your video files (e.g., different languages, commentaries).
*   **Full Playback Control:**
    *   Play / Pause
    *   Responsive Seek Bar
    *   10-Second Skip Forward/Backward
    *   Volume Control Slider & Mute
    *   Fullscreen Mode
*   **Versatile File Handling:**
    *   Drag-and-drop files directly onto the player.
    *   "Open File" dialog available on both the welcome screen and during playback.
*   **Standalone Executable:** Comes with a pre-configured `KVPlayer.spec` file to easily package the application into a single executable for all platforms using PyInstaller.

## 🚀 Getting Started (Running from Source)

To run the player from the source code, you'll need Python 3.9+ and the required packages.

**1. Clone the repository:**
```bash
git clone https://github.com/your-username/your-repo-name.git
cd your-repo-name
