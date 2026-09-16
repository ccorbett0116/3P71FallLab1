# COSC 3P71 — Lab 1: Getting Connected to Your TurboPi

**Duration:** two lab sessions (about 4 hours)
**Prerequisites:** None

---

## Overview

Your TurboPi robot is a small computer (a Raspberry Pi) on wheels. It has no keyboard or monitor of its own, so everything you do with it this term — running programs, reading sensors, driving it — happens from the lab computer over Wi-Fi. All the code you write in this course runs on the lab computer and talks to the robot over the network. This lab gets that connection working.

By the end of this lab you will have:

- Installed the TigerVNC viewer and the Python packages the course uses
- Powered on the robot and joined the Wi-Fi network it broadcasts
- Found the robot's IP address
- Connected to the robot over **SSH** (a terminal) and **VNC** (its desktop)
- Run a Python program on the lab computer that shows the robot's live camera feed — and used it to confirm the robot you are connected to is *yours*
- Given your robot's Wi-Fi network a unique name
- Completed a **teleoperation** program: a GUI joystick on the lab computer that drives the robot over the network, including sideways (strafing) motion — the TurboPi's **holonomic** mecanum drive
- Extended it to aim the camera's pan/tilt servos and to show a live reading from the ultrasonic distance sensor

### How the two sessions divide

| Session | Parts | What you will have at the end |
|---------|-------|-------------------------------|
| **1** | A – G | Lab computer set up; robot reachable by SSH and VNC; you have been inside the robot's software container; the camera check proves which robot is yours; your robot's network has its own name |
| **2** | H – J | The teleop program complete: driving, camera aiming, and a live sonar readout |

Session 1 is many short steps, most of which only have to be done once; Session 2 is the programming. If you finish Session 1 early, start Part H — the background reading is worth doing without a robot in front of you.

**Between sessions, read "Ending a Session" below.** In particular: the lab computers may not keep your files, and you may not get the same computer next time.

---

## What You Need

- Your TurboPi robot, charged and switched off
- A Windows lab computer with Wi-Fi (built-in or a USB Wi-Fi dongle) and Python 3 installed
- Internet access for the downloads in Part A. **Do Part A first:** while the computer is connected to the robot's Wi-Fi it has no internet.
- The two Python files provided with this lab:

| File | Purpose |
|------|---------|
| `camera_check.py` | Part F — shows the robot's live camera feed; complete, nothing to edit |
| `teleop_scaffold.py` | Parts H, I and J — the teleoperation program; you complete seven marked `TODO`s in three stages |

---

## Reference: The Robot Documentation

The manufacturer, Hiwonder, publishes documentation for the TurboPi here:

**https://docs.hiwonder.com/projects/TurboPi/en/advanced/**

Bookmark it. If something in this lab does not behave the way the manual says, the Hiwonder docs are the first place to look. The sections most relevant to today are:

| Section | Covers |
|---------|--------|
| 1.7 — Remote Desktop Installation and Connection | Connecting to the robot's desktop over Wi-Fi |
| 7.1 — Changing Wi-Fi Name and Password | Renaming the robot's hotspot |
| 7.2 — Modify Network Connection Mode | Hotspot mode vs. joining an existing network |

> **Note:** Hiwonder's guide uses RealVNC's "VNC Viewer". In this course we use **TigerVNC** instead. The steps are the same — type the robot's IP address, enter the password — only the program looks slightly different.

---

## Background: How the Robot's Software Works

Read this once now; come back to it whenever a command in this manual looks mysterious. There are three layers, and knowing which one you are in explains almost every confusing moment in this course.

```text
┌───────────────────────────────────────────────────────────────┐
│  LAB COMPUTER (Windows)                                       │
│  your Python programs: camera_check.py, teleop_scaffold.py    │
└──────────────────────────────┬────────────────────────────────┘
                               │  Wi-Fi: the robot's own hotspot
┌──────────────────────────────▼────────────────────────────────┐
│  RASPBERRY PI inside the robot — Raspberry Pi OS (Linux)      │
│  where SSH and VNC land, as user  pi                          │
│                                                               │
│   ┌───────────────────────────────────────────────────────┐   │
│   │  DOCKER CONTAINER  "turbopi" — Ubuntu Linux           │   │
│   │  ROS 2 Humble and all of the robot's software:        │   │
│   │    camera driver · motor controller · sonar driver    │   │
│   │    rosbridge (port 9090) · web_video_server (8080)    │   │
│   │  user inside:  ubuntu                                 │   │
│   └───────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────┘
```

### Layer 1 — the Raspberry Pi

The robot's brain is a Raspberry Pi, a small Linux computer, running **Raspberry Pi OS** (a version of Debian). When you SSH or VNC into the robot, this is where you arrive, logged in as the user `pi`. It has a desktop, a home folder, and the usual Linux commands.

### Layer 2 — the Docker container

The robot's actual software does **not** run directly on Raspberry Pi OS. It runs inside a **Docker container** named `turbopi`.

**What Docker is.** Docker packages a complete Linux environment — a filesystem, an operating system's worth of installed programs and libraries, configuration, everything — into a single **image**, and can run that image as an isolated **container** on any computer. Think of a container as a sealed box with its own Linux inside it, running as a program on the host. Whatever is installed inside the box is not installed outside it, and vice versa.

**Why Hiwonder does this.** ROS 2 Humble is built for Ubuntu 22.04; the Raspberry Pi runs Debian. Rather than fight that mismatch on every robot, Hiwonder ships one Ubuntu image with ROS 2 and all the robot software pre-installed and tested. Every robot runs the identical image, so every robot behaves identically, and reinstalling a broken robot means re-loading the image. This is exactly why Docker is everywhere in industry: *it works on my machine* becomes *it works in the container, and the container is the same everywhere.*

**What this means for you.** Four things you will run into:

1. **The container has its own files, programs and users.** From the `pi` login, `ros2` is not a command and the robot's software is nowhere to be found. To use any ROS tool you must step *inside* the container with `docker exec`.
2. **Inside, you are a different user.** The container's user is `ubuntu`, not `pi`. The prompt tells you where you are: `pi@raspberrypi:~ $` means outside, `ubuntu@raspberrypi:~$` means inside.
3. **It starts itself.** The container and the robot's software start automatically at boot. You never start, stop, or install anything in it.
4. **Its network is the robot's network.** The container shares the Raspberry Pi's network address, so a program on the lab computer connecting to port 8080 or 9090 at `192.168.149.1` reaches straight into the container. That is why your own programs never need to know Docker exists.

**The Docker commands you will use.** There are only three:

| Command | What it does |
|---------|--------------|
| `docker ps` | List the containers that are running. You should see one, named `turbopi`. |
| `docker exec -it --user ubuntu turbopi bash` | Open a shell **inside** the container. Your prompt changes to `ubuntu@…`. |
| `exit` | Leave the container shell and return to `pi`. |

The middle one looks long, so here it is piece by piece:

| Piece | Meaning |
|-------|---------|
| `docker exec` | Run a command inside a running container |
| `-it` | *Interactive* with a *terminal* — needed whenever you want to type at the thing you are running. Leave it out and your keystrokes never arrive. |
| `--user ubuntu` | Run as the container's `ubuntu` user, who owns the ROS installation |
| `turbopi` | The name of the container to run in |
| `bash` | The command to run inside: a shell |

Replace `bash` with any other command to run just that one thing inside the container and come straight back out.

**The two `source` lines.** One more rule that applies inside the container: ROS 2 must be loaded into your shell before any `ros2` command works. Every time you open a container shell, first run:

```bash
source /opt/ros/humble/setup.bash
source /home/ubuntu/ros2_ws/install/setup.bash
```

`source` runs a script *in your current shell* so that the variables it sets (where programs are, where Python libraries are) stick. The first line loads core ROS 2; the second loads the robot-specific packages — the motor controller, the servo message types, and so on. Forgetting these is the single most common error in this course: if `ros2` says *command not found* inside the container, this is why.

### Layer 3 — ROS 2

Inside the container runs **ROS 2** (Robot Operating System), the framework the robot's software is built on. Its central idea is the **topic**: a named channel that programs publish messages to, or subscribe to receive messages from. The camera driver publishes pictures on `/image_raw`; the motor controller subscribes to `/cmd_vel` and drives the wheels according to whatever it receives; the sonar driver publishes distances on `/sonar_controller/get_distance`. Programs that publish and subscribe are called **nodes**.

