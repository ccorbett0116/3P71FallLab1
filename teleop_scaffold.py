#!/usr/bin/env python3
"""
COSC 3P71 - Lab 1: GUI teleoperation scaffold.

Runs on the LAB COMPUTER and talks to the TurboPi over Wi-Fi through rosbridge.
You complete it in three stages, each a part of the lab manual:

    Part H  drive the robot        TODO 1, TODO 2, TODO 3
    Part I  aim the camera         TODO 4, TODO 5
    Part J  read the sonar         TODO 6, TODO 7

    python teleop_scaffold.py --check     # tests every TODO except 3 - no robot needed
    python teleop_scaffold.py             # run it

This year's joystick is DIGITAL, not analog: dragging the knob snaps it to
one of 8 compass directions (N, NE, E, SE, S, SW, W, NW) and every direction
drives at a fixed speed - how far past the centre deadzone you push the
stick does not change the speed, only which direction is selected.

Controls:
    drag the joystick        snaps to 8 directions: forward/back (linear.x)
                              and strafe (linear.y), together for a diagonal
    hold Rotate L / R        turn in place (angular.z)
    STOP button / space      stop
    hold the camera pad or arrow keys   pan / tilt the camera;  c or the centre button re-centres
    close the window         stop and disconnect

Requires:  pip install websocket-client
"""
import json
import math
import sys
import threading
import time
import tkinter as tk

try:
    import websocket                    # from the websocket-client package
except ImportError:
    sys.exit("websocket-client is not installed. Run:  pip install websocket-client")

# -- Robot settings ----------------------------------------------------------
ROBOT_IP       = "192.168.149.1"
ROSBRIDGE_PORT = 9090

# Driving (Part H)
CMD_VEL_TOPIC  = "/cmd_vel"
CMD_VEL_TYPE   = "geometry_msgs/msg/Twist"
MAX_LINEAR  = 0.25          # m/s: the speed for a cardinal direction (N/E/S/W), and for the
                            # major wheel pair on a diagonal. Keep it low until it works.
MIN_LINEAR  = 0.15          # m/s: below this the motors do not turn at all (measured on the
                            # robot). Also the speed used for the minor wheel pair on a
                            # diagonal move - see "TODO 2" in the manual.
MAX_ANGULAR = 1.5           # rad/s while a rotate button is held (below ~1.4 some wheels stall)
PUBLISH_PERIOD_MS = 100     # send /cmd_vel 10 times a second, whether or not input changed
JOY_DEADZONE = 0.3          # stick displacement below this counts as centered (stopped)

# Camera pan/tilt servos (Part I)
SERVO_TOPIC = "/ros_robot_controller/pwm_servo/set_state"
SERVO_TYPE  = "ros_robot_controller_msgs/msg/SetPWMServoState"
SERVO_PAN, SERVO_TILT = 2, 1                    # servo ids
SERVO_MIN, SERVO_MAX, SERVO_CENTER = 1000, 2000, 1500   # pulse width, microseconds
SERVO_STEP = 50             # microseconds per step while a control is held
SERVO_PERIOD_MS = 100       # step 10 times a second while held
SERVO_DURATION = 0.05       # seconds the servo is given to reach each step
# Direction multipliers, verified on our robots: a LARGER pan pulse turns the
# camera LEFT, and a LOWER tilt pulse points the camera UP.
PAN_LEFT, PAN_RIGHT = +1, -1
TILT_UP, TILT_DOWN = -1, +1

# Ultrasonic distance sensor (Part J)
SONAR_TOPIC = "/sonar_controller/get_distance"
SONAR_TYPE  = "std_msgs/msg/Int32"              # distance in MILLIMETRES
SONAR_WARN_MM = 200                             # readout turns red closer than this
SUBSCRIBE_THROTTLE_MS = 100     # ask rosbridge for at most one message per topic per 100 ms.
                                # The sonar driver publishes ~1500 times a second; without
                                # this, every one of them would be sent over Wi-Fi.

JOY_SIZE    = 240           # joystick canvas size in pixels
KNOB_RADIUS = 24
# ----------------------------------------------------------------------------


