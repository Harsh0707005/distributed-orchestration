"""Guard against processing empty SQS batches."""

def is_empty(batch):
    return not batch or len(batch) == 0