Your programs on the lab computer become participants in this through **rosbridge**, a node inside the container that accepts topic messages as JSON over a network socket. Parts F and H explain exactly how.

---

## Part A: Set Up the Lab Computer (while you still have internet)

Everything in this part needs internet access, and you will lose internet the moment you connect to the robot. Do all three steps before touching the robot.

**VNC** (Virtual Network Computing) lets you see and control the robot's desktop in a window on your laptop, as if you had a monitor and mouse plugged into it. You need a VNC *viewer* program on your laptop to do this.

### Step 1 — Download the viewer

Go to:

**https://sourceforge.net/projects/tigervnc/files/stable/1.16.2/**

The page lists many files. Download exactly this one:

```
vncviewer64-1.16.2.exe
```

It is about 24 MB. Save it somewhere you can find again, such as your Desktop.

> **Do not** download `tigervnc64-1.16.2.exe`. That is the full installer including a VNC *server*, which you do not need. You only need the viewer.

### Step 2 — Run it

`vncviewer64-1.16.2.exe` is a standalone program — there is no installer. Double-click the file to run it.

Windows may show a **"Windows protected your PC"** warning the first time. Click **More info**, then **Run anyway**.

A small window titled **VNC Viewer: Connection Details** appears with a **VNC server:** text field. That is the whole program. You can close it for now; you will come back to it in Part E.

> **macOS / Linux:** the same page has `TigerVNC-1.16.2.dmg` for macOS. Most Linux distributions ship TigerVNC in their package manager (`tigervnc-viewer`).

### Step 3 — Install the Python packages

Part F runs a Python program that talks to the robot. It needs two packages. Open Command Prompt (**Win + R**, type `cmd`, **Enter**) and run:

```cmd
pip install websocket-client Pillow
```

| Package | What it is for |
|---------|----------------|
| `websocket-client` | Talking to **rosbridge** on the robot (port 9090) — how we will send commands in later labs |
| `Pillow` | Decoding the JPEG images that make up the camera stream |

Then check Python itself works:

```cmd
python --version
```

It should print `Python 3.x.x`. If it says `'python' is not recognized`, try `py --version` instead and use `py` wherever this manual says `python`.

Finally, save `camera_check.py` and `teleop_scaffold.py` (provided with this lab) somewhere you can find them, for example a folder `lab1` on your Desktop.

---

## Part B: Power On the Robot and Join Its Wi-Fi

### Step 1 — Power on

Place the robot on the floor or a clear desk and switch it on. The Raspberry Pi takes roughly **30–60 seconds** to boot. Wait for it.

### Step 2 — Find the robot's Wi-Fi network

When the robot has booted, it broadcasts its own Wi-Fi hotspot (this is called **AP mode** — the robot acts as its own access point). On your laptop, open the Wi-Fi list and look for a network whose name begins with **`HW`**.

Connect to it. The password is:

```
hiwonder
```

> **First lab only:** every robot ships with the same generic hotspot name, so with a room full of robots you will see several near-identical networks. Your lab demonstrator will tell you how to identify yours. Later in this lab (Part G) you will **rename** your robot's network so it is unmistakably yours — follow the demonstrator's instructions for the naming convention.

> **You lose internet while connected to the robot.** The robot's hotspot is not connected to anything else. This is normal. Make sure Part A is done before you connect.

Once connected, Windows may label the network "No internet" — ignore that; it is expected.

---

## Part C: Find the Robot's IP Address

To connect over SSH or VNC you need the robot's **IP address** — its address on the little Wi-Fi network it just created. Your laptop already knows it, because the robot is acting as the *router* for that network.

### Step 1 — Open Command Prompt

Press **Win + R**, type `cmd`, and press **Enter**.

### Step 2 — Run `ipconfig`

```cmd
ipconfig
```

This prints one block per network adapter on your laptop. Find the block for your wireless adapter. It is usually headed **Wireless LAN adapter Wi-Fi** (if you are using a USB Wi-Fi dongle it may have a different name, but it will still say *Wireless*). It looks like this:

```
Wireless LAN adapter Wi-Fi:

   Connection-specific DNS Suffix  . :
   Link-local IPv6 Address . . . . . : fe80::a1b2:c3d4:e5f6:7890%12
   IPv4 Address. . . . . . . . . . . : 192.168.149.23
   Subnet Mask . . . . . . . . . . . : 255.255.255.0
   Default Gateway . . . . . . . . . : 192.168.149.1
```

### Step 3 — Read the Default Gateway

The line you want is **Default Gateway**. That is the address of the device your wireless adapter is connected *to* — the robot.

| Line | What it is |
|------|-----------|
| `IPv4 Address` | Your **laptop's** address on the robot's network. Not what you want. |
| `Default Gateway` | The **robot's** address. This is what you type into SSH and VNC. |

On a TurboPi in hotspot mode this is normally **`192.168.149.1`**, but always check `ipconfig` rather than assuming. Write the address down; you will use it for the rest of the lab.

> **macOS / Linux:** run `ipconfig getifaddr en0` / `ip route` and read the gateway, or just try `192.168.149.1`.

> **If `Default Gateway` is blank, or `IPv4 Address` starts with `169.254`:** your laptop did not get an address from the robot. Disconnect from the robot's Wi-Fi, wait a few seconds, reconnect, and run `ipconfig` again.

---

## Part D: Connect over SSH

**SSH** (Secure Shell) gives you a *terminal* on the robot: you type commands on your laptop and they run on the robot. This is how you will run most of your code this term, so make sure it works.

Windows 10 and 11 include an SSH client, so you can use it straight from Command Prompt.

### Step 1 — Connect

In the same Command Prompt, run (replace the address with the one from Part C if it differs):

```cmd
ssh pi@192.168.149.1
```

| Part | Meaning |
|------|---------|
| `ssh` | The SSH client program |
| `pi` | The username to log in as on the robot |
| `192.168.149.1` | The robot's IP address |

### Step 2 — Accept the robot's host key

The **first** time you connect to a robot, SSH has never seen it before and asks you to confirm:

```
The authenticity of host '192.168.149.1 (192.168.149.1)' can't be established.
ED25519 key fingerprint is SHA256:....
Are you sure you want to continue connecting (yes/no/[fingerprint])?
```

Type `yes` and press **Enter**. You will not be asked again for this robot.

### Step 3 — Enter the password

```
pi@192.168.149.1's password:
```

Type:

```
raspberrypi
```

**Nothing appears on screen while you type the password** — no dots, no asterisks. That is normal. Type it and press **Enter**.

### Step 4 — You're in

You should see a prompt like:

```
pi@raspberrypi:~ $
```

Everything you type here now runs **on the robot**, not on your laptop. Try a couple of commands to prove it:

```bash
hostname
uptime
ls
```

`hostname` should print `raspberrypi`.

### Step 5 — Step inside the robot's software container

You are logged in to the Raspberry Pi — but as the Background section explained, the robot's software lives one layer down, inside the Docker container. See for yourself. Still at the `pi@raspberrypi` prompt, try:

```bash
ros2
```

```text
-bash: ros2: command not found
```

Nothing. ROS is not installed *here*. Now look at what containers are running:

```bash
docker ps
```

```text
CONTAINER ID   IMAGE         COMMAND               CREATED        STATUS         PORTS     NAMES
13d7631b7087   turbopi:new   "tail -f /dev/null"   6 months ago   Up 7 minutes             turbopi
```

One container, named `turbopi`, `Up` since the robot booted. Step inside it:

```bash
docker exec -it --user ubuntu turbopi bash
```

Your prompt changes to `ubuntu@raspberrypi:~$` — different user, different Linux. Load ROS 2 into this shell (the two lines from the Background section):

```bash
source /opt/ros/humble/setup.bash
source /home/ubuntu/ros2_ws/install/setup.bash
```

Now ROS exists. List the topics the robot's software is publishing and subscribing to:

```bash
ros2 topic list
```

You will see about 35 names. Three of them are the whole of this lab:

```text
/cmd_vel
/image_raw
/sonar_controller/get_distance
```

Watch one live — this prints every distance reading the sonar publishes, in millimetres:

```bash
ros2 topic echo /sonar_controller/get_distance
```

Put your hand in front of the sensor on the front of the robot and watch the number fall. Press **Ctrl+C** to stop.