class RosbridgeClient:
    """Everything that talks to the robot, over one websocket to rosbridge.

    rosbridge speaks JSON. Everything we send is a dictionary with an "op"
    key saying what we want:

        {"op": "advertise", "topic": ..., "type": ...}   "I will publish this type on this topic"
        {"op": "publish",   "topic": ..., "msg": {...}}  "here is one message"
        {"op": "subscribe", "topic": ..., "type": ...}   "send me every message on this topic"

    and rosbridge sends us the same "publish" shape, in reverse, for every
    message on a topic we subscribed to. The "msg" dictionary always has the
    same fields, with the same names, as the ROS message type.

    This class also remembers the robot-side state we care about: where the
    camera servos are (pan, tilt) and the latest sonar reading (distance_mm).
    """

    def __init__(self, ip, port):
        self.ip, self.port = ip, port
        self.ws = None
        self.connected = False
        self.error = ""             # last connection problem, for the status line
        self._lock = threading.Lock()   # only one thread may send at a time
        self._callbacks = {}        # topic -> function to call with each message

        self.pan = SERVO_CENTER     # where we last sent the camera servos
        self.tilt = SERVO_CENTER
        self.distance_mm = None     # latest sonar reading; None until one arrives

    # ---------- connection plumbing (provided) ----------

    def connect(self):
        try:
            self.ws = websocket.WebSocket()
            self.ws.connect(f"ws://{self.ip}:{self.port}", timeout=5)
            self.connected = True
            self.error = ""
            # Tell rosbridge what we are going to publish
            self._send({"op": "advertise", "topic": CMD_VEL_TOPIC, "type": CMD_VEL_TYPE})
            self._send({"op": "advertise", "topic": SERVO_TOPIC,   "type": SERVO_TYPE})
            # Listen for messages coming back from the robot (Part J)
            threading.Thread(target=self._receive_loop, daemon=True).start()
            self.subscribe(SONAR_TOPIC, SONAR_TYPE, self.sonar_callback)
        except Exception as e:
            self.connected = False
            self.error = str(e)

    def _send(self, data):
        """Send one dictionary to rosbridge as JSON text."""
        if not self.connected or self.ws is None:
            return
        with self._lock:
            try:
                self.ws.send(json.dumps(data))
            except Exception as e:
                self.connected = False
                self.error = str(e)

    def _receive_loop(self):
        """Background thread: read everything rosbridge sends us."""
        ws = self.ws
        while self.connected and ws is self.ws:
            try:
                text = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue                        # nothing arrived for a while; fine
            except Exception as e:
                if self.connected:
                    self.connected = False
                    self.error = str(e)
                break
            try:
                self._dispatch(json.loads(text))
            except ValueError:
                pass                            # not JSON; ignore

    def _dispatch(self, data):
        """Route one incoming rosbridge message to the right place."""
        if data.get("op") == "publish":
            callback = self._callbacks.get(data.get("topic"))
            if callback:
                callback(data.get("msg", {}))

    def disconnect(self):
        self.connected = False
        if self.ws is not None:
            try:
                self.ws.abort()     # wakes the receive thread and closes the link at once
                self.ws.shutdown()
            except Exception:
                pass

    # ---------- Part H: driving ----------

    def cmd_vel(self, lx, ly, az):
        """Publish one Twist: lx = forward m/s, ly = left m/s, az = turn rad/s."""
        # TODO 1: fill in the "msg" dictionary so that it is a complete
        #         geometry_msgs/msg/Twist:
        #
        #             linear.x  = lx      linear.y  = ly      linear.z  = 0.0
        #             angular.x = 0.0     angular.y = 0.0     angular.z = az
        #
        #         See "TODO 1" in the manual for the message definition and
        #         how a ROS message becomes a dictionary.
        msg = {
            "op": "publish",
            "topic": CMD_VEL_TOPIC,
            "msg": {
                # your code here
            },
        }
        self._send(msg)

    # ---------- Part I: camera servos ----------

    def set_servos(self, pan, tilt):
        """Publish one SetPWMServoState that moves the pan servo to `pan` and
        the tilt servo to `tilt` (pulse widths in microseconds)."""
        # TODO 4: fill in the "msg" dictionary. A SetPWMServoState has two fields:
        #             state     a LIST of PWMServoState, one entry per servo
        #             duration  seconds the move may take (use SERVO_DURATION)
        #         and each PWMServoState has three fields, each a LIST:
        #             id        [servo id]        position  [pulse width]      offset  [0]
        #         You need two entries in "state": one for SERVO_PAN at `pan`,
        #         one for SERVO_TILT at `tilt`. See "TODO 4" in the manual.
        msg = {
            "op": "publish",
            "topic": SERVO_TOPIC,
            "msg": {
                # your code here
            },
        }
        if msg["msg"]:                  # nothing to send until TODO 4 is done
            self._send(msg)

    def move_camera(self, pan_step=0, tilt_step=0, center=False):
        """Nudge the camera by a step (or return it to centre), remembering
        where it is, and send the new position to the servos."""
        if center:
            self.pan = self.tilt = SERVO_CENTER
        else:
            # TODO 5: add pan_step to self.pan and tilt_step to self.tilt, and
            #         CLAMP both results into SERVO_MIN..SERVO_MAX so that
            #         holding a button can never push a servo past its limit.
            #         Two lines. See "TODO 5" in the manual.
            pass
        self.set_servos(self.pan, self.tilt)

    # ---------- Part J: sonar ----------

    def subscribe(self, topic, msg_type, callback):
        """Ask rosbridge to send us every message published on `topic`.
        `callback(msg)` is then called with each message's dictionary."""
        self._callbacks[topic] = callback
        # TODO 6: build the "subscribe" message. It has the same three keys
        #         as the "advertise" messages in connect(), with a different
        #         "op". See "TODO 6" in the manual.
        msg = {
            # your code here
        }
        if msg:
            msg.setdefault("throttle_rate", SUBSCRIBE_THROTTLE_MS)   # see settings block
            self._send(msg)

    def sonar_callback(self, msg):
        """Called with each std_msgs/msg/Int32 the sonar publishes.
        (Runs on the receive thread - store the value, do not touch the GUI.)"""
        # TODO 7: Int32 has ONE field. Store its value (millimetres) in
        #         self.distance_mm. One line. See "TODO 7" in the manual.
        pass


