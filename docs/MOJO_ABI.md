# Native Mojo ABI

The standalone engine is generated from `mojo/mgesture_core.mojo` and exposed through a small C ABI. `MGESTURE_MOJO_ABI_VERSION` is `1`.

Exports:

- `mgesture_mojo_abi_version`
- `mgesture_mojo_config_size` / `mgesture_mojo_config_alignment`
- `mgesture_mojo_action_size` / `mgesture_mojo_action_alignment`
- `mgesture_mojo_engine_size` / `mgesture_mojo_engine_alignment`
- `mgesture_mojo_engine_init`
- `mgesture_mojo_engine_process`
- `mgesture_mojo_engine_reset`
- `mgesture_mojo_engine_set_armed`
- `mgesture_mojo_engine_destroy`

The ABI uses fixed-width integers, `Float64`, and pointers to fixed-layout `MojoConfig` and `MojoAction` records. The caller owns the aligned engine-state storage and landmark buffer; the Mojo engine owns persistent filter/gesture state; the caller owns the output record. The destroy operation resets state and does not free caller-owned storage. `MojoAction.state_order` is `0` when a state transition precedes the action and `1` when cleanup emits the action before the transition. No Mojo exceptions, strings, Python objects, callbacks, or per-frame allocations cross the ABI.

`mgesture_mojo_engine_process` receives selected-hand validity as `0` (none), `1` (physical right), or `2` (physical left); older callers using `0`/`1` retain their behavior. The Python boundary applies the configured hand selection before this call.

Native library names are `libmgesture_mojo.so`, `libmgesture_mojo.dylib`, and `mgesture_mojo.dll`. The loader rejects an ABI version, layout, export, or binary-architecture mismatch before selecting Mojo. `auto` falls back to Python if loading fails; explicit `mojo` fails clearly.
