import hashlib
import secrets


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    # A token 256 bit véletlen, ezért elég egy gyors hash (nem jelszó, nem kell bcrypt).
    return hashlib.sha256(token.encode()).hexdigest()
