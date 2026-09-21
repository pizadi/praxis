"""Backup crypto unit tests (app/services/backup_crypto.py)."""

import os
from pathlib import Path

import pytest

from app.services.backup_crypto import (
    MAGIC,
    decrypt_file,
    encrypt_file,
    is_encrypted,
    sha256_file,
    sniff_and_decrypt,
)


@pytest.fixture
def artifact(tmp_path):
    src = tmp_path / "a.tar.gz"
    src.write_bytes(os.urandom(3 * 1024 * 1024 + 137))  # multi-chunk, unaligned
    return src


def test_sha256_file(artifact):
    import hashlib

    assert sha256_file(artifact) == hashlib.sha256(artifact.read_bytes()).hexdigest()


def test_is_encrypted(artifact):
    assert not is_encrypted(artifact)
    enc = artifact.with_suffix(".enc")
    encrypt_file(artifact, enc, "pw")
    assert is_encrypted(enc)
    assert enc.read_bytes()[: len(MAGIC)] == MAGIC


def test_encrypt_round_trip(artifact, tmp_path):
    enc = tmp_path / "a.enc"
    dec = tmp_path / "a.dec"
    encrypt_file(artifact, enc, "correct horse")
    # header (9) + salt (16) + nonce (12) + tag (16) = 53 bytes of overhead
    assert enc.stat().st_size == artifact.stat().st_size + 53
    decrypt_file(enc, dec, "correct horse")
    assert dec.read_bytes() == artifact.read_bytes()


def test_salt_and_nonce_are_fresh_per_archive(artifact, tmp_path):
    e1, e2 = tmp_path / "1.enc", tmp_path / "2.enc"
    encrypt_file(artifact, e1, "pw")
    encrypt_file(artifact, e2, "pw")
    assert e1.read_bytes() != e2.read_bytes()  # different salt/nonce → different ciphertext


def test_wrong_key_rejected(artifact, tmp_path):
    enc, dec = tmp_path / "a.enc", tmp_path / "a.dec"
    encrypt_file(artifact, enc, "right")
    with pytest.raises(ValueError, match="wrong key"):
        decrypt_file(enc, dec, "wrong")


def test_tampering_rejected(artifact, tmp_path):
    enc, dec = tmp_path / "a.enc", tmp_path / "a.dec"
    encrypt_file(artifact, enc, "pw")
    blob = bytearray(enc.read_bytes())
    blob[30] ^= 0xFF  # flip one ciphertext bit
    enc.write_bytes(blob)
    with pytest.raises(ValueError, match="corrupted"):
        decrypt_file(enc, dec, "pw")


def test_truncated_rejected(artifact, tmp_path):
    enc, dec = tmp_path / "a.enc", tmp_path / "a.dec"
    encrypt_file(artifact, enc, "pw")
    enc.write_bytes(enc.read_bytes()[:20])
    with pytest.raises(ValueError, match="truncated"):
        decrypt_file(enc, dec, "pw")


def test_sniff_and_decrypt_passthrough(artifact):
    plain, was = sniff_and_decrypt(str(artifact), None)
    assert plain == str(artifact) and was is False


def test_sniff_and_decrypt_encrypted(artifact, tmp_path):
    enc = tmp_path / "a.enc"
    encrypt_file(artifact, enc, "pw")
    plain, was = sniff_and_decrypt(str(enc), "pw")
    assert was is True
    assert Path(plain).read_bytes() == artifact.read_bytes()


def test_sniff_encrypted_without_key_raises(artifact, tmp_path):
    enc = tmp_path / "a.enc"
    encrypt_file(artifact, enc, "pw")
    with pytest.raises(ValueError, match="BACKUP_ENCRYPTION_KEY"):
        sniff_and_decrypt(str(enc), None)
