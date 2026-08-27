from std.math import max, min, sqrt
from std.memory import Pointer
from std.sys import align_of, size_of


comptime ACTION_NONE = Int32(0)
comptime ACTION_MOVE = Int32(1)
comptime ACTION_BUTTON_DOWN = Int32(2)
comptime ACTION_BUTTON_UP = Int32(3)
comptime ACTION_SCROLL = Int32(4)
comptime MGESTURE_MOJO_ABI_VERSION = Int32(1)
comptime LANDMARK_COUNT = Int(63)
comptime LANDMARK_ABS_LIMIT = Float64(2.0)
comptime MIN_PALM_SCALE = Float64(0.0001)

comptime STATE_PAUSED = Int32(0)
comptime STATE_ARMED = Int32(1)
comptime STATE_LEFT_DOWN = Int32(2)
comptime STATE_RIGHT_DOWN = Int32(3)
comptime STATE_SCROLL = Int32(4)


@fieldwise_init
struct MojoConfig(Copyable, Movable, Writable):
    var screen_x: Float64
    var screen_y: Float64
    var screen_width: Float64
    var screen_height: Float64
    var mirror: Int32
    var handedness_confidence: Float64
    var active_left: Float64
    var active_right: Float64
    var active_top: Float64
    var active_bottom: Float64
    var pointer_gain: Float64
    var pointer_acceleration: Float64
    var dead_zone: Float64
    var filter_min_cutoff: Float64
    var filter_beta: Float64
    var filter_derivative_cutoff: Float64
    var pinch_down_threshold: Float64
    var pinch_release_threshold: Float64
    var debounce_ms: Int64
    var release_debounce_ms: Int64
    var hand_loss_timeout_ms: Int64
    var reacquisition_ms: Int64
    var scroll_entry_ms: Int64
    var scroll_sensitivity: Float64
    var scroll_direction: Int32
    var scroll_dead_zone: Float64
    var activation_gesture: Int32
    var activation_gesture_ms: Int64
    var activation_cooldown_ms: Int64


@fieldwise_init
struct MojoAction(Copyable, Movable, Writable):
    var action: Int32
    var state: Int32
    var button: Int32
    var state_order: Int32
    var x: Float64
    var y: Float64


@fieldwise_init
struct Measurements(Copyable, Movable, Writable):
    var index_pinch: Float64
    var middle_pinch: Float64
    var palm_x: Float64
    var palm_y: Float64
    var index_x: Float64
    var index_y: Float64
    var scroll_pose: Bool
    var open_palm: Bool


@fieldwise_init
struct FilteredPoint(Copyable, Movable, Writable):
    var x: Float64
    var y: Float64