# PROVIDED: the 8 compass directions a snapped stick can land on, as
# (dir_x, dir_y) unit-ish components (each -1, 0 or +1), starting at E and
# going counter-clockwise in 45 degree steps - matching
# atan2(joy_y, joy_x) with joy_y = +1 UP: E, NE, N, NW, W, SW, S, SE.
_EIGHT_DIRECTIONS = [
    (1, 0), (1, 1), (0, 1), (-1, 1),
    (-1, 0), (-1, -1), (0, -1), (1, -1),
]


def snap_to_8_directions(joy_x, joy_y):
    """PROVIDED - not a TODO. Snap a raw (joy_x, joy_y) stick position to
    the nearest of the 8 cardinal/intercardinal directions. Returns
    (dir_x, dir_y), each in {-1, 0, 1}. Within JOY_DEADZONE of the center
    this returns (0, 0) - see "Constant-speed, 8-direction driving" in the
    manual for why the joystick works this way this year."""
    if math.hypot(joy_x, joy_y) < JOY_DEADZONE:
        return 0, 0
    angle = math.degrees(math.atan2(joy_y, joy_x)) % 360
    sector = round(angle / 45) % 8
    return _EIGHT_DIRECTIONS[sector]


def twist_from_joystick(joy_x, joy_y, turn):
    """Convert the window's input state into Twist values.

        joy_x : -1.0 .. 1.0    knob position, +1 = pushed fully RIGHT
        joy_y : -1.0 .. 1.0    knob position, +1 = pushed fully UP
        turn  : -1, 0, +1      +1 while "Rotate L" is held, -1 while "Rotate R" is held

    Returns (lx, ly, az): forward speed in m/s, left speed in m/s, turn rate in rad/s.
    """
    # PROVIDED: snap the raw stick position to the nearest of the 8 compass
    # directions, and count how many axes are involved: 0 (centred), 1 (a
    # cardinal direction: only linear.x OR linear.y is nonzero) or 2 (a
    # diagonal: both are).
    dir_x, dir_y = snap_to_8_directions(joy_x, joy_y)
    axes_active = abs(dir_x) + abs(dir_y)

    if axes_active == 2:
        # PROVIDED: a diagonal drives BOTH linear.x and linear.y at once. A
        # mecanum drivetrain mixes them per wheel (roughly FL = vx-vy,
        # FR = vx+vy, RL = vx+vy, RR = vx-vy), so sending MAX_LINEAR on both
        # would leave two wheels idle and spin the other two at DOUBLE
        # speed. This uneven split instead puts one wheel pair at
        # MAX_LINEAR and the other at MIN_LINEAR (the slowest speed the
        # motors actually turn at) - see "Constant-speed, 8-direction
        # driving" in the manual for the derivation.
        lx = dir_y * (MAX_LINEAR + MIN_LINEAR) / 2
        ly = -dir_x * (MAX_LINEAR - MIN_LINEAR) / 2
    elif axes_active == 1:
        # TODO 2: a cardinal direction drives only ONE of linear.x /
        #         linear.y. Fill in lx and ly from dir_x, dir_y and
        #         MAX_LINEAR. Two lines. Before writing them, work through
        #         the sign table under "TODO 2" in the manual: one of the
        #         two signs is not what you would first expect.
        lx = 0.0
        ly = 0.0
    else:
        lx = ly = 0.0                   # centred: PROVIDED

    # TODO 2 (continued): az from turn and MAX_ANGULAR. One line.
    az = 0.0
    return lx, ly, az