Two useful relatives of these commands, for later:

```bash
ros2 topic info /cmd_vel                        # what message type a topic carries, and who is listening
ros2 interface show geometry_msgs/msg/Twist     # the definition of a message type
```

Now leave. `exit` once takes you out of the container (prompt back to `pi@raspberrypi`); `exit` again closes SSH and returns you to your laptop's prompt.

```bash
exit
exit
```

> **Which layer am I in?** Look at the prompt. `pi@raspberrypi` — on the Pi, outside the container. `ubuntu@raspberrypi` — inside the container. `C:\Users\…>` — your own laptop. Most "command not found" moments in this course are a command typed in the wrong layer.

> **If Windows says `'ssh' is not recognized`:** your laptop is missing the OpenSSH client. Open **Settings → Apps → Optional features**, click **Add a feature**, and install **OpenSSH Client**. Alternatively, install PuTTY (https://www.putty.org/) and enter the robot's IP as the Host Name, port 22, connection type SSH.

---

## Part E: Connect over VNC

Now the desktop. Where SSH gives you a terminal, VNC gives you the robot's full graphical desktop in a window.

### Step 1 — Open the viewer

Double-click `vncviewer64-1.16.2.exe` (from Part A).

### Step 2 — Enter the robot's address

In the **VNC server:** field, type the robot's IP address:

```
192.168.149.1
```

Click **Connect**.

### Step 3 — Enter the password

A **VNC authentication** dialog asks for a password. Enter:

```
raspberrypi
```

### Step 4 — You should see the robot's desktop

A window opens showing the Raspberry Pi desktop. You can move the mouse and click inside it exactly as if a monitor were plugged into the robot.

To convince yourself it is the same machine you reached over SSH, right-click on the desktop and choose **Open Terminal** (or click the terminal icon in the taskbar), then run:

```bash
hostname
```

It prints `raspberrypi`, the same answer SSH gave you.

You can leave the VNC window open. Closing it disconnects the viewer but does nothing to the robot.

---

## Part F: See Through the Robot's Camera

SSH and VNC prove you can log in to *a* robot. They do not prove it is *your* robot: every TurboPi has the same address (`192.168.149.1`) and the same login, so if you joined the wrong `HW…` network in Part B, everything so far would have worked exactly the same way on someone else's robot. The camera settles it. In this part you run a small Python program on the lab computer that connects to the robot over Wi-Fi and shows its live camera feed.

### How the lab computer talks to the robot

Recall the three layers from the Background section. The robot's software runs on **ROS 2** inside the `turbopi` container, exchanging data on named **topics** — you listed them in Part D, Step 5: the camera driver publishes a stream of images on `/image_raw`, the motor controller listens on `/cmd_vel`, and so on. A program on your laptop cannot join ROS directly, but two small bridge nodes inside the container expose it over ordinary network connections, on the robot's own address:

| Service | Port | What it does | Used today for |
|---------|------|--------------|----------------|
| **rosbridge** | 9090 | A websocket that accepts small JSON messages and turns them into ROS publishes and subscribes | A connection check (in later labs: driving the robot) |
| **web_video_server** | 8080 | Serves any image topic as an **MJPEG** stream over HTTP — a never-ending series of JPEG pictures that even a web browser can show | The camera feed |

Both are plain network sockets to the robot's IP address. That is why everything you write this term runs on the lab computer in ordinary Python, with no ROS installation of your own.

### Step 1 — Check the stream in a browser

Before running any code, prove the robot side is working. With the computer on the robot's Wi-Fi, open this address in your web browser:

```
http://192.168.149.1:8080/
```

web_video_server shows a plain page listing the image topics it can see. Click **`image_raw`** (or open `http://192.168.149.1:8080/stream_viewer?topic=/image_raw` directly). You should see live video from the robot. Wave at it.

If this works, the robot is streaming. Everything from here on happens on your side.

### Step 2 — Open `camera_check.py`

Open the file in your editor. Near the top is the settings block:

```python
ROBOT_IP       = "192.168.149.1"   # from ipconfig -> Default Gateway (Part C)
ROSBRIDGE_PORT = 9090
WEB_VIDEO_PORT = 8080
CAMERA_TOPIC   = "/image_raw"      # the topic the TurboPi camera publishes on
```

Check that `ROBOT_IP` matches the address you found in Part C. If it does, you do not need to change anything.

### Step 3 — Run it

In Command Prompt, go to the folder where you saved the file and run it:

```cmd
cd Desktop\lab1
python camera_check.py
```

### Step 4 — What you should see

A window with two status lines at the top and the video below. Within a few seconds both lines should turn green:

```
rosbridge  (port 9090):  connected
camera     (port 8080):  streaming /image_raw  at 10 fps
```

and the video panel shows what the robot's camera sees (about 10 frames a second — the robot is doing a lot of other image processing at the same time). **Wave at the camera.** If you see yourself, you are connected to your robot.

> **This is the whole point of the check.** If the video shows a different bench — someone else's hands, someone else's robot — you are connected to the wrong robot. Every robot has the same IP address, so the Wi-Fi network you joined in Part B is the *only* thing that decides which robot you are talking to. Disconnect, join the correct `HW…` network, and run the program again.

Close the window to quit.

### How it works

The program has three pieces. Read through the file alongside this table; you will be extending it in later labs.

**1. `RosbridgeClient`** — opens a websocket to `ws://192.168.149.1:9090`. Today it sends nothing; a successful connection is all we check. In later labs this class gains a method that publishes to `/cmd_vel` to drive the robot.

**2. `MjpegCamera`** — a background **thread** that reads the video stream:

```python
stream = urllib.request.urlopen(self.url, timeout=5)   # the response never ends
...
chunk = stream.read(8192)                               # next 8 KB of video
buf += chunk
```

```python
start = buf.find(b"\xff\xd8")             # every JPEG starts with FF D8
end   = buf.find(b"\xff\xd9", start + 2)  # ...and ends with FF D9
jpg, buf = buf[start:end + 2], buf[end + 2:]
img = Image.open(io.BytesIO(jpg))           # decode the picture
self.frame = img                            # hand it to the window
```

**3. `CameraCheckApp`** — the tkinter window. It never waits for the network itself; it just checks for a new frame 30 times a second:

```python
def update_video(self):
    if self.camera.frame_count != self.shown_count:
        ...
        self.photo = ImageTk.PhotoImage(img)
        self.video_lbl.config(image=self.photo)
    self.root.after(DISPLAY_PERIOD_MS, self.update_video)   # call me again in 33 ms
```

| Code | What it does |
|------|--------------|
| `urllib.request.urlopen(STREAM_URL)` | Opens an HTTP connection to web_video_server. Unlike a normal web page, the response never finishes — it *is* the video stream. |
| `stream.read(8192)` | Reads the next 8 KB. A JPEG may be split across two reads, so bytes are collected in a buffer until a whole image is present. |
| `buf.find(b"\xff\xd8")` / `buf.find(b"\xff\xd9")` | Finds the start and end markers of the next JPEG in the buffer. |
| `Image.open(io.BytesIO(jpg))` | Pillow decodes the JPEG bytes into a picture. |
| `threading.Thread` / `daemon=True` | The stream reader runs in its own thread so waiting for network bytes never freezes the window. `daemon=True` means it dies automatically when the program exits. |
| `root.after(33, self.update_video)` | Asks tkinter to call `update_video` again in 33 ms. This is how a GUI program repeats something forever without blocking the window. |
| `ImageTk.PhotoImage(img)` | Converts the picture into something a tkinter `Label` can display. It must be kept in a variable (`self.photo`) or Python throws it away and the panel goes blank. |

The split — network reading in a background thread, drawing in `root.after()` loops on the main thread — is the shape every GUI you write in this course will have. tkinter must only be touched from the main thread, which is why the camera thread stores the frame and lets the window pick it up.

**Try it:** in `STREAM_URL`, change `quality=70` to `quality=10` and run again. Same feed, far blockier, a fraction of the bytes over Wi-Fi. That trade-off is the whole business of video streaming.

---

## Part G: Rename Your Robot's Network

Every robot in the room is still broadcasting the same generic `HW…` name, which is exactly how people end up driving someone else's robot. Now that you have confirmed which robot is yours, give its network a unique name. **Use the naming convention your demonstrator gives you.**

The hotspot settings live in a small Python file on the robot. You edit it over SSH.

### Step 1 — Open the Wi-Fi configuration file

Log in over SSH (Part D) and open the file in the `nano` text editor:

```bash
nano /home/pi/hiwonder-toolbox/wifi_conf.py
```

You will see something like:

```python
WIFI_MODE = 1
#WIFI_AP_SSID = 'HW-Robot'
#WIFI_AP_PASSWORD = 'hiwonder'
WIFI_STA_SSID = 'hiwonder_5G'
WIFI_STA_PASSWORD = 'hiwonder'
```

| Line | Meaning |
|------|---------|
| `WIFI_MODE = 1` | **AP mode**: the robot broadcasts its own hotspot. This is what we use all term. **Leave it at 1.** |
| `#WIFI_AP_SSID` | The hotspot's name. The `#` makes it a comment, so the robot falls back to its generic default name. |
| `#WIFI_AP_PASSWORD` | The hotspot's password (default `hiwonder`). |
| `WIFI_STA_SSID` / `WIFI_STA_PASSWORD` | Only used in mode 2, where the robot *joins* an existing network instead. Ignore them. |

### Step 2 — Set the name

Using the arrow keys, move to the `WIFI_AP_SSID` line, delete the `#` at the start, and change the name to the one your demonstrator specified. Leave the quotes in place. **The name must keep the `HW-` prefix** — the robot's own software expects it (Hiwonder's phone app stops working without it). You may also uncomment and change the password if you wish; if you do, write it down.