struct GestureEngine(Copyable, Movable, Writable):
    var config: MojoConfig
    var armed: Bool
    var state: Int32
    var held: Int32
    var active_hand: Int32
    var down_candidate: Int32
    var down_since_ms: Int64
    var release_since_ms: Int64
    var invalid_since_ms: Int64
    var reacquire_since_ms: Int64
    var last_x: Float64
    var last_y: Float64
    var last_palm_y: Float64
    var scroll_remainder: Float64
    var scroll_active: Bool
    var scroll_entry_since_ms: Int64
    var open_since_ms: Int64
    var last_toggle_ms: Int64
    var initialized: Bool
    var filter_x: Float64
    var filter_y: Float64
    var filter_dx: Float64
    var filter_dy: Float64
    var filter_last_x: Float64
    var filter_last_y: Float64
    var filter_last_time: Float64
    var filter_initialized: Bool
    var derivative_initialized: Bool

    def __init__(out self, config: MojoConfig, armed: Int32):
        self.config = config.copy()
        self.armed = armed != 0
        self.state = STATE_ARMED if self.armed else STATE_PAUSED
        self.held = 0
        self.active_hand = 0
        self.down_candidate = 0
        self.down_since_ms = 0
        self.release_since_ms = -1
        self.invalid_since_ms = -1
        self.reacquire_since_ms = 0
        self.last_x = -1.0
        self.last_y = -1.0
        self.last_palm_y = -1.0
        self.scroll_remainder = 0.0
        self.scroll_active = False
        self.scroll_entry_since_ms = -2
        self.open_since_ms = -1
        self.last_toggle_ms = 0
        self.initialized = False
        self.filter_x = 0.0
        self.filter_y = 0.0
        self.filter_dx = 0.0
        self.filter_dy = 0.0
        self.filter_last_x = 0.0
        self.filter_last_y = 0.0
        self.filter_last_time = 0.0
        self.filter_initialized = False
        self.derivative_initialized = False

    @staticmethod
    def create(config: MojoConfig, armed: Int32) -> Self:
        return Self(config, armed)

    def initialize(mut self, config: MojoConfig, armed: Int32):
        self.config = config.copy()
        self.armed = armed != 0
        self.state = STATE_ARMED if self.armed else STATE_PAUSED
        self.held = 0
        self.active_hand = 0
        self.down_candidate = 0
        self.down_since_ms = 0
        self.release_since_ms = -1
        self.invalid_since_ms = -1
        self.reacquire_since_ms = 0
        self.last_x = -1.0
        self.last_y = -1.0
        self.last_palm_y = -1.0
        self.scroll_remainder = 0.0
        self.scroll_active = False
        self.scroll_entry_since_ms = -2
        self.open_since_ms = -1
        self.last_toggle_ms = 0
        self.initialized = False

    def reset_transient(mut self):
        self.down_candidate = 0
        self.down_since_ms = 0
        self.release_since_ms = -1
        self.invalid_since_ms = -1
        self.reacquire_since_ms = 0
        self.last_x = -1.0
        self.last_y = -1.0
        self.last_palm_y = -1.0
        self.scroll_remainder = 0.0
        self.scroll_active = False
        self.scroll_entry_since_ms = -2
        self.open_since_ms = -1
        self.initialized = False
        self.filter_x = 0.0
        self.filter_y = 0.0
        self.filter_dx = 0.0
        self.filter_dy = 0.0
        self.filter_last_x = 0.0
        self.filter_last_y = 0.0
        self.filter_last_time = 0.0
        self.filter_initialized = False
        self.derivative_initialized = False

    def reset_internal(mut self) -> MojoAction:
        var button = self.held
        self.held = 0
        self.active_hand = 0
        self.reset_transient()
        self.state = STATE_ARMED if self.armed else STATE_PAUSED
        if button != 0:
            return Self.result_after(ACTION_BUTTON_UP, 0.0, 0.0, button, self.state)
        return Self.result(ACTION_NONE, 0.0, 0.0, 0, self.state)

    def set_armed_internal(mut self, value: Int32) -> MojoAction:
        var button = self.held
        self.armed = value != 0
        self.held = 0
        self.active_hand = 0
        self.reset_transient()
        self.state = STATE_ARMED if self.armed else STATE_PAUSED
        if button != 0 and not self.armed:
            return Self.result_after(ACTION_BUTTON_UP, 0.0, 0.0, button, STATE_PAUSED)
        return Self.result(ACTION_NONE, 0.0, 0.0, 0, self.state)

    @staticmethod
    def coord(landmarks: Pointer[mut=True, Float32, MutAnyOrigin], point: Int, axis: Int) -> Float64:
        return Float64(landmarks[unsafe_offset=point * 3 + axis])

    @staticmethod
    def distance(landmarks: Pointer[mut=True, Float32, MutAnyOrigin], first: Int, second: Int) -> Float64:
        var dx = Self.coord(landmarks, first, 0) - Self.coord(landmarks, second, 0)
        var dy = Self.coord(landmarks, first, 1) - Self.coord(landmarks, second, 1)
        var dz = Self.coord(landmarks, first, 2) - Self.coord(landmarks, second, 2)
        return sqrt(dx * dx + dy * dy + dz * dz)

    @staticmethod
    def palm_scale(landmarks: Pointer[mut=True, Float32, MutAnyOrigin]) -> Float64:
        return 0.5 * (Self.distance(landmarks, 0, 9) + Self.distance(landmarks, 5, 17))

    @staticmethod
    def valid_landmarks(landmarks: Pointer[mut=True, Float32, MutAnyOrigin]) -> Bool:
        for i in range(LANDMARK_COUNT):
            var value = Float64(landmarks[unsafe_offset=i])
            if value != value or abs(value) > LANDMARK_ABS_LIMIT:
                return False
        return Self.palm_scale(landmarks) > MIN_PALM_SCALE

    @staticmethod
    def finger_extended(landmarks: Pointer[mut=True, Float32, MutAnyOrigin], tip: Int, pip: Int, mcp: Int) -> Bool:
        return Self.distance(landmarks, tip, mcp) > Self.distance(landmarks, pip, mcp) * 1.25

    def measure(self, landmarks: Pointer[mut=True, Float32, MutAnyOrigin]) -> Measurements:
        var palm_scale = max(0.000001, Self.palm_scale(landmarks))
        var index_pinch = Self.distance(landmarks, 4, 8) / palm_scale
        var middle_pinch = Self.distance(landmarks, 4, 12) / palm_scale
        var palm_x = (Self.coord(landmarks, 0, 0) + Self.coord(landmarks, 5, 0) + Self.coord(landmarks, 9, 0) + Self.coord(landmarks, 13, 0) + Self.coord(landmarks, 17, 0)) / 5.0
        var palm_y = (Self.coord(landmarks, 0, 1) + Self.coord(landmarks, 5, 1) + Self.coord(landmarks, 9, 1) + Self.coord(landmarks, 13, 1) + Self.coord(landmarks, 17, 1)) / 5.0
        var index_x = Self.coord(landmarks, 8, 0)
        var index_y = Self.coord(landmarks, 8, 1)
        var index_extended = Self.finger_extended(landmarks, 8, 6, 5)
        var middle_extended = Self.finger_extended(landmarks, 12, 10, 9)
        var ring_extended = Self.finger_extended(landmarks, 16, 14, 13)
        var pinky_extended = Self.finger_extended(landmarks, 20, 18, 17)
        var scroll_pose = index_extended and middle_extended and not ring_extended and not pinky_extended and index_pinch > self.config.pinch_release_threshold and middle_pinch > self.config.pinch_release_threshold
        var open_palm = index_extended and middle_extended and ring_extended and pinky_extended
        return Measurements(index_pinch, middle_pinch, palm_x, palm_y, index_x, index_y, scroll_pose, open_palm)

    @staticmethod
    def alpha(cutoff: Float64, dt: Float64) -> Float64:
        var tau = 1.0 / (6.283185307179586 * max(cutoff, 0.000001))
        return 1.0 / (1.0 + tau / max(dt, 0.000001))

    def filter_point(mut self, x: Float64, y: Float64, timestamp_ms: Int64) -> FilteredPoint:
        var timestamp_s = Float64(timestamp_ms) / 1000.0
        if not self.filter_initialized:
            self.filter_initialized = True
            self.filter_last_x = x
            self.filter_last_y = y
            self.filter_last_time = timestamp_s
            self.filter_x = x
            self.filter_y = y
            return FilteredPoint(x, y)
        if timestamp_s <= self.filter_last_time:
            return FilteredPoint(self.filter_x, self.filter_y)
        var dt = max(timestamp_s - self.filter_last_time, 0.0001)
        var raw_dx = (x - self.filter_last_x) / dt
        var raw_dy = (y - self.filter_last_y) / dt
        if not self.derivative_initialized:
            self.filter_dx = raw_dx
            self.filter_dy = raw_dy
            self.derivative_initialized = True
        else:
            var derivative_alpha = Self.alpha(self.config.filter_derivative_cutoff, dt)
            self.filter_dx = derivative_alpha * raw_dx + (1.0 - derivative_alpha) * self.filter_dx
            self.filter_dy = derivative_alpha * raw_dy + (1.0 - derivative_alpha) * self.filter_dy
        var x_alpha = Self.alpha(self.config.filter_min_cutoff + self.config.filter_beta * abs(self.filter_dx), dt)
        var y_alpha = Self.alpha(self.config.filter_min_cutoff + self.config.filter_beta * abs(self.filter_dy), dt)
        self.filter_x = x_alpha * x + (1.0 - x_alpha) * self.filter_x
        self.filter_y = y_alpha * y + (1.0 - y_alpha) * self.filter_y
        self.filter_last_x = x
        self.filter_last_y = y
        self.filter_last_time = timestamp_s
        return FilteredPoint(self.filter_x, self.filter_y)

    def pointer(mut self, measurements: Measurements, timestamp_ms: Int64) -> MojoAction:
        var filtered = self.filter_point(measurements.index_x, measurements.index_y, timestamp_ms)
        var now_x = (filtered.x - self.config.active_left) / max(0.000001, 1.0 - self.config.active_left - self.config.active_right)
        var now_y = (filtered.y - self.config.active_top) / max(0.000001, 1.0 - self.config.active_top - self.config.active_bottom)
        if self.config.mirror != 0:
            now_x = 1.0 - now_x
        var gain = max(0.1, self.config.pointer_gain)
        now_x = 0.5 + (now_x - 0.5) * gain
        now_y = 0.5 + (now_y - 0.5) * gain
        now_x = min(1.0, max(0.0, now_x))
        now_y = min(1.0, max(0.0, now_y))
        var out_x = self.config.screen_x + now_x * max(1.0, self.config.screen_width - 1.0)
        var out_y = self.config.screen_y + now_y * max(1.0, self.config.screen_height - 1.0)
        var quiet = self.last_x >= 0.0 and sqrt((filtered.x - self.last_x) * (filtered.x - self.last_x) + (filtered.y - self.last_y) * (filtered.y - self.last_y)) <= self.config.dead_zone
        if not quiet:
            self.last_x = filtered.x
            self.last_y = filtered.y
            return Self.result(ACTION_MOVE, out_x, out_y, 0, self.state)
        return Self.result(ACTION_NONE, out_x, out_y, 0, self.state)

    def process(mut self, landmarks: Pointer[mut=True, Float32, MutAnyOrigin], timestamp_ms: Int64, hand_selected: Int32, confidence: Float64) -> MojoAction:
        var valid = hand_selected != 0 and confidence == confidence and confidence >= 0.0 and confidence <= 1.0 and confidence >= self.config.handedness_confidence
        if valid:
            valid = Self.valid_landmarks(landmarks)
        if not valid:
            if self.invalid_since_ms < 0:
                self.reset_transient()
                self.invalid_since_ms = timestamp_ms
            if timestamp_ms - self.invalid_since_ms >= self.config.hand_loss_timeout_ms:
                self.active_hand = 0
                return self.reset_internal()
            return Self.result(ACTION_NONE, 0.0, 0.0, 0, self.state)

        if self.active_hand != 0 and self.active_hand != hand_selected:
            var button = self.held
            self.held = 0
            self.reset_transient()
            self.active_hand = hand_selected
            self.state = STATE_ARMED if self.armed else STATE_PAUSED
            if button != 0:
                return Self.result_after(ACTION_BUTTON_UP, 0.0, 0.0, button, self.state)
            return Self.result(ACTION_NONE, 0.0, 0.0, 0, self.state)
        self.active_hand = hand_selected
        self.invalid_since_ms = -1
        if not self.initialized:
            self.reacquire_since_ms = timestamp_ms
            self.initialized = True
        var measurements = self.measure(landmarks)
        if self.config.activation_gesture != 0 and measurements.open_palm:
            if self.open_since_ms < 0:
                self.open_since_ms = timestamp_ms
            elif timestamp_ms - self.open_since_ms >= self.config.activation_gesture_ms and timestamp_ms - self.last_toggle_ms >= self.config.activation_cooldown_ms:
                var button = self.held
                self.last_toggle_ms = timestamp_ms
                self.open_since_ms = -1
                self.armed = not self.armed
                self.held = 0
                self.reset_transient()
                if button != 0 and not self.armed:
                    self.state = STATE_PAUSED
                    return Self.result_after(ACTION_BUTTON_UP, 0.0, 0.0, button, self.state)
                self.state = STATE_ARMED if self.armed else STATE_PAUSED
                return Self.result(ACTION_NONE, 0.0, 0.0, 0, self.state)
        else:
            self.open_since_ms = -1

        if not self.armed or timestamp_ms - self.reacquire_since_ms < self.config.reacquisition_ms:
            if not self.armed:
                self.state = STATE_PAUSED
            elif self.held == 1:
                self.state = STATE_LEFT_DOWN
            elif self.held == 2:
                self.state = STATE_RIGHT_DOWN
            else:
                self.state = STATE_ARMED
            return Self.result(ACTION_NONE, 0.0, 0.0, 0, self.state)

        var left_pressed = measurements.index_pinch <= self.config.pinch_down_threshold
        var right_pressed = measurements.middle_pinch <= self.config.pinch_down_threshold
        if self.held != 0:
            var still_pressed = (self.held == 1 and measurements.index_pinch <= self.config.pinch_release_threshold) or (self.held == 2 and measurements.middle_pinch <= self.config.pinch_release_threshold)
            if not still_pressed:
                if self.release_since_ms < 0:
                    self.release_since_ms = timestamp_ms
                if self.config.release_debounce_ms <= 0 or timestamp_ms - self.release_since_ms >= self.config.release_debounce_ms:
                    var button = self.held
                    self.held = 0
                    self.reset_transient()
                    self.state = STATE_ARMED
                    return Self.result_after(ACTION_BUTTON_UP, 0.0, 0.0, button, self.state)
            else:
                self.release_since_ms = -1
            var pointer = self.pointer(measurements, timestamp_ms)
            self.state = STATE_LEFT_DOWN if self.held == 1 else STATE_RIGHT_DOWN
            pointer.button = self.held
            pointer.state = self.state
            return pointer^

        if right_pressed:
            if self.down_candidate != 2:
                self.down_candidate = 2
                self.down_since_ms = timestamp_ms
            if self.config.debounce_ms <= 0 or timestamp_ms - self.down_since_ms >= self.config.debounce_ms:
                self.held = 2
                self.down_candidate = 0
                self.state = STATE_RIGHT_DOWN
                return Self.result(ACTION_BUTTON_DOWN, 0.0, 0.0, 2, self.state)
            var pointer = self.pointer(measurements, timestamp_ms)
            pointer.state = STATE_ARMED
            return pointer^
        if left_pressed and not right_pressed:
            if self.down_candidate != 1:
                self.down_candidate = 1
                self.down_since_ms = timestamp_ms
            if self.config.debounce_ms <= 0 or timestamp_ms - self.down_since_ms >= self.config.debounce_ms:
                self.held = 1
                self.down_candidate = 0
                self.state = STATE_LEFT_DOWN
                return Self.result(ACTION_BUTTON_DOWN, 0.0, 0.0, 1, self.state)
            var pointer = self.pointer(measurements, timestamp_ms)
            pointer.state = STATE_ARMED
            return pointer^

        if measurements.scroll_pose:
            if self.scroll_entry_since_ms < 0:
                self.scroll_entry_since_ms = timestamp_ms
            if timestamp_ms - self.scroll_entry_since_ms >= self.config.scroll_entry_ms:
                if not self.scroll_active:
                    self.scroll_active = True
                    self.last_palm_y = measurements.palm_y
                    self.last_x = -1.0
                    self.last_y = -1.0
                    self.filter_initialized = False
                    self.derivative_initialized = False
                    self.state = STATE_SCROLL
                    return Self.result(ACTION_NONE, 0.0, 0.0, 0, self.state)
                var dy = measurements.palm_y - self.last_palm_y
                if abs(dy) <= self.config.scroll_dead_zone:
                    self.state = STATE_SCROLL
                    return Self.result(ACTION_NONE, 0.0, 0.0, 0, self.state)
                var direction = 1.0 if dy > 0.0 else -1.0
                var effective_dy = dy - direction * self.config.scroll_dead_zone
                self.last_palm_y = measurements.palm_y - direction * self.config.scroll_dead_zone
                self.scroll_remainder += -effective_dy * self.config.scroll_sensitivity * Float64(self.config.scroll_direction)
                var steps = Int32(self.scroll_remainder)
                if steps != 0:
                    self.scroll_remainder -= Float64(steps)
                    self.state = STATE_SCROLL
                    return Self.result(ACTION_SCROLL, 0.0, Float64(steps), 0, self.state)
                self.state = STATE_SCROLL
                return Self.result(ACTION_NONE, 0.0, 0.0, 0, self.state)
        else:
            self.scroll_entry_since_ms = -2
            self.scroll_remainder = 0.0
            if self.scroll_active:
                self.scroll_active = False
                self.last_x = -1.0
                self.last_y = -1.0
                self.filter_initialized = False
                self.derivative_initialized = False
                self.state = STATE_ARMED
                var pointer = self.pointer(measurements, timestamp_ms)
                return pointer^

        self.down_candidate = 0
        self.down_since_ms = 0
        self.state = STATE_ARMED
        var pointer = self.pointer(measurements, timestamp_ms)
        pointer.state = self.state
        return pointer^

    @staticmethod
    def result(action: Int32, x: Float64, y: Float64, button: Int32, state: Int32) -> MojoAction:
        return MojoAction(action, state, button, 0, x, y)

    @staticmethod
    def result_after(action: Int32, x: Float64, y: Float64, button: Int32, state: Int32) -> MojoAction:
        return MojoAction(action, state, button, 1, x, y)