class TeleopGUI:
    """The window. Turns mouse and keyboard input into desired motion
    (joy_x / joy_y / turn for the wheels, cam_dx / cam_dy for the camera)
    and publishes at a steady rate. Everything here is provided except TODO 3."""

    def __init__(self, root, client):
        self.root = root
        self.client = client
        self.joy_x = 0.0
        self.joy_y = 0.0
        self.turn = 0.0
        self.cam_dx = 0             # pan direction while a control is held (Part I)
        self.cam_dy = 0             # tilt direction while a control is held (Part I)
        self.running = True

        root.title(f"TurboPi Teleop - {ROBOT_IP}")
        root.resizable(False, False)
        self.build_layout()
        self.bind_keys()

        threading.Thread(target=self.connect_loop, daemon=True).start()
        self.publish_loop()
        self.servo_loop()
        root.protocol("WM_DELETE_WINDOW", self.quit)

    # ---------- layout ----------

    def build_layout(self):
        self.conn_lbl = tk.Label(self.root, text="rosbridge: connecting...",
                                 fg="dark orange", anchor="w")
        self.conn_lbl.pack(fill=tk.X, padx=10, pady=(8, 0))

        main = tk.Frame(self.root)
        main.pack(padx=10, pady=4)

        # --- left: virtual joystick and rotate/stop buttons ---
        left = tk.Frame(main)
        left.grid(row=0, column=0, padx=(0, 16))
        tk.Label(left, text="Drive (drag the knob; release to stop)").pack()
        self.canvas = tk.Canvas(left, width=JOY_SIZE, height=JOY_SIZE,
                                bg="white", highlightthickness=1)
        self.canvas.pack(pady=4)
        c = JOY_SIZE / 2
        self.canvas.create_oval(10, 10, JOY_SIZE - 10, JOY_SIZE - 10,
                                outline="gray70", width=2)
        self.canvas.create_line(c, 10, c, JOY_SIZE - 10, fill="gray85")
        self.canvas.create_line(10, c, JOY_SIZE - 10, c, fill="gray85")
        self.knob = self.canvas.create_oval(
            c - KNOB_RADIUS, c - KNOB_RADIUS, c + KNOB_RADIUS, c + KNOB_RADIUS,
            fill="steelblue", outline="")
        self.canvas.bind("<ButtonPress-1>", self.on_drag)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

        row = tk.Frame(left)
        row.pack(pady=6)
        self.make_hold_button(row, "⟲ Rotate L", +1.0).pack(side=tk.LEFT, padx=4)
        tk.Button(row, text="STOP", fg="white", bg="firebrick", width=8,
                  command=self.stop_all).pack(side=tk.LEFT, padx=4)
        self.make_hold_button(row, "Rotate R ⟳", -1.0).pack(side=tk.LEFT, padx=4)

        # --- right: sonar readout (Part J) and camera pad (Part I) ---
        right = tk.Frame(main)
        right.grid(row=0, column=1, sticky="n")

        tk.Label(right, text="Sonar (Part J)").pack(pady=(4, 0))
        self.sonar_lbl = tk.Label(right, text="waiting...", fg="gray40",
                                  font=("TkDefaultFont", 12, "bold"))
        self.sonar_lbl.pack(pady=(0, 12))

        tk.Label(right, text="Camera (Part I)\nhold a button or an arrow key").pack()
        pad = tk.Frame(right)
        pad.pack(pady=4)
        self.make_cam_button(pad, "▲", dy=TILT_UP).grid(row=0, column=1)
        self.make_cam_button(pad, "◀", dx=PAN_LEFT).grid(row=1, column=0)
        tk.Button(pad, text="⌂", width=3,
                  command=lambda: self.client.move_camera(center=True)).grid(row=1, column=1)
        self.make_cam_button(pad, "▶", dx=PAN_RIGHT).grid(row=1, column=2)
        self.make_cam_button(pad, "▼", dy=TILT_DOWN).grid(row=2, column=1)

        # --- status bar: what is being sent right now ---
        self.status = tk.Label(self.root, text="", anchor="w", relief=tk.SUNKEN,
                               font=("Courier", 10))
        self.status.pack(fill=tk.X, padx=10, pady=(0, 8))

    def make_hold_button(self, parent, text, direction):
        """A button that turns the robot only WHILE it is held down.

        A normal tkinter Button(command=...) fires once, on release, which
        is no use for "hold to turn". So we bind the press and release
        events ourselves: press sets self.turn, release clears it.
        """
        btn = tk.Button(parent, text=text, width=10)
        btn.bind("<ButtonPress-1>", lambda e: self.set_turn(direction))
        btn.bind("<ButtonRelease-1>", lambda e: self.set_turn(0.0))
        return btn

    def make_cam_button(self, parent, text, dx=0, dy=0):
        """Same press/release idea for the camera pad: the camera keeps
        stepping (in servo_loop) for as long as the button is held."""
        btn = tk.Button(parent, text=text, width=3)
        btn.bind("<ButtonPress-1>", lambda e: self.cam_press(dx, dy))
        btn.bind("<ButtonRelease-1>", lambda e: self.cam_release(dx, dy))
        return btn

    def bind_keys(self):
        self.root.bind("<space>", lambda e: self.stop_all())
        # Arrow keys pan/tilt the camera while held; c re-centres it
        for key, dx, dy in (("Left", PAN_LEFT, 0), ("Right", PAN_RIGHT, 0),
                            ("Up", 0, TILT_UP), ("Down", 0, TILT_DOWN)):
            self.root.bind(f"<KeyPress-{key}>",
                           lambda e, dx=dx, dy=dy: self.cam_press(dx, dy))
            self.root.bind(f"<KeyRelease-{key}>",
                           lambda e, dx=dx, dy=dy: self.cam_release(dx, dy))
        self.root.bind("c", lambda e: self.client.move_camera(center=True))

    # ---------- networking ----------

    def connect_loop(self):
        """Background thread: connect, and reconnect if the link drops."""
        while self.running:
            if not self.client.connected:
                self.client.connect()
            time.sleep(3)

    # ---------- input handlers ----------

    def set_turn(self, direction):
        self.turn = direction

    def cam_press(self, dx=0, dy=0):
        if dx:
            self.cam_dx = dx
        if dy:
            self.cam_dy = dy

    def cam_release(self, dx=0, dy=0):
        # only clear a direction if it is the one being released, so that
        # overlapping presses behave sensibly
        if dx and self.cam_dx == dx:
            self.cam_dx = 0
        if dy and self.cam_dy == dy:
            self.cam_dy = 0

    def on_drag(self, event):
        """Mouse pressed or dragged on the joystick: move the knob and
        convert its position to joy_x / joy_y in -1..1."""
        c = JOY_SIZE / 2
        usable = c - 10 - KNOB_RADIUS
        dx = max(-1.0, min(1.0, (event.x - c) / usable))
        dy = max(-1.0, min(1.0, (event.y - c) / usable))
        self.joy_x = dx
        self.joy_y = -dy            # screen y grows DOWNWARD; up must be +
        # PROVIDED: draw the knob snapped to the same 8 directions the robot
        # actually drives in, instead of following the raw mouse position.
        dir_x, dir_y = snap_to_8_directions(self.joy_x, self.joy_y)
        self.draw_knob(dir_x * usable, -dir_y * usable)

    def on_release(self, event):
        """Mouse released: knob snaps to centre and the robot stops."""
        self.joy_x = self.joy_y = 0.0
        self.draw_knob(0, 0)

    def draw_knob(self, px, py):
        c = JOY_SIZE / 2
        self.canvas.coords(self.knob,
                           c + px - KNOB_RADIUS, c + py - KNOB_RADIUS,
                           c + px + KNOB_RADIUS, c + py + KNOB_RADIUS)

    def stop_all(self):
        self.joy_x = self.joy_y = 0.0
        self.turn = 0.0
        self.draw_knob(0, 0)

    # ---------- repeating loops ----------

    def publish_loop(self):
        """Runs every PUBLISH_PERIOD_MS. It always publishes the CURRENT
        desired velocity, even when nothing has changed: the robot is
        continuously told what to do, so if this program dies the commands
        simply stop arriving instead of the last one running forever."""
        lx, ly, az = twist_from_joystick(self.joy_x, self.joy_y, self.turn)
        self.client.cmd_vel(lx, ly, az)

        self.status.config(
            text=f"linear.x={lx:+.2f}  linear.y={ly:+.2f}  angular.z={az:+.2f}"
                 f"   pan={self.client.pan}  tilt={self.client.tilt}")

        if self.client.connected:
            text, colour = f"rosbridge: connected to {ROBOT_IP}", "green4"
        else:
            text = (f"rosbridge: NOT connected - {self.client.error or 'connecting...'}"
                    "  (retrying)")
            colour = "red"
        self.conn_lbl.config(text=text, fg=colour)

        # Sonar readout (comes alive once TODO 6 and TODO 7 are done)
        d = self.client.distance_mm
        if d is None:
            self.sonar_lbl.config(text="waiting...", fg="gray40")
        elif d < SONAR_WARN_MM:
            self.sonar_lbl.config(text=f"{d / 10:.0f} cm  TOO CLOSE", fg="red")
        else:
            self.sonar_lbl.config(text=f"{d / 10:.0f} cm", fg="green4")

        if self.running:
            self.root.after(PUBLISH_PERIOD_MS, self.publish_loop)

    def servo_loop(self):
        """Runs every SERVO_PERIOD_MS: steps the camera while a pad button
        or arrow key is held. Holding sweeps the full range in ~2 seconds."""
        if self.cam_dx or self.cam_dy:
            self.client.move_camera(pan_step=self.cam_dx * SERVO_STEP,
                                    tilt_step=self.cam_dy * SERVO_STEP)
        if self.running:
            self.root.after(SERVO_PERIOD_MS, self.servo_loop)

    def quit(self):
        """Called when the window is closed."""
        self.running = False
        # TODO 3: the robot keeps doing whatever the LAST message told it.
        #         If you were driving forward when you closed the window,
        #         what must be sent before we disconnect? One line.

        time.sleep(0.2)                 # give the last message time to leave
        self.client.disconnect()
        self.root.destroy()


