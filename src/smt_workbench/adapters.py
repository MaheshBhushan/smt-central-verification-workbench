"""Local JSON adapters inspired by M2M/IPC-CFX concepts; no wire compatibility claim."""

from .schemas import Event


def normalize(message: dict):
    if message.get("adapter") == "cfx-inspired":
        return Event.model_validate(message["body"])
    return Event.model_validate(message)