@export("mgesture_mojo_abi_version")
def mgesture_mojo_abi_version() abi("C") -> Int32:
    return MGESTURE_MOJO_ABI_VERSION


@export("mgesture_mojo_config_size")
def mgesture_mojo_config_size() abi("C") -> Int64:
    return Int64(size_of[MojoConfig]())


@export("mgesture_mojo_config_alignment")
def mgesture_mojo_config_alignment() abi("C") -> Int64:
    return Int64(align_of[MojoConfig]())


@export("mgesture_mojo_action_size")
def mgesture_mojo_action_size() abi("C") -> Int64:
    return Int64(size_of[MojoAction]())


@export("mgesture_mojo_action_alignment")
def mgesture_mojo_action_alignment() abi("C") -> Int64:
    return Int64(align_of[MojoAction]())


@export("mgesture_mojo_engine_size")
def mgesture_mojo_engine_size() abi("C") -> Int64:
    return Int64(size_of[GestureEngine]())


@export("mgesture_mojo_engine_alignment")
def mgesture_mojo_engine_alignment() abi("C") -> Int64:
    return Int64(align_of[GestureEngine]())


@export("mgesture_mojo_engine_init")
def mgesture_mojo_engine_init(
    engine: Pointer[mut=True, GestureEngine, MutAnyOrigin],
    config: Pointer[mut=False, MojoConfig, ImmutAnyOrigin],
    armed: Int32,
) abi("C") -> Int32:
    engine[].initialize(config[], armed)
    return 0


