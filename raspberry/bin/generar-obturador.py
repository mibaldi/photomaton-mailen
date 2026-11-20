#!/usr/bin/env python3
# sonido de obturador sintético: dos clics con ruido filtrado
import wave, struct, random, math
sr = 44100
def clic(dur, amp, decay):
    n = int(sr * dur); out = []; prev = 0
    for i in range(n):
        x = random.uniform(-1, 1); prev = 0.6 * prev + 0.4 * x
        out.append(prev * amp * math.exp(-i / (sr * decay)))
    return out
s = clic(0.05, 0.9, 0.008) + [0] * int(sr * 0.07) + clic(0.09, 0.8, 0.02) + [0] * int(sr * 0.05)
with wave.open("/home/admin/photobooth-data/userdata/obturador.wav", "w") as f:
    f.setnchannels(1); f.setsampwidth(2); f.setframerate(sr)
    f.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, v)) * 32000)) for v in s))