```python
WIFI_MODE = 1
WIFI_AP_SSID = 'HW-<the name your demonstrator gave you>'
#WIFI_AP_PASSWORD = 'hiwonder'
```

> **Do not change `WIFI_MODE`.** Mode 2 makes the robot stop broadcasting and try to join a different network, and you will not be able to find it again without plugging in a monitor and keyboard.

Save and exit nano: press **Ctrl+X**, then **Y**, then **Enter**.

### Step 3 — Reboot and reconnect

The new name takes effect on the next boot:

```bash
sudo reboot
```

Your SSH session drops — that is expected. Wait about a minute. The old `HW…` network disappears from your Wi-Fi list and your new name appears in its place. Connect to it (password `hiwonder`, or the one you set).

The robot's IP address is **unchanged**: `192.168.149.1`. Prove the rename worked by logging in again:

```cmd
ssh pi@192.168.149.1
```

From now on, this is the network you join at the start of every lab.

> Hiwonder documents the same procedure in section 7.1, "Changing Wi-Fi Name and Password".

---

## Part H: Drive the Robot — GUI Teleoperation

**Teleoperation** means a human drives the robot directly: your input becomes wheel motion, with nothing deciding anything in between. In this part you complete a tkinter program on the lab computer that drives the TurboPi with an on-screen joystick. The pipeline is:

```text
mouse on the joystick -> desired velocity -> rosbridge (websocket) -> /cmd_vel topic -> motor controller -> wheels
```

Most of the program is provided. In this part you write about **nine lines**, in three marked `TODO`s (TODO 1–3) — but they are the nine lines that matter, so read the two background sections first. Parts I and J add four more TODOs to the same file.

### Background: the Twist message

Velocity commands in ROS are **`geometry_msgs/msg/Twist`** messages. The robot's motor controller subscribes to the topic **`/cmd_vel`**; whatever Twist arrives there is what the wheels do. A Twist describes motion with two 3-D vectors:

```text
geometry_msgs/msg/Twist
    Vector3 linear        # straight-line velocity, metres per second
        float64 x
        float64 y
        float64 z
    Vector3 angular       # rotational velocity, radians per second
        float64 x
        float64 y
        float64 z
```

(That is what `ros2 interface show geometry_msgs/msg/Twist` prints on the robot.)

ROS fixes what each axis means, and it is **not** the same as a screen:

| Field | Axis | `+` means | `−` means | Used today? |
|-------|------|-----------|-----------|-------------|
| `linear.x` | forward / backward | forward | backward | yes |
| `linear.y` | sideways (strafe) | **left** | right | yes |
| `linear.z` | up / down | — | — | no (ground robot) |
| `angular.z` | rotation about the vertical axis ("yaw") | turn **left** (counter-clockwise seen from above) | turn right | yes |
| `angular.x`, `angular.y` | roll, pitch | — | — | no |

The rule behind the table: ROS uses a **right-handed** coordinate frame with **x forward, y left, z up**, and positive rotation is counter-clockwise about the axis. "Positive y is *left*" is the one that catches everyone, because on a screen, right is the positive direction.

Think of it like a joystick: `linear.x` is the forward/back axis, `linear.y` is the sideways axis, and `angular.z` is the twist.

### Background: holonomic drive — why `linear.y` works at all

A car, and most simple robots, cannot move sideways. To change where it is going, it has to *turn*. Such a robot is **non-holonomic**: on the floor it has three ways it could move — forward/back, sideways, and rotation — but it can only directly control two of them. Send a car a `linear.y` and nothing happens.

The TurboPi is **holonomic**: it controls all three independently. It can strafe sideways without turning, drive diagonally while facing straight ahead, or spin on the spot while sliding — any combination of `linear.x`, `linear.y` and `angular.z` at once.

What makes that possible is its **mecanum wheels**. Look at one: instead of a plain tyre it has a ring of small rollers mounted at 45°. When the wheel spins, it pushes the robot not straight ahead but *diagonally*. Spin all four the same way and the sideways components cancel — the robot drives straight. Spin the front-left and rear-right one way and the other two the opposite way, and it is the *forward* components that cancel — the robot slides sideways. Every other direction is some mix of those. The motor controller does that arithmetic for you: you send the `Twist` you want, it works out what each of the four wheels must do.

```text
        forward              strafe right            rotate left
       ↑      ↑              ↑      ↓                ↓      ↑
      [FL]  [FR]            [FL]  [FR]              [FL]  [FR]
      [RL]  [RR]            [RL]  [RR]              [RL]  [RR]
       ↑      ↑              ↓      ↑                ↓      ↑
   all four the same    diagonal pairs oppose    left side vs right side
```

