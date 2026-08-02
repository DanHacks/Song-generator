"""Music provider interface (future upgrade path).

The app currently ships a hybrid engine: real sample one-shots layered with the
synth for pads/risers/fx. This ABC lets us later plug in MusicGen / Udio-style
local models without touching the API layer.

Start with ``SampleEngine``; when you have AWS GPU capacity, implement a
``MusicGenEngine`` and switch the factory.
"""

import os

from abc import ABC, abstractmethod


class MusicProvider(ABC):
    """Generate a stereo arrangement from a spec + settings."""

    name = "base"

    @abstractmethod
    def generate(self, prompt, settings):
        """Return (L, R, meta). L/R are float stereo arrays at engine.SR."""
        raise NotImplementedError

    @property
    def capabilities(self):
        return {}


class SampleEngine(MusicProvider):
    """Real samples layered with the NumPy synth. Fast, offline, CPU-only."""

    name = "samples"

    def generate(self, prompt, settings):
        from .generator import generate_from_prompt, generate_from_lyrics
        mode = settings.get("mode", "prompt")
        if mode == "lyrics":
            return generate_from_lyrics(
                settings.get("lyrics", prompt),
                duration_s=settings.get("duration_s", 40.0),
                genre_name=settings.get("genre"),
                seed=settings.get("seed"),
                vocal_style=settings.get("vocal_style", "none"),
                voice=settings.get("voice"),
                key=settings.get("key"),
                scale_name=settings.get("scale"),
                transpose=settings.get("transpose", 0),
            )
        return generate_from_prompt(
            prompt,
            duration_s=settings.get("duration_s", 40.0),
            seed=settings.get("seed"),
            genre_name=settings.get("genre"),
            key=settings.get("key"),
            scale_name=settings.get("scale"),
            transpose=settings.get("transpose", 0),
        )

    @property
    def capabilities(self):
        return {"samples": True, "synth": True, "vocals": True}


class MusicGenEngine(MusicProvider):
    """Real generative audio via Meta's MusicGen (transformers).

    Loads facebook/musicgen-{small|medium} once (cached on disk via
    HF_HOME / SONGFORGE_MODEL_DIR), generates from a text prompt on CPU or GPU,
    and returns a stereo WAV at engine.SR. When the model or its deps are
    unavailable it raises ``MusicGenUnavailable`` so callers can fall back.
    """

    name = "musicgen"
    # 32 kHz native; we upmix to engine.SR for a uniform pipeline.
    DEFAULT_MODEL = "facebook/musicgen-small"
    _model = None
    _processor = None

    def __init__(self, model=None, device=None, max_duration_s=180.0):
        self.model_name = model or os.environ.get("SONGFORGE_MUSICGEN_MODEL", self.DEFAULT_MODEL)
        self.device = device or os.environ.get("SONGFORGE_DEVICE", "auto")
        self.max_duration_s = max_duration_s
        self._ensure()

    def _ensure(self):
        if MusicGenEngine._model is not None:
            return
        try:
            import torch
            from transformers import AutoProcessor, MusicgenForConditionalGeneration
        except Exception as exc:
            raise MusicGenUnavailable("MusicGen deps missing: %s" % exc)
        if self.device == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        model_id = self.model_name
        try:
            MusicGenEngine._processor = AutoProcessor.from_pretrained(model_id)
            MusicGenEngine._model = MusicgenForConditionalGeneration.from_pretrained(model_id)
        except Exception as exc:
            raise MusicGenUnavailable("Failed to load %s: %s" % (model_id, exc))
        MusicGenEngine._model.eval()
        if self.device == "cuda":
            MusicGenEngine._model.to("cuda")

    def generate(self, prompt, settings):
        import numpy as np

        import torch
        from transformers import set_seed

        duration_s = float(settings.get("duration_s", 40.0))
        duration_s = min(duration_s, self.max_duration_s)
        seed = settings.get("seed")
        if seed is not None:
            set_seed(int(seed))
        tokens = max(1, int(round(duration_s * 50)))  # 50 tokens/s @ 32kHz
        inputs = MusicGenEngine._processor(
            text=[prompt], padding=True, return_tensors="pt"
        )
        if self.device == "cuda":
            inputs = {k: v.to("cuda") for k, v in inputs.items()}
        with torch.no_grad():
            audio = MusicGenEngine._model.generate(
                **inputs,
                max_new_tokens=tokens,
                do_sample=True,
                temperature=float(settings.get("temperature", 1.0)),
                top_k=int(settings.get("top_k", 250)),
                top_p=float(settings.get("top_p", 0.95)),
                guidance_scale=float(settings.get("guidance_scale", 3.0)),
            )
        wav = audio[0].cpu().numpy()  # [T] mono at 32kHz (or [C,T])
        if wav.ndim == 2:
            mono = wav.mean(axis=0)
        else:
            mono = wav
        from .engine import SR as OUT_SR
        if OUT_SR != 32000:
            mono = _resample_linear(mono, 32000, OUT_SR)
        # soft normalize, duplicate mono to stereo
        peak = float(np.max(np.abs(mono))) + 1e-9
        mono = mono / peak * 0.92
        L = mono.astype(np.float32)
        R = L.copy()
        meta = settings.get("_meta", {})
        meta["engine"] = "musicgen"
        meta["model"] = self.model_name
        meta["prompt"] = prompt
        return L, R, meta

    @property
    def capabilities(self):
        return {"musicgen": True, "device": self.device}


def _resample_linear(x, src, dst):
    import numpy as np
    n = int(len(x) * dst / src)
    idx = np.linspace(0, len(x) - 1, n)
    return np.interp(idx, np.arange(len(x)), x).astype(np.float32)


class MusicGenUnavailable(Exception):
    pass


def get_provider(name=None):
    """Factory.

    - name="musicgen": MusicGen, raises MusicGenUnavailable if not available.
    - name="samples": hybrid sample+synth engine.
    - name=None (default): MusicGen primary, hybrid samples fallback.
    """
    if name == "musicgen":
        return MusicGenEngine()
    if name == "samples":
        return SampleEngine()
    try:
        return MusicGenEngine()
    except MusicGenUnavailable:
        return SampleEngine()
