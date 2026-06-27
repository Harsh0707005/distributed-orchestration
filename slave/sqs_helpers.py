"""Helpers for constructing SQS payloads."""

def build_message(batch_id, payload):
    return {"batch_id": batch_id, "payload": payload}
