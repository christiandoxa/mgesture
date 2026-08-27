# Gestures

MediaPipe hand landmark numbering uses wrist `0`, thumb tip `4`, index MCP/tip `5/8`, middle MCP/tip `9/12`, ring MCP/tip `13/16`, and pinky MCP/tip `17/20`.

Priority is deterministic:

1. invalid hand/hand-loss cleanup and pause;
2. maintain an already held left or right button until release;
3. new right pinch;
4. new left pinch when right pinch is not active;
5. stable scroll pose;
6. normal pointer movement.

Pinch distance is divided by a palm-scale average of wrist-to-middle-MCP and index-MCP-to-pinky-MCP distances, so hand size does not change the gesture. Down and release thresholds are separate, and each transition is time-debounced. A held pinch emits one button-down and one button-up only; moving while held is a drag. Two quick cycles are deliberately left for the OS to recognize as a double click.

Left and right selections use the same landmark indices and gesture mapping; physical handedness only chooses which detected hand supplies the frame.

Pointer mapping mirrors X by default, maps the inner active region to the selected monitor/virtual desktop, clamps coordinates, filters with an FPS-aware One Euro filter, and suppresses the first reacquisition interval.

Scroll uses palm-normalized index/middle reach and straightness, relaxed (not clearly extended) ring/pinky fingers, and a thumb that is not in a pinch-down state. Entry is delayed for stability; active scroll tolerates brief finger or landmark dropouts before exiting. Palm displacement uses a dead-zone anchor and accumulates fractional wheel steps. Buttons suppress scrolling. The diagnostic observation path reports each finger score, pose readiness, entry progress, active state, delta, remainder, and block reason.

The app begins paused. The configured global shortcut toggles pause/resume; Space toggles through the preview as a fallback, and the optional open-palm hold gesture uses a cooldown. The selected physical hand stays locked while both hands are visible; a stable hand switch resets the gesture engine and releases any held button before the replacement hand can act. Right pinch wins an ambiguous new pinch frame; held buttons never switch sides. Nonfinite, out-of-bounds, or degenerate landmarks are treated as hand loss: no click or scroll is emitted, the pointer filter resets on reacquisition, and held buttons are released after the configured timeout.
