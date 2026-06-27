from uuid import uuid4

def get_next_batch_name() -> str:
    return f'batch_{uuid4()}'