(Arrows show the direction each wheel's *tread* spins; which diagonal pair goes which way depends on how the rollers are mounted, so treat the middle picture as the idea, not a wiring diagram.)

In this lab the joystick gives you two of the three freedoms at once — push the knob diagonally and the robot moves diagonally — and the Rotate buttons give you the third. Strafing is not a gimmick: a holonomic base is what lets a robot slide sideways into a parking spot, or circle an object while keeping its camera pointed at it.

### Background: how rosbridge publishes a message

rosbridge (port 9090) is how a program with no ROS of its own talks to ROS topics. It speaks **JSON** over a websocket: every message you send is a JSON object with an `"op"` key saying what you want. Publishing takes two ops:

1. **Advertise**, once, when you connect — "I am going to publish this type on this topic":

   ```json
   {"op": "advertise", "topic": "/cmd_vel", "type": "geometry_msgs/msg/Twist"}
   ```

2. **Publish**, every time you have a message — "here is one":

   ```json
   {"op": "publish", "topic": "/cmd_vel", "msg": { ...the Twist goes here... }}
   ```

The rule for `"msg"` is simple: **it mirrors the ROS message definition exactly** — one key per field, spelled the same, and a field that is itself a message becomes a nested object. Two worked examples with *other* message types:

- `std_msgs/msg/String` has a single field, `string data`, so a message is:

  ```json
  {"data": "hello"}
  ```

- `geometry_msgs/msg/Vector3` has three fields, `float64 x`, `float64 y`, `float64 z`, so a message is:

  ```json
  {"x": 1.0, "y": 0.0, "z": 0.0}
  ```

In Python you build these as ordinary dictionaries; `json.dumps` turns them into text, and the scaffold's `_send()` already does that for you.

Two things rosbridge does **not** do — we tested both on the robot: a message with a misspelled or extra field name is **dropped silently**, and a message with a missing field is **filled in with zeros** and delivered. Neither mistake produces an error anywhere you can see it; the robot simply does not move, or moves wrongly. That is why the scaffold has a `--check` mode.

### Safety rules for live driving

- The robot goes **on the floor** in open space, never on a desk.
- Leave the speed limits alone until everything works: `MAX_LINEAR = 0.25` m/s and `MAX_ANGULAR = 1.5` rad/s.
- Know the motors' **dead-zone**: below about 0.15 m/s they do not turn at all (measured: 0.10 m/s moved one wheel, 0.15 moved all four). The scaffold raises any smaller non-zero command to `MIN_LINEAR = 0.15`, so *any* joystick deflection moves the robot at least that fast. There is no such thing as "creeping" — be ready to release.
- The program must publish a zero Twist when it exits, no matter how it exits (that is TODO 3).
- A teleop program publishes its current command at a steady rate (the scaffold does this at 10 Hz) rather than only when input changes.
- Keep one hand near **STOP** / the space bar. If in doubt, close the window; if in real doubt, switch the robot off.

### Step 1 — Read the scaffold

Open `teleop_scaffold.py`. Map of the file:

The one file carries you through Parts H, I and J: you keep building on it rather than starting over. Its map:

| Part of the file | What it does | Yours? |
|------------------|--------------|--------|
| Settings block | Robot IP and port; topic names, message types and limits for driving (Part H), the camera servos (Part I) and the sonar (Part J) | provided |
| `motor_floor()` | Raises tiny commands to `MIN_LINEAR` — the motors ignore anything smaller | provided |
| `RosbridgeClient` — connection plumbing | Connects to port 9090, advertises the two topics we publish, starts a thread that listens for messages coming *back* from the robot, sends JSON; reconnects if the link drops | provided |
| `RosbridgeClient.cmd_vel()` | Publishes one Twist | **TODO 1** (this part) |
| `twist_from_joystick()` | Turns joystick position + rotate button into `(lx, ly, az)` | **TODO 2** (this part) |
| `RosbridgeClient.set_servos()`, `move_camera()` | Aim the camera | TODO 4, 5 — **Part I, leave for now** |
| `RosbridgeClient.subscribe()`, `sonar_callback()` | Receive sonar readings | TODO 6, 7 — **Part J, leave for now** |
| `TeleopGUI` | The window: joystick, Rotate L/R (hold), STOP, space bar, camera pad and arrow keys, sonar readout, status bar, the 10 Hz publish and servo loops | provided — except **TODO 3** in `quit()` |
| `self_check()` | `--check` mode: tests every TODO except 3, on the lab computer, no robot needed | provided |

The camera pad and the sonar readout are already in the window, but do nothing until Parts I and J.

Three things the provided code does that you should notice, because every teleop program you write from now on needs them:

- **`publish_loop()` reschedules itself** with `root.after(PUBLISH_PERIOD_MS, ...)` and publishes the *current* desired velocity every time, whether or not anything changed. The robot is continuously told what to do.
- **Releasing the joystick stops the robot.** `on_release()` zeroes `joy_x` and `joy_y` and snaps the knob to centre.
- **The Rotate buttons bind `<ButtonPress-1>` and `<ButtonRelease-1>`**, not `command=`. A normal button's `command` fires once, on release, which is useless for "turn while held"; press/release bindings set `turn` on the way down and clear it on the way up.

### Step 2 — TODO 1: build the publish message

In `RosbridgeClient.cmd_vel(lx, ly, az)` the `"msg"` dictionary is empty. Fill it in so that it is a complete Twist with

```text
linear.x  = lx     linear.y  = ly     linear.z  = 0.0
angular.x = 0.0    angular.y = 0.0    angular.z = az
```

Work it out from the two background sections:

1. Look at the Twist definition. A Twist has two fields. What are their names? Those are the two keys of `"msg"`.
2. Each of those fields is a `Vector3`, which is itself a message with three fields. A message inside a message is a dictionary inside a dictionary — look at the `Vector3` example above for what each one looks like.
3. Every field must be present and spelled exactly as ROS spells it. Use `lx`, `ly`, `az` where the values come from, and `0.0` for the rest.

It comes to about four lines. Then test it — no robot needed:

```cmd
python teleop_scaffold.py --check
```

The line for TODO 1 should end in `ok`. If it says `not done yet`, your code did not change what `cmd_vel()` sends; if it lists `FAIL`s, each one names the field that is missing, misspelled, or wrong. Fix and run `--check` again. (The Part I and Part J lines will say `not done yet` — that is expected until you get there.)

### Step 3 — TODO 2: map the joystick to a Twist

`twist_from_joystick(joy_x, joy_y, turn)` receives the window's input state:

| Input | Range | Meaning |
|-------|-------|---------|
| `joy_y` | −1 … +1 | knob position up/down. `+1` = pushed fully **up**. (The scaffold has already flipped the screen's downward y axis for you.) |
| `joy_x` | −1 … +1 | knob position left/right. `+1` = pushed fully **right**. |
| `turn` | −1, 0, +1 | `+1` while **Rotate L** is held, `−1` while **Rotate R** is held, `0` otherwise |

and must return `(lx, ly, az)`. Each output is just the matching input scaled by its speed limit (`MAX_LINEAR` or `MAX_ANGULAR`). The only thing to decide is the **sign**, and the way to decide it is: *what should the robot do, and which Twist sign means that?* Fill in the last column using the Twist table above:

| Input | The robot should… | Twist field | Which sign of the field means that? | So the formula is… |
|-------|-------------------|-------------|-------------------------------------|--------------------|
| `joy_y = +1` (knob up) | drive forward | `linear.x` | `+` | `lx = joy_y * MAX_LINEAR` |
| `joy_x = +1` (knob right) | strafe **right** | `linear.y` | ? | `ly = ___ * MAX_LINEAR` |
| `turn = +1` (Rotate L) | turn left, counter-clockwise | `angular.z` | ? | `az = ___ * MAX_ANGULAR` |

Two of the three formulas look exactly like the first row. One does not — for that row, the input is positive but the Twist field must be negative. If you are not sure which, re-read the `+` column of the Twist table.

Run `--check` again. TODO 2 should now be `ok` and the summary should say `Part H: complete.` If exactly the two *strafe* cases fail and everything else passes, you have found the famous one.

### Step 4 — TODO 3: stop on exit

`quit()` runs when you close the window. Right now it disconnects and exits.

Think about what the robot knows. It does whatever the **last** `/cmd_vel` message told it. If you were driving forward and closed the window, the last message it received said "forward at 0.15 m/s" — and then the messages just stopped. Do not rely on the robot noticing the silence.

Add **one line** before `disconnect()`: which method of `self.client` sends a Twist, and which three values mean "stop"?

`--check` cannot test this one, so re-read your line and make sure it is *before* `self.client.disconnect()`.

### Step 5 — Drive

Put the robot on the floor with a metre of clear space around it. Make sure the lab computer is on your robot's Wi-Fi (the network you named in Part G). Then:

```cmd
python teleop_scaffold.py
```

Within a few seconds the top line should read **`rosbridge: connected to 192.168.149.1`** in green. The status bar at the bottom shows the exact values being published right now; while the knob is centred it reads `linear.x=+0.00  linear.y=+0.00  angular.z=+0.00`.

Drag the knob **upward** a little. The robot drives forward at 0.15 m/s (the smallest speed its motors respond to); push further and it goes up to 0.25. Release: it stops. Now work through all of these:

- [ ] Knob up → forward; knob down → backward
- [ ] Knob left → strafes left; knob right → strafes right (the robot does not turn)
- [ ] Knob **diagonally** up-and-right → the robot moves diagonally, still facing the same way. That is holonomic motion; a car cannot do it.
- [ ] Hold **Rotate L** → turns left on the spot; release → stops. Same for **Rotate R**.
- [ ] Releasing the knob stops the robot within about half a second
- [ ] **STOP** and the space bar stop everything
- [ ] Drag the knob up and, **with the mouse button still held, press Alt+F4** to close the window: the robot stops (TODO 3)

If a motion is wrong, the status bar tells you what you are sending. Compare it with the Twist table: a robot that strafes the wrong way is being sent the wrong sign of `linear.y`.

**Optional — watch your messages arrive on the robot.** Open a container shell over SSH exactly as in Part D, Step 5 (`docker exec …`, then the two `source` lines) and run:

```bash
ros2 topic echo /cmd_vel
```

Drag the joystick and watch the numbers change. Press **Ctrl+C** to stop. If your GUI says *connected* but nothing prints here, TODO 1 is producing something rosbridge rejects — run `--check`. This echo and `--check` are your only diagnostics: rosbridge itself never reports a bad message back to you.

---

## Part I: Aim the Camera — Servo Control

The camera sits on a **pan/tilt head** driven by two small servos. In this part you make the camera pad in the window (and the arrow keys) aim it. Technically it is a second thing to publish, on a second topic — but the message type is a custom one with a *list* inside it, which is the one new idea here.

### Background: the pan/tilt servos

These are hobby **PWM servos**. You do not tell a servo an angle; you send it a **pulse width** in microseconds, and it moves to the matching position and holds it:

| Pulse width | Position |
|-------------|----------|
| `1000` | one end of its travel |
| `1500` | centre |
| `2000` | the other end |

The TurboPi has two of them on the camera head, with fixed IDs:

| Servo ID | Moves the camera… | Constant |
|----------|-------------------|----------|
| **2** | left / right (**pan**) | `SERVO_PAN` |
| **1** | up / down (**tilt**) | `SERVO_TILT` |

Which way is which has been checked on our robots and encoded in the settings block: a **larger** pan pulse turns the camera **left** (`PAN_LEFT = +1`), and a **lower** tilt pulse points the camera **up** (`TILT_UP = -1`) — the opposite of the guess most people make. If your robot's camera moves the wrong way, flip the sign of the relevant constant; do not change the rest of the code.

Servos do not report where they are. If you want to *nudge* one — "50 microseconds further left" — your program has to remember where it last sent it. That is what `self.pan` and `self.tilt` in `RosbridgeClient` are for.

### Background: the SetPWMServoState message

`Twist` was a standard ROS type. This one is defined by the robot's manufacturer, in the package `ros_robot_controller_msgs`. Its definition — you can print it yourself on the robot with `ros2 interface show ros_robot_controller_msgs/msg/SetPWMServoState` — is:

```text
ros_robot_controller_msgs/msg/SetPWMServoState
    PWMServoState[] state       # one entry per servo you want to move
    float64 duration            # seconds the servos are given to get there

ros_robot_controller_msgs/msg/PWMServoState
    uint16[] id                 # servo id
    uint16[] position           # target pulse width, microseconds
    int16[]  offset             # calibration trim - leave at 0
```

**The new rule:** `[]` after a type means *a list of*. In JSON a list is `[ … ]`. A list of numbers is a list of numbers: `uint16[] id` holding servo 2 is `[2]`. A list of **messages** is a list of **dictionaries**, one per message. Worked example with another standard type, `geometry_msgs/msg/Polygon`, whose only field is `Point32[] points`:

```json
{"points": [ {"x": 0.0, "y": 0.0, "z": 0.0},
             {"x": 1.0, "y": 0.0, "z": 0.0} ]}
```

One oddity of Hiwonder's design: `id`, `position` and `offset` are *each* lists, even though we use one servo per entry. So every one of them is a one-element list, `[2]`, `[1500]`, `[0]`, and the `state` list holds one such entry per servo.

### Step 1 — What is already there

- The **camera pad** (`▲ ◀ ⌂ ▶ ▼`) and the **arrow keys** are wired up with the same press/release pattern as the Rotate buttons: pressing sets a direction (`cam_dx` / `cam_dy`), releasing clears it. `⌂` and the `c` key re-centre.
- **`servo_loop()`** runs 10 times a second and, while a direction is set, calls `move_camera()` with one `SERVO_STEP` (50 µs) in that direction. Holding a control sweeps the whole range in about two seconds. Holding a button and stepping from a loop is the same *state + repeating loop* idea as `publish_loop()`; it is more predictable than one step per click or relying on the keyboard's auto-repeat.
- **`move_camera()`** updates the remembered position and then calls **`set_servos()`**, which builds and publishes the message. The scaffold already `advertise`s the servo topic when it connects.

Your two TODOs are the last two bullets: building the message, and updating the remembered position safely.

### Step 2 — TODO 4: build the servo message

In `RosbridgeClient.set_servos(pan, tilt)`, fill in `"msg"` so it is a complete `SetPWMServoState` that moves servo `SERVO_PAN` to `pan` and servo `SERVO_TILT` to `tilt`. Work down the definition:

1. A `SetPWMServoState` has two fields. Those are the two keys of `"msg"`. One of them is a number (`SERVO_DURATION` is the value to use); the other is a list.
2. The list holds one `PWMServoState` per servo — so two dictionaries, one for pan and one for tilt.
3. Each `PWMServoState` has three fields, and *each one is a list*: the servo's id in a one-element list, the target position in a one-element list, and `[0]` for the offset.

Six or seven lines. Then:

```cmd
python teleop_scaffold.py --check
```

The TODO 4 line should end in `ok`. The check sends `set_servos(1200, 1700)` and looks for an entry with id `[2]` at `[1200]` and one with id `[1]` at `[1700]`; each `FAIL` names exactly what it could not find.

### Step 3 — TODO 5: step and clamp

`move_camera(pan_step, tilt_step)` must add the steps to `self.pan` and `self.tilt`. That is one line each — but think about what happens over time. `servo_loop()` calls this ten times a second while a button is held. Hold `◀` for three seconds: 30 steps of 50 is 1500 µs, and the pan value has gone from 1500 to 3000. The servo's range ends at 2000. A servo commanded past its end stop stalls against it — buzzing, heating, and eventually stripping its gears. This is how servos get broken.

So every new value must be **clamped** into `SERVO_MIN`…`SERVO_MAX`: if it would go above the maximum, use the maximum; below the minimum, use the minimum. Python's `min()` and `max()` do this in one expression. `min(SERVO_MAX, value)` can never be above the maximum. Wrap that in `max(SERVO_MIN, …)` and the result can never be below the minimum either. Two lines total, one for pan and one for tilt.

Run `--check`. The TODO 5 check nudges from centre, then tries to push past both ends and expects the value to stop exactly at the limit.

### Step 4 — Try it

Run the program (robot on the floor, connected). Hold `◀`: the camera turns left; the status bar shows `pan=` climbing and stopping at 2000. `▲` points it up. `⌂` re-centres. The arrow keys do the same.

To see what the camera sees while you aim it, run `camera_check.py` in a **second** Command Prompt at the same time.

> **If a direction is reversed on your robot**, flip the sign of the constant in the settings block (`PAN_LEFT`/`PAN_RIGHT` or `TILT_UP`/`TILT_DOWN`), not your TODO code.

---

## Part J: Read the Sensors — the Ultrasonic Sonar

Everything so far has flowed one way: lab computer → robot. Sensors flow the other way. In this part the robot's distance sensor reports into your window, live.

### Background: the sensor

On the front of the robot is an **ultrasonic (sonar) sensor**: it emits a click too high to hear and times the echo. Its driver publishes the distance to the nearest object ahead on the topic **`/sonar_controller/get_distance`** as a **`std_msgs/msg/Int32`**, in **millimetres**. You watched it in Part D, Step 5.

The message definition could not be simpler:

```text
std_msgs/msg/Int32
    int32 data
```

Ultrasonic sensors are cheap and useful but not precise: readings are noisy near the ends of the range and on soft or angled surfaces. Test against something flat and hard, held square to the sensor.

### Background: subscribing through rosbridge

To receive a topic, you send rosbridge a **subscribe** op:

```json
{"op": "subscribe", "topic": "/sonar_controller/get_distance", "type": "std_msgs/msg/Int32"}
```

From then on, every time a message is published on that topic, rosbridge sends *you* one — and it uses exactly the same `publish` shape you have been sending, just in the other direction:

```json
{"op": "publish", "topic": "/sonar_controller/get_distance", "msg": {"data": 512}}
```

```text
   you                              rosbridge                      sonar driver
    │  {"op":"subscribe", topic}  ─▶   │                                 │
    │                                  │  ◀── publishes Int32 on topic ──│
    │  ◀─ {"op":"publish", "msg":…}    │                                 │
    │  ◀─ {"op":"publish", "msg":…}    │  (…10 times a second…)          │
```

The scaffold already handles the receiving side: `connect()` starts a background thread, `_receive_loop()`, that reads everything rosbridge sends; for each `publish` it calls `_dispatch()`, which looks up the function you registered for that topic and calls it with the `"msg"` dictionary. `connect()` also already calls `self.subscribe(SONAR_TOPIC, SONAR_TYPE, self.sonar_callback)` for you — so once your two TODOs work, sonar readings start arriving in `sonar_callback()` automatically.

**One rule about threads.** Your callback runs on the *receive* thread, not the GUI thread. The rule from `camera_check.py` applies: **store the value, do not touch the window.** `publish_loop()`, on the GUI thread, reads `distance_mm` ten times a second and updates the sonar readout. That readout code is already written.

### Step 1 — TODO 6: the subscribe message

`subscribe(topic, msg_type, callback)` records the callback, then must send the subscribe op. Look at the `advertise` messages in `connect()`: a subscribe message has the **same three keys** with a different `"op"`. Build it from the function's **parameters** (`topic` and `msg_type`), not from the sonar constants — this function must work for *any* topic, and in the Optional Extensions you will call it with a second one. Three lines.

One thing the scaffold adds to whatever you build: `"throttle_rate": 100`. The sonar driver publishes about **1,500 readings a second** (measured on the robot), and rosbridge would faithfully forward every one of them — over 800 JSON messages a second over Wi-Fi, into your receive thread. `throttle_rate` asks rosbridge for at most one message per 100 ms per topic. The line that adds it is right under your TODO; leave it there.

Run `--check`. The TODO 6 check calls `subscribe()` with a topic that is deliberately *not* the sonar, and expects that topic in the message.

### Step 2 — TODO 7: the callback

`sonar_callback(msg)` receives the `"msg"` dictionary of each incoming message. An `Int32` has one field — you have seen the `String` example `{"data": "hello"}`; an `Int32` message looks the same with a number. Pull that field out and store it in `self.distance_mm`. One line.

Run `--check`: the check calls your callback directly with `{"data": 512}`, and then pushes a message through `_dispatch()` the way the receive thread would.

### Step 3 — Try it

Run the program. Within a second the sonar readout stops saying `waiting...` and shows a distance in centimetres. Move your hand towards the front of the robot: the number falls, and under 20 cm the readout turns red with **TOO CLOSE**.

Things worth finding out while it is running:

1. What does the sensor report when there is nothing in front of it? Is that a real distance or a "nothing seen" value?
2. Hold a book flat, then at an angle. Hold a soft object. How steady is the reading in each case?
3. What is the smallest distance it reports before the number stops making sense?

The readout is only a readout: the robot will still happily drive into the thing it is measuring. Turning this reading into a safety guard — refusing a forward command when something is too close — is where the next lab begins.

---

## Ending a Session

Do this at the end of **each** session, in this order:

1. **Close your programs.** Closing the teleop window stops the robot (TODO 3). Check that it has actually stopped.
2. **Save your work somewhere that survives.** The lab computers may be wiped between sessions and you may not get the same one next time. Copy `teleop_scaffold.py` (with your TODOs in it) and `camera_check.py` to a USB stick, your university cloud drive, or email them to yourself. **Do not rely on the Desktop.**
3. **Shut the robot down cleanly.** Over SSH:

   ```bash
   sudo shutdown now
   ```

   Wait about 20 seconds, *then* switch the robot off. Cutting the power to a running Raspberry Pi can corrupt its SD card, which means a re-imaged robot and a lost session.
4. **Charge it** if your demonstrator asks you to.
5. **Reconnect the lab computer** to the normal campus Wi-Fi so it has internet again.

**Starting Session 2:** if you are on a different computer, repeat Part A (TigerVNC, `pip install`, your saved files). Then power the robot on, join **your renamed network** from Part G, and run `camera_check.py` to prove it is your robot before you touch Part H.

---

## Checkpoint

Before moving on, all of these should be true:

- [ ] `vncviewer64-1.16.2.exe` runs on your laptop
- [ ] Your laptop is connected to your robot's `HW…` Wi-Fi network
- [ ] `ipconfig` shows a **Default Gateway** on the wireless adapter (normally `192.168.149.1`)
- [ ] `ssh pi@<robot-ip>` logs in and `hostname` prints `raspberrypi`
- [ ] TigerVNC shows the robot's desktop
- [ ] `http://192.168.149.1:8080/` in a browser shows live video from `image_raw`
- [ ] `python camera_check.py` shows both status lines green and live video — and it is *your* bench in the picture
- [ ] Your robot broadcasts the network name you gave it in Part G, and SSH still works at `192.168.149.1`
- [ ] `python teleop_scaffold.py --check` prints `ALL CHECKS PASSED`
- [ ] The robot drives forward, backward, strafes both ways, rotates both ways, stops on release, and stops when the window is closed mid-drive (Alt+F4)
- [ ] `--check` reports `Part I: complete.` — holding the camera pad or arrow keys pans and tilts the camera, `pan=`/`tilt=` in the status bar stop at 1000 and 2000, and `⌂` re-centres
- [ ] `--check` reports `Part J: complete.` — the sonar readout shows a live distance that falls as your hand approaches
- [ ] In an SSH session you can `docker exec` into the container, `source` ROS 2, and run `ros2 topic list`

---

## Troubleshooting

**No `HW…` network appears in the Wi-Fi list.** The robot is not finished booting, is switched off, or its battery is flat. Wait a full minute after switching on and refresh the list. Check the power switch and charge level.

**Connected to the robot's Wi-Fi but `ipconfig` shows no Default Gateway (or an address starting `169.254`).** Your laptop never received an address from the robot. Disconnect from the network, wait five seconds, reconnect, and check again.

**`ssh: connect to host ... : Connection timed out`** or **VNC: "unable to connect to socket".** Your laptop cannot reach that address. Almost always this means you are not actually on the robot's Wi-Fi (Windows sometimes silently switches back to a network that has internet). Check the Wi-Fi icon, reconnect to the `HW…` network, and re-check the address with `ipconfig`.

**`Permission denied, please try again.`** Wrong password. It is `raspberrypi`, all lowercase, no spaces. Remember nothing is shown while you type.

**`WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!`** SSH remembers the identity of each address it has connected to. Every TurboPi uses the same address, `192.168.149.1`, so if you connect to a *different* robot than last time (or your robot was re-imaged) SSH thinks something is wrong. Nothing is — it is just a different machine at the same address. Clear the old entry and connect again:

```cmd
ssh-keygen -R 192.168.149.1
ssh pi@192.168.149.1
```

**VNC: "Authentication failed".** The VNC password is `raspberrypi`, the same as SSH.

**VNC connects but the desktop is black or frozen.** Close the viewer window and connect again. If it persists, log in over SSH and reboot the robot with `sudo reboot`, wait a minute, then reconnect.

**`ModuleNotFoundError: No module named 'websocket'` (or `'PIL'`).** The packages from Part A, Step 3 are not installed. Installing needs internet: switch the computer to a network with internet, run `pip install websocket-client Pillow`, then switch back to the robot's Wi-Fi.

**`pip install` fails with `Permission denied` or `Access is denied`.** You do not have administrator rights on this computer. Add `--user`: `pip install --user websocket-client Pillow`.

**`'python' is not recognized as an internal or external command`.** Try `py camera_check.py`. If that fails too, Python is not installed on this computer — tell your demonstrator.

**Camera line is red: `Connection refused` or `timed out`.** The computer cannot reach port 8080 on the robot. In order of likelihood: you are not on the robot's Wi-Fi; `ROBOT_IP` in the file does not match `ipconfig`; the robot's video server is not running (does the browser page from Part F, Step 1 load? If not, tell your demonstrator).

**Camera line stays orange: `waiting for first frame...`.** Port 8080 answered but no images are arriving, which means the topic name is wrong or the camera driver on the robot is not running. Open `http://192.168.149.1:8080/` in a browser and look at the list of topics. If `image_raw` is not listed, the robot did not detect its camera at boot: check the camera's USB cable is firmly plugged into the Raspberry Pi, then reboot the robot (`sudo reboot` over SSH) and try again.

**rosbridge line is red but the camera works.** Port 9090 is not answering. Today's check is still valid — the camera proves the connection — but later labs need rosbridge, so tell your demonstrator.

**Video is jerky or lags several seconds behind.** Wi-Fi is struggling. Move closer to the robot, and try lowering `quality=70` in `STREAM_URL`.

**The video shows a different bench.** You are connected to someone else's robot. See Part F, Step 4.

**After the rename, no network with my new name appears.** Wait the full minute; the robot reboots slower than you expect. If it still does not appear, the `wifi_conf.py` edit is probably malformed (a missing quote, or the `#` still there). Look for the old generic name, connect to it, and re-open the file.

**After the rename, the network appears but I cannot connect / wrong password.** You uncommented and changed `WIFI_AP_PASSWORD`. Use the password you set. If you have lost it, ask your demonstrator.

**Teleop: `rosbridge: NOT connected - ... refused` or `... timed out`.** The computer cannot reach port 9090. Same checklist as the camera: are you on the robot's Wi-Fi? Does `ROBOT_IP` match? Does `camera_check.py` still connect? If the camera works but rosbridge does not, tell your demonstrator.

**Teleop: connected, `--check` passes, status bar shows non-zero values, but the robot does not move (or only one wheel turns).** If the value shown is below 0.15, you have changed `MIN_LINEAR` or `motor_floor()` — put them back; the motors do not turn below that. Otherwise check the battery — a low battery makes the motors weak or disables them. Confirm the messages are actually arriving with the `ros2 topic echo /cmd_vel` command in Part H, Step 5. If they arrive and the robot still does not move, tell your demonstrator.

**Teleop: the robot drives and turns fine but does not strafe.** Strafing only works if the four mecanum wheels are mounted in the right positions (their rollers must form an X seen from above). Your commands are correct — the status bar shows `linear.y` — the chassis is not. Tell your demonstrator.

**Teleop: the robot moves, but in the wrong direction.** A sign is wrong in TODO 2. Run `--check`; it names the case.

**Teleop: strafe is inverted (knob right, robot goes left).** ROS `+y` is *left*. `linear.y` must be negative when the knob is to the right.

**Teleop: the robot keeps driving after I close the window.** TODO 3 is missing, or it is after `disconnect()` instead of before. Press the robot's power switch, then fix it.

**Teleop: the robot keeps moving after I release the knob.** `on_release()` zeroes the joystick — check you have not changed it. The publish loop must also still be running: the status bar values should follow the knob.

**Teleop: jerky or delayed response.** Wi-Fi. Move closer, and close the camera window if it is open at the same time.

**`ros2: command not found`.** Either you are outside the container (prompt says `pi@`), or you are inside but forgot the two `source` lines. See Part D, Step 5.

**`docker: permission denied` or `Cannot connect to the Docker daemon`.** You are not logged in as `pi` on the robot, or you typed the command on your laptop instead of in the SSH session. Check the prompt.

**Camera does not move, but `--check` says Part I is complete.** Watch the status bar: does `pan=` change while you hold the button? If it does, the message is leaving your program — confirm it reaches the robot with `ros2 topic echo /ros_robot_controller/pwm_servo/set_state` in a container shell. If `pan=` does not change, the pad's press/release events are not reaching `servo_loop()` — make sure the window has focus (click on it) when using the arrow keys.

**Camera moves the wrong way.** Flip the sign of `PAN_LEFT`/`PAN_RIGHT` or `TILT_UP`/`TILT_DOWN` in the settings block.

**Camera moves one step and stops, or keeps moving after release.** You changed something in `cam_press`/`cam_release`/`servo_loop`. Restore it: the direction variable must be set on press, cleared on release, and the loop steps only while it is set.

**Sonar readout stays at `waiting...` although `--check` says Part J is complete.** Nothing is arriving. First make sure you are connected (green top line). Then confirm the robot is actually publishing: `ros2 topic echo /sonar_controller/get_distance` in a container shell (Part D, Step 5). If that prints numbers, your `subscribe()` message is not what rosbridge expected — re-run `--check`. If it prints nothing, the sensor driver is not running: reboot the robot.

**Sonar readout is red all the time.** Read the actual number. Something (a cable, the edge of a desk, your hand) is permanently in front of the sensor — or the reading is in millimetres and you are comparing it as centimetres somewhere you changed.

---

## Quick Reference

| | |
|---|---|
| Robot Wi-Fi network | begins with `HW` (you will rename it) — password `hiwonder` |
| Robot IP address (hotspot mode) | `192.168.149.1` — confirm with `ipconfig` → Default Gateway |
| SSH | `ssh pi@192.168.149.1` |
| VNC | TigerVNC → VNC server: `192.168.149.1` |
| Username / password | `pi` / `raspberrypi` (same for SSH and VNC) |
| Camera in a browser | `http://192.168.149.1:8080/` → click `image_raw` |
| Camera stream URL | `http://192.168.149.1:8080/stream?topic=/image_raw&type=mjpeg` |
| rosbridge | `ws://192.168.149.1:9090` |
| Python packages | `pip install websocket-client Pillow` (needs internet) |
| Camera check | `python camera_check.py` |
| Wi-Fi name file (on the robot) | `nano /home/pi/hiwonder-toolbox/wifi_conf.py` → `WIFI_AP_SSID`, then `sudo reboot` |
| Teleop self-test / drive | `python teleop_scaffold.py --check` / `python teleop_scaffold.py` |
| Into the container | `docker exec -it --user ubuntu turbopi bash`, then `source /opt/ros/humble/setup.bash` and `source /home/ubuntu/ros2_ws/install/setup.bash` |
| Useful ROS 2 commands (inside) | `ros2 topic list` · `ros2 topic echo <topic>` · `ros2 topic info <topic>` · `ros2 interface show <type>` |
| Watch `/cmd_vel` in one line | `docker exec -it --user ubuntu turbopi bash -c 'source /opt/ros/humble/setup.bash && source /home/ubuntu/ros2_ws/install/setup.bash && ros2 topic echo /cmd_vel'` |
| Manufacturer docs | https://docs.hiwonder.com/projects/TurboPi/en/advanced/ |

### Twist message reference

| Field | Effect | Example value |
|-------|--------|---------------|
| `linear.x` | Forward (+) / backward (−) | `0.15` m/s |
| `linear.y` | Strafe left (+) / right (−) | `0.15` m/s |
| `angular.z` | Turn left (+) / right (−) | `1.5` rad/s |

### Topics used in this lab

| Topic | Type | Direction | Notes |
|-------|------|-----------|-------|
| `/cmd_vel` | `geometry_msgs/msg/Twist` | we publish | m/s and rad/s; `+y` is left |
| `/ros_robot_controller/pwm_servo/set_state` | `ros_robot_controller_msgs/msg/SetPWMServoState` | we publish | servo 2 = pan, 1 = tilt; 1000–2000 µs, 1500 centre; lower tilt = up |
| `/sonar_controller/get_distance` | `std_msgs/msg/Int32` | we subscribe | **millimetres** |
| `/image_raw` | `sensor_msgs/msg/Image` | via web_video_server | port 8080 MJPEG |

### rosbridge messages used in this lab

```json
{"op": "advertise", "topic": "/cmd_vel", "type": "geometry_msgs/msg/Twist"}
{"op": "publish",   "topic": "/cmd_vel", "msg": {"linear": {...}, "angular": {...}}}
{"op": "subscribe", "topic": "/sonar_controller/get_distance", "type": "std_msgs/msg/Int32"}
```

---

## Optional Extensions

If you finish early:

- **A second sensor:** the `subscribe()` you wrote works for any topic. Run `ros2 topic list` in a container shell and look for the battery voltage or IMU topics, check their types with `ros2 topic info`, then add a second `subscribe()` call in `connect()`, a callback that stores the value, and a label that shows it.
- **Keyboard driving:** bind `<KeyPress-w>` / `<KeyRelease-w>` (and `s`, `a`, `d`, `q`, `e`) on `root` to set and clear `joy_x`, `joy_y`, `turn`, exactly as the Rotate buttons do with press/release.
- **Orbit (needs keyboard driving):** with one mouse you cannot strafe and rotate at the same time. Once `q`/`e` rotate from the keyboard, hold `e` while dragging the knob to the left: the robot strafes one way while turning the other, and circles a point on the floor while facing it. Only a holonomic robot can do this. Adjust the two speeds until the circle closes.
- **Speed slider:** a `tk.Scale` from 0.05 to 0.30 whose value replaces `MAX_LINEAR` in `twist_from_joystick()`.
- **Drive by camera:** put the camera feed from `camera_check.py` next to the joystick. The `MjpegCamera` class can be imported directly if both files are in the same folder: `from camera_check import MjpegCamera`.
- **Deadman switch:** the robot only moves while a chosen key is physically held.
- **Command log:** write every published `(lx, ly, az)` with a timestamp to a file, and print a summary on exit.
- **Looking ahead:** you now have a human driving, and a sensor that knows when something is in the way. The next lab puts a safety filter between the two. Think about which of the six motions it should be allowed to veto, and which it must never touch.
