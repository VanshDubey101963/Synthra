import os
import sys
from contextlib import contextmanager
import speech_recognition as sr

@contextmanager
def suppress_stderr():
    fd = sys.stderr.fileno()
    with open(os.devnull, "w") as devnull:
        old = os.dup(fd)
        try:
            os.dup2(devnull.fileno(), fd)
            yield
        finally:
            os.dup2(old, fd)
            os.close(old)

def speech_to_text(lang="en-IN"):
    r = sr.Recognizer()
    with suppress_stderr():
        with sr.Microphone() as source:
            r.adjust_for_ambient_noise(source, duration=2)
            audio = r.listen(source)
    try:
        return r.recognize_google(audio, language=lang)
    except (sr.UnknownValueError, sr.RequestError):
        return None
