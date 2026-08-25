from std.math import max, min, sqrt
from std.os import abort
from std.python import Python, PythonObject
from std.python.bindings import PythonModuleBuilder


@fieldwise_init
struct PythonGestureEngine(Movable, Writable):
    var screen_x: Float64
    var screen_y: Float64
    var screen_width: Float64
    var screen_height: Float64
    var mirror: Bool
    var armed: Bool
    var handedness_confidence: Float64
    var pinch_down_threshold: Float64
    var pinch_release_threshold: Float64
    var debounce_ms: Int64
    var release_debounce_ms: Int64
    var hand_loss_timeout_ms: Int64
    var reacquisition_ms: Int64
    var active_left: Float64
    var active_right: Float64
    var active_top: Float64
    var active_bottom: Float64
    var pointer_gain: Float64
    var dead_zone: Float64
    var scroll_entry_ms: Int64
    var scroll_sensitivity: Float64
    var scroll_direction: Int64
    var scroll_dead_zone: Float64
    var activation_gesture: Bool
    var activation_gesture_ms: Int64
    var activation_cooldown_ms: Int64
    var held: Int
    var down_candidate: Int
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

    @staticmethod
    def py_init(out self: PythonGestureEngine, args: PythonObject, kwargs: PythonObject) raises:
        _ = kwargs
        if len(args) != 1:
            raise Error("PythonGestureEngine(config) expects one dictionary")
        var config = args[0]
        var screen_x = Float64(py=config.get("screen_x"))
        var screen_y = Float64(py=config.get("screen_y"))
        var screen_width = Float64(py=config.get("screen_width"))
        var screen_height = Float64(py=config.get("screen_height"))
        var mirror = Bool(py=config.get("mirror", PythonObject(True)))
        var armed = Bool(py=config.get("armed", PythonObject(False)))
        var handedness_confidence = Float64(py=config.get("handedness_confidence", PythonObject(0.70)))
        var pinch_down_threshold = Float64(py=config.get("pinch_down_threshold", PythonObject(0.45)))
        var pinch_release_threshold = Float64(py=config.get("pinch_release_threshold", PythonObject(0.60)))
        var debounce_ms = Int64(py=config.get("debounce_ms", PythonObject(70)))
        var release_debounce_ms = Int64(py=config.get("release_debounce_ms", PythonObject(35)))
        var hand_loss_timeout_ms = Int64(py=config.get("hand_loss_timeout_ms", PythonObject(250)))
        var reacquisition_ms = Int64(py=config.get("reacquisition_ms", PythonObject(150)))
        var active_left = Float64(py=config.get("active_left", PythonObject(0.10)))
        var active_right = Float64(py=config.get("active_right", PythonObject(0.10)))
        var active_top = Float64(py=config.get("active_top", PythonObject(0.10)))
        var active_bottom = Float64(py=config.get("active_bottom", PythonObject(0.10)))
        var pointer_gain = Float64(py=config.get("pointer_gain", PythonObject(1.0)))
        var dead_zone = Float64(py=config.get("dead_zone", PythonObject(0.002)))
        var scroll_entry_ms = Int64(py=config.get("scroll_entry_ms", PythonObject(180)))
        var scroll_sensitivity = Float64(py=config.get("scroll_sensitivity", PythonObject(35.0)))
        var scroll_direction = Int64(py=config.get("scroll_direction", PythonObject(1)))
        var scroll_dead_zone = Float64(py=config.get("scroll_dead_zone", PythonObject(0.001)))
        var activation_gesture = Bool(py=config.get("activation_gesture", PythonObject(True)))
        var activation_gesture_ms = Int64(py=config.get("activation_gesture_ms", PythonObject(1000)))
        var activation_cooldown_ms = Int64(py=config.get("activation_cooldown_ms", PythonObject(1000)))
        self = Self(screen_x, screen_y, screen_width, screen_height, mirror, armed, handedness_confidence, pinch_down_threshold, pinch_release_threshold, debounce_ms, release_debounce_ms, hand_loss_timeout_ms, reacquisition_ms, active_left, active_right, active_top, active_bottom, pointer_gain, dead_zone, scroll_entry_ms, scroll_sensitivity, scroll_direction, scroll_dead_zone, activation_gesture, activation_gesture_ms, activation_cooldown_ms, 0, 0, 0, 0, -1, 0, -1.0, -1.0, 0.0, 0.0, False, -2, -1, 0, False)

    @staticmethod
    def process(
        self_ptr: Pointer[mut=True, PythonGestureEngine, MutAnyOrigin],
        landmarks: PythonObject,
        timestamp_ms: PythonObject,
        right_hand: PythonObject,
        confidence: PythonObject,
    ) raises -> PythonObject:
        return self_ptr[].process_internal(landmarks, timestamp_ms, right_hand, confidence)

    def process_internal(
        mut self,
        landmarks: PythonObject,
        timestamp_ms: PythonObject,
        right_hand: PythonObject,
        confidence: PythonObject,
    ) raises -> PythonObject:
        var now = Int64(py=timestamp_ms)
        var is_right = Bool(py=right_hand)
        var score = Float64(py=confidence)
        if not is_right or score < self.handedness_confidence:
            if self.invalid_since_ms < 0:
                self.invalid_since_ms = now
            if self.held != 0 and now - self.invalid_since_ms >= self.hand_loss_timeout_ms:
                var button = self.held
                self.held = 0
                self.release_since_ms = 0
                return Self.result("button_up", 0.0, 0.0, button, "ARMED")
            return Self.result("none", 0.0, 0.0, 0, "PAUSED" if not self.armed else "ARMED")

        self.invalid_since_ms = -1
        if not self.initialized:
            self.reacquire_since_ms = now
            self.initialized = True
        var palm_scale = max(0.000001, 0.5 * (Self.distance(landmarks, 0, 9) + Self.distance(landmarks, 5, 17)))
        var index_pinch = Self.distance(landmarks, 4, 8) / palm_scale
        var middle_pinch = Self.distance(landmarks, 4, 12) / palm_scale
        var palm_y = (Self.coord(landmarks, 0, 1) + Self.coord(landmarks, 5, 1) + Self.coord(landmarks, 9, 1) + Self.coord(landmarks, 13, 1) + Self.coord(landmarks, 17, 1)) / 5.0
        var open_palm = Self.finger_extended(landmarks, 8, 6, 5) and Self.finger_extended(landmarks, 12, 10, 9) and Self.finger_extended(landmarks, 16, 14, 13) and Self.finger_extended(landmarks, 20, 18, 17)
        var scroll_pose = Self.finger_extended(landmarks, 8, 6, 5) and Self.finger_extended(landmarks, 12, 10, 9) and not Self.finger_extended(landmarks, 16, 14, 13) and not Self.finger_extended(landmarks, 20, 18, 17) and middle_pinch > self.pinch_release_threshold
        var index_x = Self.coord(landmarks, 8, 0)
        var index_y = Self.coord(landmarks, 8, 1)
        var now_x = (index_x - self.active_left) / max(0.000001, 1.0 - self.active_left - self.active_right)
        var now_y = (index_y - self.active_top) / max(0.000001, 1.0 - self.active_top - self.active_bottom)
        if self.mirror:
            now_x = 1.0 - now_x
        now_x = 0.5 + (now_x - 0.5) * self.pointer_gain
        now_y = 0.5 + (now_y - 0.5) * self.pointer_gain
        now_x = min(1.0, max(0.0, now_x))
        now_y = min(1.0, max(0.0, now_y))
        var out_x = self.screen_x + now_x * max(1.0, self.screen_width - 1.0)
        var out_y = self.screen_y + now_y * max(1.0, self.screen_height - 1.0)
        if now - self.reacquire_since_ms < self.reacquisition_ms:
            return Self.result("none", out_x, out_y, 0, "ARMED" if self.armed else "PAUSED")
        var pointer_quiet = self.last_x >= 0.0 and sqrt((now_x - self.last_x) * (now_x - self.last_x) + (now_y - self.last_y) * (now_y - self.last_y)) < self.dead_zone
        if not pointer_quiet:
            self.last_x = now_x
            self.last_y = now_y
        if self.activation_gesture:
            if open_palm:
                if self.open_since_ms < 0:
                    self.open_since_ms = now
                elif now - self.open_since_ms >= self.activation_gesture_ms and now - self.last_toggle_ms >= self.activation_cooldown_ms:
                    var button = self.held
                    self.last_toggle_ms = now
                    self.open_since_ms = -1
                    self.armed = not self.armed
                    self.held = 0
                    self.last_x = -1.0
                    self.last_y = -1.0
                    if button != 0 and not self.armed:
                        return Self.result("button_up", out_x, out_y, button, "PAUSED")
                    return Self.result("none", out_x, out_y, 0, "ARMED" if self.armed else "PAUSED")
            else:
                self.open_since_ms = -1
        if not self.armed:
            return Self.result("none", out_x, out_y, 0, "PAUSED")

        var left_pressed = index_pinch <= self.pinch_down_threshold
        var right_pressed = middle_pinch <= self.pinch_down_threshold
        if self.held != 0:
            var still_pressed = (self.held == 1 and index_pinch <= self.pinch_release_threshold) or (self.held == 2 and middle_pinch <= self.pinch_release_threshold)
            if not still_pressed:
                if self.release_since_ms == 0:
                    self.release_since_ms = now
                if now - self.release_since_ms >= self.release_debounce_ms:
                    var button = self.held
                    self.held = 0
                    self.release_since_ms = 0
                    return Self.result("button_up", out_x, out_y, button, "ARMED")
            else:
                self.release_since_ms = 0
                return Self.result("none" if pointer_quiet else "move_absolute", out_x, out_y, self.held, "LEFT DOWN" if self.held == 1 else "RIGHT DOWN")
            return Self.result("none" if pointer_quiet else "move_absolute", out_x, out_y, self.held, "LEFT DOWN" if self.held == 1 else "RIGHT DOWN")

        if scroll_pose and not right_pressed and not left_pressed:
            if self.scroll_entry_since_ms < 0:
                self.scroll_entry_since_ms = now
            if now - self.scroll_entry_since_ms >= self.scroll_entry_ms:
                if not self.scroll_active:
                    self.scroll_active = True
                    self.last_palm_y = palm_y
                    return Self.result("none", out_x, out_y, 0, "SCROLL")
                var dy = palm_y - self.last_palm_y
                self.last_palm_y = palm_y
                if abs(dy) >= self.scroll_dead_zone:
                    self.scroll_remainder += -dy * self.scroll_sensitivity * Float64(self.scroll_direction)
                    var steps = Int(self.scroll_remainder)
                    if steps != 0:
                        self.scroll_remainder -= Float64(steps)
                        return Self.result("scroll", 0.0, Float64(steps), 0, "SCROLL")
                return Self.result("none", out_x, out_y, 0, "SCROLL")
        else:
            self.scroll_entry_since_ms = -2
            self.scroll_remainder = 0.0
            if self.scroll_active:
                self.scroll_active = False
                return Self.result("move_absolute", out_x, out_y, 0, "ARMED")

        if right_pressed:
            if self.down_candidate != 2:
                self.down_candidate = 2
                self.down_since_ms = now
            if now - self.down_since_ms >= self.debounce_ms:
                self.held = 2
                self.down_candidate = 0
                return Self.result("button_down", out_x, out_y, 2, "RIGHT DOWN")
            return Self.result("move_absolute", out_x, out_y, 0, "ARMED")
        if left_pressed:
            if self.down_candidate != 1:
                self.down_candidate = 1
                self.down_since_ms = now
            if now - self.down_since_ms >= self.debounce_ms:
                self.held = 1
                self.down_candidate = 0
                return Self.result("button_down", out_x, out_y, 1, "LEFT DOWN")
            return Self.result("move_absolute", out_x, out_y, 0, "ARMED")
        self.down_candidate = 0
        self.scroll_active = False
        return Self.result("none" if pointer_quiet else "move_absolute", out_x, out_y, 0, "ARMED")

    @staticmethod
    def reset(self_ptr: Pointer[mut=True, PythonGestureEngine, MutAnyOrigin], reason: PythonObject) raises -> PythonObject:
        return self_ptr[].reset_internal(reason)

    def reset_internal(mut self, reason: PythonObject) raises -> PythonObject:
        _ = reason
        var button = self.held
        self.held = 0
        self.down_candidate = 0
        self.release_since_ms = 0
        self.invalid_since_ms = -1
        self.reacquire_since_ms = 0
        self.last_x = -1.0
        self.last_y = -1.0
        self.scroll_active = False
        self.scroll_entry_since_ms = -2
        self.scroll_remainder = 0.0
        self.open_since_ms = -1
        self.initialized = False
        if button != 0:
            return Self.result("button_up", 0.0, 0.0, button, "ARMED" if self.armed else "PAUSED")
        return Self.result("none", 0.0, 0.0, 0, "ARMED" if self.armed else "PAUSED")

    @staticmethod
    def set_armed(self_ptr: Pointer[mut=True, PythonGestureEngine, MutAnyOrigin], value: PythonObject) raises -> PythonObject:
        return self_ptr[].set_armed_internal(value)

    def set_armed_internal(mut self, value: PythonObject) raises -> PythonObject:
        var button = self.held
        self.armed = Bool(py=value)
        self.held = 0
        self.down_candidate = 0
        self.last_x = -1.0
        self.last_y = -1.0
        self.scroll_active = False
        self.scroll_entry_since_ms = -2
        self.scroll_remainder = 0.0
        self.open_since_ms = -1
        self.initialized = False
        if button != 0 and not self.armed:
            return Self.result("button_up", 0.0, 0.0, button, "PAUSED")
        return Self.result("none", 0.0, 0.0, 0, "ARMED" if self.armed else "PAUSED")

    @staticmethod
    def coord(landmarks: PythonObject, point: Int, axis: Int) raises -> Float64:
        return Float64(py=landmarks[point * 3 + axis])

    @staticmethod
    def distance(landmarks: PythonObject, first: Int, second: Int) raises -> Float64:
        var dx = Self.coord(landmarks, first, 0) - Self.coord(landmarks, second, 0)
        var dy = Self.coord(landmarks, first, 1) - Self.coord(landmarks, second, 1)
        var dz = Self.coord(landmarks, first, 2) - Self.coord(landmarks, second, 2)
        return sqrt(dx * dx + dy * dy + dz * dz)

    @staticmethod
    def finger_extended(landmarks: PythonObject, tip: Int, pip: Int, mcp: Int) raises -> Bool:
        return Self.distance(landmarks, tip, mcp) > Self.distance(landmarks, pip, mcp) * 1.25


    @staticmethod
    def result(action: String, x: Float64, y: Float64, button: Int, state: String) raises -> PythonObject:
        return Python.dict(
            action=PythonObject(action),
            x=PythonObject(x),
            y=PythonObject(y),
            button=PythonObject(button),
            state=PythonObject(state),
        )


@export
def PyInit_mgesture_core() abi("C") -> PythonObject:
    try:
        var module = PythonModuleBuilder("mgesture_core")
        _ = module.add_type[PythonGestureEngine]("PythonGestureEngine").def_py_init[PythonGestureEngine.py_init]().def_method[PythonGestureEngine.process]("process").def_method[PythonGestureEngine.reset]("reset").def_method[PythonGestureEngine.set_armed]("set_armed")
        return module.finalize()
    except e:
        abort(String("failed to initialize mgesture_core: ", e))