# ---------------------------------------------------------------------------
# Self-check: `python teleop_scaffold.py --check`
# Tests every TODO except TODO 3, on this computer, with no robot involved.
# ---------------------------------------------------------------------------

def _captured_client():
    """A client whose _send() records messages instead of sending them."""
    client = RosbridgeClient(ROBOT_IP, ROSBRIDGE_PORT)
    sent = []
    client.connected = True
    client._send = sent.append
    return client, sent


def _check_todo1():
    client, sent = _captured_client()
    client.cmd_vel(0.12, -0.34, 0.56)
    if len(sent) != 1:
        return [f"expected exactly one message to be sent, got {len(sent)}"], False
    m = sent[0]
    msg = m.get("msg")
    if not msg:
        return [], True                                   # not started
    problems = []
    if m.get("op") != "publish":
        problems.append('"op" should be "publish"')
    if m.get("topic") != CMD_VEL_TOPIC:
        problems.append(f'"topic" should be "{CMD_VEL_TOPIC}"')
    for part in ("linear", "angular"):
        if not isinstance(msg.get(part), dict):
            problems.append(f'"msg" needs a "{part}" dictionary (a Twist has two: linear and angular)')
            continue
        for axis in "xyz":
            if not isinstance(msg[part].get(axis), (int, float)):
                problems.append(f'"{part}" needs a numeric "{axis}" (a Vector3 has x, y and z)')
        extra = set(msg[part]) - set("xyz")
        if extra:
            problems.append(f'"{part}" has fields ROS does not know: {sorted(extra)}')
    extra = set(msg) - {"linear", "angular"}
    if extra:
        problems.append(f'"msg" has fields a Twist does not have: {sorted(extra)}')
    expected = {"linear":  {"x": 0.12, "y": -0.34, "z": 0.0},
                "angular": {"x": 0.0,  "y": 0.0,   "z": 0.56}}
    if not problems and msg != expected:
        problems.append(f"cmd_vel(0.12, -0.34, 0.56) should send msg = {expected}\n"
                        f"            but sent msg = {msg}")
    return problems, False