@export("mgesture_mojo_engine_reset")
def mgesture_mojo_engine_reset(
    engine: Pointer[mut=True, GestureEngine, MutAnyOrigin],
    output: Pointer[mut=True, MojoAction, MutAnyOrigin],
) abi("C") -> Int32:
    output[] = engine[].reset_internal()
    return 0


@export("mgesture_mojo_engine_set_armed")
def mgesture_mojo_engine_set_armed(
    engine: Pointer[mut=True, GestureEngine, MutAnyOrigin],
    armed: Int32,
    output: Pointer[mut=True, MojoAction, MutAnyOrigin],
) abi("C") -> Int32:
    output[] = engine[].set_armed_internal(armed)
    return 0


@export("mgesture_mojo_engine_process")
def mgesture_mojo_engine_process(
    engine: Pointer[mut=True, GestureEngine, MutAnyOrigin],
    landmarks: Pointer[mut=True, Float32, MutAnyOrigin],
    timestamp_ms: Int64,
    hand_selected: Int32,
    confidence: Float64,
    output: Pointer[mut=True, MojoAction, MutAnyOrigin],
) abi("C") -> Int32:
    output[] = engine[].process(landmarks, timestamp_ms, hand_selected, confidence)
    return 0


@export("mgesture_mojo_engine_destroy")
def mgesture_mojo_engine_destroy(
    engine: Pointer[mut=True, GestureEngine, MutAnyOrigin],
) abi("C") -> Int32:
    _ = engine[].reset_internal()
    return 0
