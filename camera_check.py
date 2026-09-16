#!/usr/bin/env python3
"""
COSC 3P71 - Lab 1: TurboPi camera check.

This program runs on the LAB COMPUTER, not on the robot. It connects to the
robot over Wi-Fi and shows the robot's live camera feed in a window, so you
can confirm you are talking to YOUR robot: wave at the camera and you should
see yourself.

It opens two connections, both to the robot's IP address:

    port 9090  - rosbridge (a websocket). Later labs will send driving
                 commands through this. Today it only proves the port answers.
    port 8080  - web_video_server. Streams the camera topic as MJPEG
                 (a never-ending series of JPEG images over HTTP).

Requires:   pip install websocket-client Pillow
Run:        python camera_check.py
"""

import io
import sys
import time
import threading
import tkinter as tk
import urllib.request

try:
    from PIL import Image, ImageTk
except ImportError:
    sys.exit("Pillow is not installed. Run:  pip install Pillow")

try:
    import websocket                      # from the websocket-client package
    WS_AVAILABLE = True
except ImportError:
    WS_AVAILABLE = False

# -- Robot settings ----------------------------------------------------------
# These are the only lines you should need to change.
ROBOT_IP       = "192.168.149.1"   # from ipconfig -> Default Gateway (Part C)
ROSBRIDGE_PORT = 9090
WEB_VIDEO_PORT = 8080
CAMERA_TOPIC   = "/image_raw"      # the topic the TurboPi camera publishes on

VIDEO_W, VIDEO_H = 640, 480        # size of the video panel in the window
DISPLAY_PERIOD_MS = 33             # redraw the video ~30 times per second
STATUS_PERIOD_MS  = 250            # refresh the status lines 4 times per second
# ----------------------------------------------------------------------------

STREAM_URL = (f"http://{ROBOT_IP}:{WEB_VIDEO_PORT}/stream"
              f"?topic={CAMERA_TOPIC}&type=mjpeg&quality=70")


class RosbridgeClient:
    """A minimal connection to the robot's rosbridge websocket.

    rosbridge lets a program that is NOT running ROS (like this one, on a
    Windows lab computer) talk to ROS topics on the robot by sending small
    JSON messages over a websocket. In later labs you will add methods here
    that publish to /cmd_vel to drive the robot. For now, connecting is all
    we need: if it succeeds, port 9090 on the robot is alive.
    """

    def __init__(self, ip, port):
        self.url = f"ws://{ip}:{port}"
        self.ws = None
        self.connected = False
        self.error = ""

    def connect(self):
        if not WS_AVAILABLE:
            self.error = "websocket-client not installed"
            return
        try:
            self.ws = websocket.WebSocket()
            self.ws.connect(self.url, timeout=5)
            self.connected = True
        except Exception as e:
            self.connected = False
            self.error = str(e)

    def close(self):
        self.connected = False
        if self.ws is not None:
            try:
                self.ws.close()
            except Exception:
                pass


class MjpegCamera(threading.Thread):
    """Reads the camera's MJPEG stream in the background.

    web_video_server sends one JPEG after another down a single HTTP
    connection. Every JPEG begins with the two bytes FF D8 and ends with
    FF D9, so we collect bytes into a buffer and cut out each complete
    image as it arrives. The newest decoded frame is kept in `self.frame`;
    the window picks it up from there. (The GUI must only be touched from
    the main thread, which is why this thread never draws anything itself.)
    """

    def __init__(self, url):
        super().__init__(daemon=True)   # daemon: dies with the main program
        self.url = url
        self.running = True
        self.frame = None               # newest frame as a PIL image
        self.frame_count = 0
        self.last_frame_time = 0.0
        self.error = ""

    def run(self):
        while self.running:
            try:
                stream = urllib.request.urlopen(self.url, timeout=5)
                self.error = ""
                buf = b""
                while self.running:
                    chunk = stream.read(8192)
                    if not chunk:
                        raise ConnectionError("stream ended")
                    buf += chunk
                    buf = self._extract_frames(buf)
            except Exception as e:
                self.error = str(e)
                time.sleep(2)           # wait, then try to reconnect

    def _extract_frames(self, buf):
        """Pull every complete JPEG out of `buf`; return the leftover bytes."""
        while True:
            start = buf.find(b"\xff\xd8")
            if start == -1:
                return buf[-1:]         # no image started yet; keep a stray FF
            end = buf.find(b"\xff\xd9", start + 2)
            if end == -1:
                return buf[start:]      # image not finished; wait for more
            jpg, buf = buf[start:end + 2], buf[end + 2:]
            try:
                img = Image.open(io.BytesIO(jpg))
                img.load()              # decode now, so errors surface here
            except Exception:
                continue                # a damaged frame; skip it
            self.frame = img
            self.frame_count += 1
            self.last_frame_time = time.time()


