"""Bounded GPU admission; never unload or stop another application's models."""
import time
from scheduler import inventory


def wait_for_memory(gpu, minimum, cancelled=lambda: False, observe=lambda event: None,
                    timeout=30, sample=None, clock=time.monotonic, sleep=time.sleep):
    sample = sample or inventory
    deadline = clock() + timeout
    stable = 0
    while True:
        if cancelled():
            raise RuntimeError('GPU admission cancelled')
        cards = sample()  # Query failures are errors, never treated as free VRAM.
        card = next((c for c in cards if c['index'] == gpu), None)
        if card is None:
            raise RuntimeError(f'GPU {gpu} is unavailable')
        free = card['memory.free']
        stable = stable + 1 if free >= minimum else 0
        observe(dict(gpu=gpu, free_mib=free, required_mib=minimum, stable_samples=stable))
        if stable >= 2:
            return free
        if clock() >= deadline and free < minimum:
            raise RuntimeError(f'Out of VRAM: GPU {gpu} has {free}MiB free; {minimum}MiB required after waiting. Other applications were not stopped.')
        sleep(.5)