def _check_todo2():
    # "not started" is judged only from the cases YOUR lines control
    # (cardinal, rotate, centred, and the deadzone) - the diagonal cases are
    # provided code and should already be correct even before you touch
    # TODO 2, so they are not part of that judgement, only of the FAIL list
    # once you have started.
    L, M, A = MAX_LINEAR, MIN_LINEAR, MAX_ANGULAR
    vx_diag, vy_diag = (L + M) / 2, (L - M) / 2
    todo_cases = [
        ((0, 1, 0),   (L, 0.0, 0.0),   "knob UP -> drive forward"),
        ((0, -1, 0),  (-L, 0.0, 0.0),  "knob DOWN -> drive backward"),
        ((-1, 0, 0),  (0.0, L, 0.0),   "knob LEFT -> strafe left"),
        ((1, 0, 0),   (0.0, -L, 0.0),  "knob RIGHT -> strafe right  (which way is +y in ROS?)"),
        ((0, 0, 1),   (0.0, 0.0, A),   "Rotate L held -> turn left (counter-clockwise)"),
        ((0, 0, -1),  (0.0, 0.0, -A),  "Rotate R held -> turn right (clockwise)"),
        ((0, 0.5, 0), (L, 0.0, 0.0),   "knob HALF way up -> still FULL speed (constant speed, not proportional)"),
        ((0, 0, 0),   (0.0, 0.0, 0.0), "knob centred, nothing held -> all zero"),
    ]
    provided_cases = [
        ((0.7, 0.7, 0),   (vx_diag, -vy_diag, 0.0),  "knob up-right -> snaps to NE (diagonal split is provided code)"),
        ((-0.7, 0.7, 0),  (vx_diag, vy_diag, 0.0),   "knob up-left -> snaps to NW (diagonal split is provided code)"),
        ((0.7, -0.7, 0),  (-vx_diag, -vy_diag, 0.0), "knob down-right -> snaps to SE (diagonal split is provided code)"),
        ((-0.7, -0.7, 0), (-vx_diag, vy_diag, 0.0),  "knob down-left -> snaps to SW (diagonal split is provided code)"),
    ]
    results = [twist_from_joystick(jx, jy, t) for (jx, jy, t), _, _ in todo_cases]
    if all(r == (0.0, 0.0, 0.0) for r in results):
        return [], True                                   # not started
    problems = []
    for (jx, jy, t), want, desc in todo_cases + provided_cases:
        got = twist_from_joystick(jx, jy, t)
        if not all(abs(g - w) < 1e-9 for g, w in zip(got, want)):
            problems.append(f"{desc}\n            joy_x={jx} joy_y={jy} turn={t}: "
                            f"expected (lx, ly, az) = {want}, got {tuple(round(g, 3) for g in got)}")
    return problems, False


