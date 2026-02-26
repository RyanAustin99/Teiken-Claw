from pathlib import Path

import pytest

from app.control_plane.domain.errors import SingleInstanceError
from app.control_plane.infra.lock import SingleInstanceLock


def test_single_instance_lock_blocks_second_holder(tmp_path):
    lock_file = tmp_path / "run" / "control_plane.lock"
    lock_a = SingleInstanceLock(lock_file)
    lock_b = SingleInstanceLock(lock_file)

    lock_a.acquire()
    try:
        with pytest.raises(SingleInstanceError):
            lock_b.acquire()
    finally:
        lock_a.release()

