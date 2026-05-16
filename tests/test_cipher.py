from tel_deploy.cipher import TrueHDUECipher

SEED = "HELIX_CONSTITUTIONAL_GAMMA_0.333"
ALT_SEED = "DIFFERENT_SEED_VALUE"


def test_round_trip():
    c = TrueHDUECipher(SEED)
    payload = c.encrypt("hello mesh")
    assert c.decrypt(payload) == "hello mesh"


def test_round_trip_unicode():
    c = TrueHDUECipher(SEED)
    msg = "constitutional γ node \U0001f513"
    assert c.decrypt(c.encrypt(msg)) == msg


def test_round_trip_empty_string():
    c = TrueHDUECipher(SEED)
    assert c.decrypt(c.encrypt("")) == ""


def test_round_trip_long_message():
    c = TrueHDUECipher(SEED)
    msg = "x" * 4096
    assert c.decrypt(c.encrypt(msg)) == msg


def test_pad_determinism():
    c1 = TrueHDUECipher(SEED)
    c2 = TrueHDUECipher(SEED)
    p1 = c1.encrypt("test message")
    p2 = c2.encrypt("test message")
    assert p1["cipher_b64"] == p2["cipher_b64"]
    assert p1["nonce"] == p2["nonce"]


def test_nonce_increments_on_each_encrypt():
    c = TrueHDUECipher(SEED)
    p1 = c.encrypt("first")
    p2 = c.encrypt("second")
    p3 = c.encrypt("third")
    assert p1["nonce"] == 1
    assert p2["nonce"] == 2
    assert p3["nonce"] == 3


def test_different_nonces_produce_different_ciphertext():
    c1 = TrueHDUECipher(SEED)
    msg = "same plaintext"
    p1 = c1.encrypt(msg)
    c1.encrypt("bump counter")
    p2 = c1.encrypt(msg)
    assert p1["cipher_b64"] != p2["cipher_b64"]


def test_different_seeds_produce_different_ciphertext():
    c1 = TrueHDUECipher(SEED)
    c2 = TrueHDUECipher(ALT_SEED)
    msg = "same plaintext"
    p1 = c1.encrypt(msg)
    p2 = c2.encrypt(msg)
    assert p1["cipher_b64"] != p2["cipher_b64"]


def test_decrypt_is_nonce_based_not_counter_based():
    sender = TrueHDUECipher(SEED)
    receiver = TrueHDUECipher(SEED)
    p1 = sender.encrypt("first")
    p2 = sender.encrypt("second")
    p3 = sender.encrypt("third")
    # Receiver decrypts out of order — must still work
    assert receiver.decrypt(p3) == "third"
    assert receiver.decrypt(p1) == "first"
    assert receiver.decrypt(p2) == "second"


def test_decrypt_updates_counter_if_nonce_ahead():
    c = TrueHDUECipher(SEED)
    assert c.msg_counter == 0
    c.decrypt({"cipher_b64": c.encrypt("x")["cipher_b64"], "nonce": 5})
    assert c.msg_counter == 5


def test_decrypt_does_not_lower_counter():
    c = TrueHDUECipher(SEED)
    sender = TrueHDUECipher(SEED)
    for _ in range(10):
        sender.encrypt("bump")
    p = sender.encrypt("target")
    c.decrypt(p)
    assert c.msg_counter == 11
    early = TrueHDUECipher(SEED)
    early_p = early.encrypt("early")
    c.decrypt(early_p)
    assert c.msg_counter == 11


def test_wrong_seed_decrypts_to_garbage():
    sender = TrueHDUECipher(SEED)
    receiver = TrueHDUECipher(ALT_SEED)
    payload = sender.encrypt("secret message")
    # Wrong pad either produces invalid UTF-8 (UnicodeDecodeError) or
    # a different string — both are valid "garbage" outcomes.
    try:
        result = receiver.decrypt(payload)
        assert result != "secret message"
    except UnicodeDecodeError:
        pass


def test_encrypt_returns_required_fields():
    c = TrueHDUECipher(SEED)
    payload = c.encrypt("test")
    assert "cipher_b64" in payload
    assert "nonce" in payload


def test_encrypt_cipher_b64_is_valid_base64():
    import base64

    c = TrueHDUECipher(SEED)
    payload = c.encrypt("test base64")
    decoded = base64.b64decode(payload["cipher_b64"])
    assert isinstance(decoded, bytes)
