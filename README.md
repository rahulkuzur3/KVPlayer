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
```
2. Create a requirements.txt file:
Create a file named requirements.txt in your project folder with the following content:
```
kivy
ffpyplayer
plyer
pyinstaller
```
## 📦 Building an Executable
This project is configured for easy packaging into a single executable file using PyInstaller. The KVPlayer.spec file is universal for Windows, macOS, and Linux.
You must run the build command on the target operating system.
Prerequisites:
 * Make sure you have an icon file in your project directory (icon.ico for Windows, icon.icns for macOS).
 * Ensure all dependencies from requirements.txt are installed.
Build Command:
Open a terminal in the project directory and run:
```
pyinstaller KVPlayer.spec
```
## The final, self-contained application will be located in the dist folder:
 * Windows: dist/KVPlayer.exe
 * macOS: dist/KVPlayer.app
 * Linux: dist/KVPlayer
## 🛠️ Main Dependencies
Kivy: For the cross-platform graphical user interface.
FFpyplayer: A Kivy-compatible video/audio player backend using the powerful FFmpeg library.
Plyer: For accessing native platform features like the file selection dialog.
PyInstaller: For packaging the application into a standalone executable.
Font Awesome: For the modern icons used in the UI.

## 📜 License
This project is licensed under the MIT License - see the LICENSE.md file for details.
