# Gestures

MediaPipe hand landmark numbering uses wrist `0`, thumb tip `4`, index MCP/tip `5/8`, middle MCP/tip `9/12`, ring MCP/tip `13/16`, and pinky MCP/tip `17/20`.

Priority is deterministic:

1. invalid hand/hand-loss cleanup and pause;
2. maintain an already held left or right button until release;
3. new right pinch;
4. new left pinch when right pinch is not active;
5. stable scroll pose;
6. normal pointer movement.

Pinch distance is divided by a palm-scale average of wrist-to-middle-MCP and index-MCP-to-pinky-MCP distances. Down and release thresholds are separate. A held pinch emits one button-down and one button-up only. Two quick cycles are deliberately left for the OS to recognize as a double click.

Pointer mapping mirrors X by default, maps the inner active region to the selected monitor/virtual desktop, clamps coordinates, filters with an FPS-aware One Euro filter, and suppresses the first reacquisition interval.

Scroll uses index/middle extended, ring/pinky folded, no active thumb pinch. Entry is delayed for stability; palm displacement accumulates fractional wheel steps. Buttons suppress scrolling.

The app begins paused. Space toggles through the preview, and the optional open-palm hold gesture uses a cooldown. Any hand ambiguity or error is safe: no click or scroll is emitted, and held buttons are released after the configured timeout.