def _check_todo4():
    client, sent = _captured_client()
    client.set_servos(1200, 1700)
    if not sent:
        return [], True                                   # not started (nothing is sent while "msg" is empty)
    if len(sent) != 1:
        return [f"expected exactly one message to be sent, got {len(sent)}"], False
    m = sent[0]
    msg = m.get("msg")
    problems = []
    if m.get("op") != "publish":
        problems.append('"op" should be "publish"')
    if m.get("topic") != SERVO_TOPIC:
        problems.append(f'"topic" should be "{SERVO_TOPIC}"')
    extra = set(msg) - {"state", "duration"}
    if extra:
        problems.append(f'"msg" has fields a SetPWMServoState does not have: {sorted(extra)}')
    if not isinstance(msg.get("duration"), (int, float)):
        problems.append('"msg" needs a numeric "duration"')
    state = msg.get("state")
    if not isinstance(state, list):
        problems.append('"state" must be a LIST (one PWMServoState per servo) - is it a list?')
        return problems, False
    if len(state) != 2:
        problems.append(f'"state" should have 2 entries (pan and tilt), it has {len(state)}')
    found = {}
    for i, entry in enumerate(state):
        if not isinstance(entry, dict):
            problems.append(f'"state"[{i}] should be a dictionary (a PWMServoState)')
            continue
        extra = set(entry) - {"id", "position", "offset"}
        if extra:
            problems.append(f'"state"[{i}] has fields a PWMServoState does not have: {sorted(extra)}')
        for field in ("id", "position", "offset"):
            if not isinstance(entry.get(field), list):
                problems.append(f'"state"[{i}] needs "{field}" and it must be a LIST, e.g. [{"0" if field == "offset" else "..."}]')
        if isinstance(entry.get("id"), list) and len(entry["id"]) == 1:
            found[entry["id"][0]] = entry
    for sid, want, name in ((SERVO_PAN, 1200, "pan"), (SERVO_TILT, 1700, "tilt")):
        entry = found.get(sid)
        if entry is None:
            problems.append(f'no entry with "id": [{sid}] (the {name} servo)')
        else:
            if entry.get("position") != [want]:
                problems.append(f'the {name} servo (id {sid}) should have "position": [{want}], got {entry.get("position")}')
            if entry.get("offset") != [0]:
                problems.append(f'the {name} servo (id {sid}) should have "offset": [0], got {entry.get("offset")}')
    return problems, False


