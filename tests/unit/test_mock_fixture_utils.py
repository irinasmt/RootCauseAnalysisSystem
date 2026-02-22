import hashlib
from pathlib import Path


def fixture_bundle_path(root: Path, bundle_id: str) -> Path:
    return root / bundle_id


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_fixture_bundle_path_builds_expected_path(tmp_path: Path):
    bundle_path = fixture_bundle_path(tmp_path, "mock-abc123")
    assert bundle_path == tmp_path / "mock-abc123"


def test_file_sha256_is_stable(tmp_path: Path):
    file_path = tmp_path / "sample.log"
    file_path.write_bytes(b"hello\n")
    expected = hashlib.sha256(b"hello\n").hexdigest()
    assert file_sha256(file_path) == expected
