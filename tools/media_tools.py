from __future__ import annotations

import ctypes
import time
from dataclasses import dataclass


VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3


@dataclass(slots=True)
class MediaTools:
    def volume_up(self, step: int = 5) -> dict:
        for _ in range(max(1, min(step, 50))):
            self._press_vk(VK_VOLUME_UP)
        time.sleep(0.5)
        current = self.get_current_volume()
        return {"status": "ok", "action": "volume_up", "step": step * 2, "current_volume": current}

    def volume_down(self, step: int = 5) -> dict:
        for _ in range(max(1, min(step, 50))):
            self._press_vk(VK_VOLUME_DOWN)
        time.sleep(0.5)
        current = self.get_current_volume()
        return {"status": "ok", "action": "volume_down", "step": step * 2, "current_volume": current}

    def get_current_volume(self) -> int | None:
        try:
            import comtypes
            comtypes.CoInitialize()
            from pycaw.pycaw import AudioUtilities

            devices = AudioUtilities.GetSpeakers()
            if devices and hasattr(devices, "EndpointVolume"):
                return int(round(devices.EndpointVolume.GetMasterVolumeLevelScalar() * 100))
        except Exception:
            pass
        return None

    def mute_audio(self) -> dict:
        state = self._set_mute_state(True)
        if state is None:
            self._press_vk(VK_VOLUME_MUTE)
            return {"status": "ok", "action": "mute_audio", "mode": "toggle_fallback"}
        return {"status": "ok", "action": "mute_audio", "mode": "pycaw"}

    def unmute_audio(self) -> dict:
        state = self._set_mute_state(False)
        if state is None:
            self._press_vk(VK_VOLUME_MUTE)
            return {"status": "ok", "action": "unmute_audio", "mode": "toggle_fallback"}
        return {"status": "ok", "action": "unmute_audio", "mode": "pycaw"}

    def toggle_mute(self) -> dict:
        self._press_vk(VK_VOLUME_MUTE)
        return {"status": "ok", "action": "toggle_mute"}

    def media_play_pause(self) -> dict:
        self._press_vk(VK_MEDIA_PLAY_PAUSE)
        return {"status": "ok", "action": "media_play_pause"}

    def media_next(self) -> dict:
        self._press_vk(VK_MEDIA_NEXT_TRACK)
        return {"status": "ok", "action": "media_next"}

    def media_previous(self) -> dict:
        self._press_vk(VK_MEDIA_PREV_TRACK)
        return {"status": "ok", "action": "media_previous"}

    def _press_vk(self, key_code: int) -> None:
        ctypes.windll.user32.keybd_event(key_code, 0, 0, 0)
        ctypes.windll.user32.keybd_event(key_code, 0, 0x0002, 0)

    def _set_mute_state(self, muted: bool) -> bool | None:
        try:
            import comtypes
            comtypes.CoInitialize()
            from pycaw.pycaw import AudioUtilities

            devices = AudioUtilities.GetSpeakers()
            if devices and hasattr(devices, "EndpointVolume"):
                devices.EndpointVolume.SetMute(1 if muted else 0, None)
                return muted
        except Exception:
            pass
        return None
