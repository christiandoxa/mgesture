from __future__ import annotations

import pytest

from mgesture.cli import _parser, main


def test_landmark_recording_requires_explicit_developer_flag() -> None:
    args = _parser().parse_args(["record-landmarks", "--output", "recording.jsonl"])
    assert args.developer is False

    with pytest.raises(SystemExit, match="developer-only"):
        main(["record-landmarks", "--output", "recording.jsonl"])
