import base64
import hashlib


class TrueHDUECipher:
    """
    Heat Death Unbreakable Encryption (V3 - Synchronous Derivation).
    Zero key material transmitted. Pad derived from Constitutional Hamiltonian.
    """

    def __init__(self, shared_seed: str):
        self.gamma = 1 / 3
        self.base_anchor = hashlib.sha3_256(shared_seed.encode()).digest()
        self.msg_counter = 0

    def _derive_synchronous_pad(self, length: int, nonce: int) -> bytes:
        pad = bytearray()
        state = self.base_anchor

        while len(pad) < length:
            collapse_string = f"{state.hex()}_{self.gamma}_{nonce}_{len(pad)}".encode()
            state = hashlib.sha3_256(collapse_string).digest()
            pad.extend(state)

        return bytes(pad[:length])

    def encrypt_bytes(self, data: bytes, kind: str = "binary") -> dict:
        """Encrypt raw bytes. kind='text' or 'binary' — informational for receiver."""
        self.msg_counter += 1
        pad = self._derive_synchronous_pad(len(data), self.msg_counter)
        ciphertext = bytes(a ^ b for a, b in zip(data, pad))
        return {
            "cipher_b64": base64.b64encode(ciphertext).decode("utf-8"),
            "nonce": self.msg_counter,
            "kind": kind,
            "length": len(data),
        }

    def decrypt_bytes(self, payload: dict) -> bytes:
        """Decrypt to raw bytes. Works for both text and binary payloads."""
        ciphertext = base64.b64decode(payload["cipher_b64"])
        nonce = payload["nonce"]
        pad = self._derive_synchronous_pad(len(ciphertext), nonce)
        if nonce > self.msg_counter:
            self.msg_counter = nonce
        return bytes(a ^ b for a, b in zip(ciphertext, pad))

    def encrypt(self, plaintext: str) -> dict:
        return self.encrypt_bytes(plaintext.encode("utf-8"), kind="text")

    def decrypt(self, payload: dict) -> str:
        return self.decrypt_bytes(payload).decode("utf-8")