def _check_todo5():
    client, sent = _captured_client()
    client.pan = client.tilt = SERVO_CENTER
    client.move_camera(pan_step=SERVO_STEP)
    if (client.pan, client.tilt) == (SERVO_CENTER, SERVO_CENTER):
        return [], True                                   # not started
    problems = []
    if (client.pan, client.tilt) != (SERVO_CENTER + SERVO_STEP, SERVO_CENTER):
        problems.append(f"from centre, move_camera(pan_step={SERVO_STEP}) should give pan={SERVO_CENTER + SERVO_STEP}, "
                        f"tilt={SERVO_CENTER}; got pan={client.pan}, tilt={client.tilt}")
    client.pan = client.tilt = SERVO_CENTER
    client.move_camera(tilt_step=-SERVO_STEP)
    if (client.pan, client.tilt) != (SERVO_CENTER, SERVO_CENTER - SERVO_STEP):
        problems.append(f"from centre, move_camera(tilt_step={-SERVO_STEP}) should give pan={SERVO_CENTER}, "
                        f"tilt={SERVO_CENTER - SERVO_STEP}; got pan={client.pan}, tilt={client.tilt}")
    client.pan = SERVO_MAX - 10
    client.move_camera(pan_step=SERVO_STEP)
    if client.pan != SERVO_MAX:
        problems.append(f"pan was {SERVO_MAX - 10} and you stepped by +{SERVO_STEP}: it must be CLAMPED to {SERVO_MAX}, got {client.pan}")
    client.tilt = SERVO_MIN + 10
    client.move_camera(tilt_step=-SERVO_STEP)
    if client.tilt != SERVO_MIN:
        problems.append(f"tilt was {SERVO_MIN + 10} and you stepped by -{SERVO_STEP}: it must be CLAMPED to {SERVO_MIN}, got {client.tilt}")
    if len(sent) != 4:
        problems.append("move_camera() should call set_servos() exactly once per call")
    return problems, False


def _check_todo6():
    client, sent = _captured_client()
    # deliberately NOT the sonar topic: subscribe() must work for any topic
    client.subscribe("/some/other/topic", "std_msgs/msg/String", client.sonar_callback)
    if not sent:
        return [], True                                   # not started
    m = sent[0]
    problems = []
    if m.get("op") != "subscribe":
        problems.append(f'"op" should be "subscribe", got {m.get("op")!r}')
    if m.get("topic") != "/some/other/topic":
        problems.append(f'"topic" should be the topic passed in as a parameter, got {m.get("topic")!r}')
    if m.get("type") != "std_msgs/msg/String":
        problems.append(f'"type" should be the type passed in as a parameter, got {m.get("type")!r}')
    extra = set(m) - {"op", "topic", "type", "throttle_rate", "queue_length"}
    if extra:
        problems.append(f"unexpected keys: {sorted(extra)}")
    return problems, False


def _check_todo7():
    client, _ = _captured_client()
    client.sonar_callback({"data": 512})
    if client.distance_mm is None:
        return [], True                                   # not started
    problems = []
    if client.distance_mm != 512:
        problems.append(f'sonar_callback({{"data": 512}}) should set distance_mm = 512, got {client.distance_mm!r}')
    # and through the real receive path:
    client._callbacks[SONAR_TOPIC] = client.sonar_callback
    client._dispatch({"op": "publish", "topic": SONAR_TOPIC, "msg": {"data": 87}})
    if client.distance_mm != 87:
        problems.append("a message arriving through _dispatch() did not update distance_mm")
    return problems, False


def self_check():
    checks = [
        ("Part H", "TODO 1", "cmd_vel() builds a Twist publish message", _check_todo1),
        ("Part H", "TODO 2", "twist_from_joystick() maps input to Twist values", _check_todo2),
        ("Part I", "TODO 4", "set_servos() builds a SetPWMServoState publish message", _check_todo4),
        ("Part I", "TODO 5", "move_camera() steps and clamps the servo positions", _check_todo5),
        ("Part J", "TODO 6", "subscribe() builds a subscribe message", _check_todo6),
        ("Part J", "TODO 7", "sonar_callback() stores the distance", _check_todo7),
    ]
    summary = {}
    for part, todo, title, fn in checks:
        try:
            problems, not_started = fn()
        except Exception as e:                            # a crash in student code
            problems, not_started = [f"crashed with {type(e).__name__}: {e}"], False
        if not_started:
            state = "not done yet"
        elif problems:
            state = f"{len(problems)} problem(s)"
        else:
            state = "ok"
        print(f"{part}  {todo}  {title:<58} {state}")
        for p in problems:
            print(f"        FAIL: {p}")
        summary.setdefault(part, []).append(state)

    print()
    for part, states in summary.items():
        if all(s == "ok" for s in states):
            print(f"{part}: complete.")
        elif all(s == "not done yet" for s in states):
            print(f"{part}: not started.")
        else:
            print(f"{part}: not finished - fix the FAILs above and run --check again.")
    print("(TODO 3 cannot be checked here - re-read it before you drive.)")
    return 0 if all(s == "ok" for s in summary["Part H"]) else 1


def main():
    if "--check" in sys.argv:
        sys.exit(self_check())
    client = RosbridgeClient(ROBOT_IP, ROSBRIDGE_PORT)
    root = tk.Tk()
    TeleopGUI(root, client)
    root.mainloop()


if __name__ == "__main__":
    main()