class CameraCheckApp:
    """The window: two status lines, the video, and a hint."""

    def __init__(self, root):
        self.root = root
        root.title(f"TurboPi Camera Check - {ROBOT_IP}")
        root.resizable(False, False)

        # --- status lines ---
        self.rosbridge_lbl = tk.Label(root, anchor="w", font=("TkDefaultFont", 10))
        self.rosbridge_lbl.pack(fill=tk.X, padx=10, pady=(8, 0))
        self.camera_lbl = tk.Label(root, anchor="w", font=("TkDefaultFont", 10))
        self.camera_lbl.pack(fill=tk.X, padx=10)

        # --- video panel (fixed size, so the window has a shape before the
        #     first frame arrives; label sizes are in characters, not pixels)
        holder = tk.Frame(root, width=VIDEO_W, height=VIDEO_H, bg="black")
        holder.pack_propagate(False)
        holder.pack(padx=10, pady=8)
        self.video_lbl = tk.Label(holder, text="Waiting for video...",
                                  bg="black", fg="white")
        self.video_lbl.pack(fill=tk.BOTH, expand=True)
        self.photo = None       # keep a reference or tkinter drops the image
        self.shown_count = 0    # frame_count of the frame currently displayed

        tk.Label(root, text="Wave at the robot's camera. If you see yourself, "
                            "this is your robot.",
                 fg="gray30").pack(pady=(0, 8))

        # --- start the two connections ---
        self.rosbridge = RosbridgeClient(ROBOT_IP, ROSBRIDGE_PORT)
        threading.Thread(target=self.rosbridge.connect, daemon=True).start()
        self.camera = MjpegCamera(STREAM_URL)
        self.camera.start()

        # for the frames-per-second readout
        self.fps = 0.0
        self._fps_count = 0
        self._fps_time = time.time()

        self.update_video()
        self.update_status()
        root.protocol("WM_DELETE_WINDOW", self.quit)

    def update_video(self):
        """Show the newest camera frame. Runs in the GUI thread."""
        if self.camera.frame_count != self.shown_count:
            self.shown_count = self.camera.frame_count
            img = self.camera.frame.copy()
            img.thumbnail((VIDEO_W, VIDEO_H))          # fit, keep aspect ratio
            self.photo = ImageTk.PhotoImage(img)
            self.video_lbl.config(image=self.photo, text="")
        self.root.after(DISPLAY_PERIOD_MS, self.update_video)

    def update_status(self):
        # rosbridge line
        if self.rosbridge.connected:
            self._set(self.rosbridge_lbl, "green4",
                      f"rosbridge  (port {ROSBRIDGE_PORT}):  connected")
        elif self.rosbridge.error:
            self._set(self.rosbridge_lbl, "red",
                      f"rosbridge  (port {ROSBRIDGE_PORT}):  FAILED - {self.rosbridge.error}")
        else:
            self._set(self.rosbridge_lbl, "dark orange",
                      f"rosbridge  (port {ROSBRIDGE_PORT}):  connecting...")

        # camera line
        now = time.time()
        if now - self._fps_time >= 1.0:
            self.fps = (self.camera.frame_count - self._fps_count) / (now - self._fps_time)
            self._fps_count = self.camera.frame_count
            self._fps_time = now

        if now - self.camera.last_frame_time < 2.0:
            self._set(self.camera_lbl, "green4",
                      f"camera     (port {WEB_VIDEO_PORT}):  streaming {CAMERA_TOPIC}"
                      f"  at {self.fps:.0f} fps")
        elif self.camera.error:
            self._set(self.camera_lbl, "red",
                      f"camera     (port {WEB_VIDEO_PORT}):  FAILED - {self.camera.error}")
        else:
            self._set(self.camera_lbl, "dark orange",
                      f"camera     (port {WEB_VIDEO_PORT}):  waiting for first frame...")

        self.root.after(STATUS_PERIOD_MS, self.update_status)

    @staticmethod
    def _set(label, colour, text):
        label.config(text=text, fg=colour)

    def quit(self):
        self.camera.running = False
        self.rosbridge.close()
        self.root.destroy()


def main():
    if not WS_AVAILABLE:
        print("websocket-client is not installed (run: pip install websocket-client).")
        print("Continuing with the camera only; the rosbridge line will show an error.\n")
    print(f"Robot:  {ROBOT_IP}")
    print(f"Video:  {STREAM_URL}")
    root = tk.Tk()
    CameraCheckApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
