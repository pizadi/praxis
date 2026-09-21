"""Backup tarball encryption + SHA-256 checksums.

Encryption: AES-256-GCM with a key derived from the configured passphrase
(scrypt, per-archive random salt). Wire format of an encrypted artifact:

    b"PRAXISBK" | b"\\x01" | salt (16) | nonce (12) | ciphertext | tag (16)

The 9-byte magic doubles as GCM additional authenticated data (AAD), so
headers cannot be shuffled between files. A corrupted or tampered artifact
fails tag verification at the end of the stream (or on import).

Everything streams in 1 MiB chunks — never whole-archive in memory,
consistent with the rest of the backup subsystem.

Checksums: SHA-256 of the FINAL artifact (encrypted bytes when encryption
is on, else the raw tarball) — that is what survives the transfer and what
the admin can re-verify with `sha256sum`. Member-level hashes live inside
the manifest (schema_version 4, see backup_import._verify_member_hashes).
"""

from __future__ import annotations

import hashlib
import os

CHUNK = 1024 * 1024  # 1 MiB
MAGIC = b"PRAXISBK\x01"  # 9 bytes
_SALT_LEN = 16
_NONCE_LEN = 12
_TAG_LEN = 16
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1


def sha256_file(path: str | os.PathLike[str]) -> str:
    """Streaming SHA-256 of a file (hex digest)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def is_encrypted(path: str | os.PathLike[str]) -> bool:
    """True when the file starts with the backup-encryption magic."""
    with open(path, "rb") as f:
        return f.read(len(MAGIC)) == MAGIC


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

    kdf = Scrypt(salt=salt, length=32, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P)
    return kdf.derive(passphrase.encode("utf-8"))


def encrypt_file(src: str | os.PathLike[str], dst: str | os.PathLike[str], passphrase: str) -> None:
    """Encrypt `src` into `dst` (AES-256-GCM); both are paths, streamed."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    salt = os.urandom(_SALT_LEN)
    nonce = os.urandom(_NONCE_LEN)
    key = _derive_key(passphrase, salt)
    enc = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    enc.authenticate_additional_data(MAGIC)
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        fout.write(MAGIC)
        fout.write(salt)
        fout.write(nonce)
        while chunk := fin.read(CHUNK):
            fout.write(enc.update(chunk))
        enc.finalize()
        fout.write(enc.tag)  # 16-byte GCM tag (available after finalize)


def decrypt_file(src: str | os.PathLike[str], dst: str | os.PathLike[str], passphrase: str) -> None:
    """Decrypt an encrypted backup into `dst`; raises ValueError on a bad
    key, truncated file, or any tampering (GCM tag mismatch)."""
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    src = str(src)
    size = os.path.getsize(src)
    header = len(MAGIC) + _SALT_LEN + _NONCE_LEN
    if size < header + _TAG_LEN:
        raise ValueError("encrypted backup file is truncated")
    with open(src, "rb") as fin:
        magic = fin.read(len(MAGIC))
        if magic != MAGIC:
            raise ValueError("not an encrypted backup file")
        salt = fin.read(_SALT_LEN)
        nonce = fin.read(_NONCE_LEN)
        # the tag lives at the END of the file
        fin.seek(size - _TAG_LEN)
        tag = fin.read(_TAG_LEN)
        fin.seek(header)
        key = _derive_key(passphrase, salt)
        dec = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
        dec.authenticate_additional_data(magic)
        body = size - header - _TAG_LEN  # ciphertext bytes (tag excluded)
        with open(dst, "wb") as fout:
            remaining = body
            while remaining > 0:
                chunk = fin.read(min(CHUNK, remaining))
                if not chunk:
                    raise ValueError("encrypted backup file is truncated")
                remaining -= len(chunk)
                fout.write(dec.update(chunk))
            try:
                dec.finalize()  # raises InvalidTag on tampering / wrong key
            except InvalidTag as exc:
                raise ValueError(
                    "backup decryption failed — wrong key or the file is corrupted/tampered"
                ) from exc


def sniff_and_decrypt(path: str, passphrase: str | None) -> tuple[str, bool]:
    """Return (plaintext_tarball_path, was_encrypted).

    Encrypted input: decrypted into a sibling temp file (caller unlinks the
    returned path); an empty passphrase raises ValueError. Plaintext input:
    returned as-is.
    """
    if not is_encrypted(path):
        return path, False
    if not passphrase:
        raise ValueError("backup is encrypted but BACKUP_ENCRYPTION_KEY is not configured")
    plain = path + ".plain"
    decrypt_file(path, plain, passphrase)
    return plain, True
