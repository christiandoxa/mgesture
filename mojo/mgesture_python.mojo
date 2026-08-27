from std.memory import Pointer
from std.os import abort
from std.python import Python, PythonObject
from std.python.bindings import PythonModuleBuilder

from mgesture_core import GestureEngine, MojoAction, MojoConfig


def action_name(action: Int32) -> String:
    if action == 1:
        return "move_absolute"
    if action == 2:
        return "button_down"
    if action == 3:
        return "button_up"
    if action == 4:
        return "scroll"
    return "none"


def state_name(state: Int32) -> String:
    if state == 1:
        return "ARMED"
    if state == 2:
        return "LEFT DOWN"
    if state == 3:
        return "RIGHT DOWN"
    if state == 4:
        return "SCROLL"
    return "PAUSED"


struct PythonGestureEngine(Movable, Writable):
    var engine: GestureEngine

    def __init__(out self, engine: GestureEngine):
        self.engine = engine.copy()

    @staticmethod
    def py_init(out self: PythonGestureEngine, args: PythonObject, kwargs: PythonObject) raises:
        _ = kwargs
        if len(args) != 1:
            raise Error("PythonGestureEngine(config) expects one dictionary")
        var config = args[0]
        var native_config = MojoConfig(
            Float64(py=config.get("screen_x", PythonObject(0.0))),
            Float64(py=config.get("screen_y", PythonObject(0.0))),
            Float64(py=config.get("screen_width", PythonObject(1920.0))),
            Float64(py=config.get("screen_height", PythonObject(1080.0))),
            Int32(py=config.get("mirror", PythonObject(1))),
            Float64(py=config.get("handedness_confidence", PythonObject(0.70))),
            Float64(py=config.get("active_left", PythonObject(0.10))),
            Float64(py=config.get("active_right", PythonObject(0.10))),
            Float64(py=config.get("active_top", PythonObject(0.10))),
            Float64(py=config.get("active_bottom", PythonObject(0.10))),
            Float64(py=config.get("pointer_gain", PythonObject(1.0))),
            Float64(py=config.get("pointer_acceleration", PythonObject(0.0))),
            Float64(py=config.get("dead_zone", PythonObject(0.002))),
            Float64(py=config.get("filter_min_cutoff", PythonObject(1.0))),
            Float64(py=config.get("filter_beta", PythonObject(0.007))),
            Float64(py=config.get("filter_derivative_cutoff", PythonObject(1.0))),
            Float64(py=config.get("pinch_down_threshold", PythonObject(0.45))),
            Float64(py=config.get("pinch_release_threshold", PythonObject(0.60))),
            Int64(py=config.get("debounce_ms", PythonObject(70))),
            Int64(py=config.get("release_debounce_ms", PythonObject(35))),
            Int64(py=config.get("hand_loss_timeout_ms", PythonObject(250))),
            Int64(py=config.get("reacquisition_ms", PythonObject(150))),
            Int64(py=config.get("scroll_entry_ms", PythonObject(180))),
            Int64(py=config.get("scroll_exit_grace_ms", PythonObject(120))),
            Float64(py=config.get("scroll_sensitivity", PythonObject(35.0))),
            Int32(py=config.get("scroll_direction", PythonObject(1))),
            Float64(py=config.get("scroll_dead_zone", PythonObject(0.001))),
            Int32(py=config.get("activation_gesture", PythonObject(1))),
            Int64(py=config.get("activation_gesture_ms", PythonObject(1000))),
            Int64(py=config.get("activation_cooldown_ms", PythonObject(1000))),
        )
        var armed = Int32(py=config.get("armed", PythonObject(0)))
        self = Self(GestureEngine.create(native_config, armed))

    @staticmethod
    def process(
        self_ptr: Pointer[mut=True, PythonGestureEngine, MutAnyOrigin],
        landmarks: PythonObject,
        timestamp_ms: PythonObject,
        hand_selected: PythonObject,
        confidence: PythonObject,
    ) raises -> PythonObject:
        var values: InlineArray[Float32, 63] = InlineArray[Float32, 63](uninitialized=True)
        for i in range(63):
            values[i] = Float32(py=landmarks[i])
        var pointer = Pointer(to=values[0]).unsafe_origin_cast[MutAnyOrigin]()
        var action = self_ptr[].engine.process(
            pointer,
            Int64(py=timestamp_ms),
            Int32(py=hand_selected),
            Float64(py=confidence),
        )
        return Self.python_result(action)

    @staticmethod
    def reset(
        self_ptr: Pointer[mut=True, PythonGestureEngine, MutAnyOrigin], reason: PythonObject
    ) raises -> PythonObject:
        _ = reason
        return Self.python_result(self_ptr[].engine.reset_internal())

    @staticmethod
    def set_armed(
        self_ptr: Pointer[mut=True, PythonGestureEngine, MutAnyOrigin], value: PythonObject
    ) raises -> PythonObject:
        return Self.python_result(self_ptr[].engine.set_armed_internal(Int32(py=value)))

    @staticmethod
    def python_result(action: MojoAction) raises -> PythonObject:
        var button = action.button
        return Python.dict(
            action=PythonObject(action_name(action.action)),
            x=PythonObject(action.x),
            y=PythonObject(action.y),
            button=PythonObject(button),
            state=PythonObject(state_name(action.state)),
            state_order=PythonObject(action.state_order),
        )


@export
def PyInit_mgesture_python() abi("C") -> PythonObject:
    try:
        var module = PythonModuleBuilder("mgesture_python")
        _ = module.add_type[PythonGestureEngine]("PythonGestureEngine").def_py_init[PythonGestureEngine.py_init]().def_method[PythonGestureEngine.process]("process").def_method[PythonGestureEngine.reset]("reset").def_method[PythonGestureEngine.set_armed]("set_armed")
        return module.finalize()
    except e:
        abort(String("failed to initialize mgesture_python: ", e))
