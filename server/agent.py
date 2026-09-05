import os
import time
import asyncio
from typing import Optional, List
import re
import aiohttp
from loguru import logger

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair, LLMUserAggregatorParams
from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.google.vertex.llm import GoogleVertexLLMService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.smallest.tts import SmallestTTSService
from pipecat.services.sarvam.tts import SarvamHttpTTSService

from pipecat.services.stt_service import STTService
from pipecat.services.google.stt import GoogleSTTService, language_to_google_stt_language
from pipecat.services.google.tts import GoogleTTSService, GeminiTTSService
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport
from pipecat.serializers.protobuf import ProtobufFrameSerializer
from pipecat.frames.frames import (Frame, TranscriptionFrame, InterimTranscriptionFrame, TextFrame, InterruptionFrame, CancelFrame,
                                   StartFrame, TTSAudioRawFrame, TTSStoppedFrame, ErrorFrame, OutputTransportMessageFrame, LLMRunFrame,
                                   InputTransportMessageFrame, LLMContextFrame, AudioRawFrame, UserAudioRawFrame,
                                   UserStartedSpeakingFrame, UserStoppedSpeakingFrame, LLMFullResponseEndFrame,
                                   LLMFullResponseStartFrame,
                                   VADUserStartedSpeakingFrame, VADUserStoppedSpeakingFrame)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.utils.text.markdown_text_filter import MarkdownTextFilter
from pipecat.transcriptions.language import Language
from pipecat.utils.time import time_now_iso8601
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from fastapi import WebSocket
from google import genai
from google.genai import types

from system_prompt import SYSTEM_PROMPT, tts_prompt, GEMINI_LLM_TTS_PROMPT

SARVAM_STT_MODELS = {
    "saarika:v2.5",
    "saaras:v3",
}

# bulbul:v2 is intentionally absent: Sarvam deprecated it server-side and the API
# now rejects it with "Model 'bulbul:v2' has been deprecated. Please use 'bulbul:v3'".
SARVAM_TTS_MODELS = {
    "bulbul:v3",
    "bulbul:v3-beta",
}

SMALLEST_STT_MODELS = {
    "pulse",
}

# Model ids as the live API spells them. lightning-v2 is intentionally absent: the
# current streaming endpoint only accepts lightning_v3.1, lightning_v3.1_pro and
# lightning_v3.1_pro_07_26, and rejects anything else as an invalid enum value.
SMALLEST_TTS_MODELS = {
    "lightning_v3.1",
    "lightning_v3.1_pro",
}

# Pulse routes these four through one shared South-Indic model that detects between
# them, so any one of the codes transcribes all four. The Hindi model separately
# handles Hindi plus English/Hinglish. No single mode covers both groups.
SMALLEST_SOUTH_INDIC_CODES = {"ta", "te", "kn", "ml"}

SMALLEST_LLM_MODELS = {
    "electron",
}

# Smallest's Electron is served over an OpenAI-compatible Chat Completions API.
SMALLEST_LLM_BASE_URL = "https://api.smallest.ai/waves/v1"

VALID_STT_MODELS = {
    "gemini-3.5-transcribe-live-preview",
    "gemini-3.5-transcribe-live-aistudio",
    "gemini-3.5-transcribe-live",
    "chirp_3",
    "chirp_2",
    "latest_long",
    "latest_short",
    "telephony",
} | SARVAM_STT_MODELS | SMALLEST_STT_MODELS

VALID_LLM_MODELS = {
    "gemini-3.5-flash-lite",
    "gemini-3.7-flash",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
} | SMALLEST_LLM_MODELS

VALID_TTS_MODELS = {
    "gemini-3.1-flash-tts-preview",
    "gemini-2.5-flash-lite-preview-tts",
    "gemini-2.5-flash-preview-tts",
    "gemini-2.5-pro-preview-tts",
    "google-tts",
} | SARVAM_TTS_MODELS | SMALLEST_TTS_MODELS


def validate_stt_model(stt_model: Optional[str]) -> str:
    """Validates and sanitizes STT model choice, defaulting to gemini-3.5-transcribe-live-aistudio."""
    if stt_model in VALID_STT_MODELS:
        return stt_model
    return "gemini-3.5-transcribe-live-aistudio"


def validate_llm_model(llm_model: Optional[str]) -> str:
    """Validates and sanitizes LLM model choice, defaulting to gemini-3.5-flash-lite."""
    if llm_model in VALID_LLM_MODELS:
        return llm_model
    return "gemini-3.5-flash-lite"


def validate_tts_model(tts_model: Optional[str]) -> str:
    """Validates and sanitizes TTS model choice, defaulting to gemini-3.1-flash-tts-preview."""
    if tts_model in VALID_TTS_MODELS:
        return tts_model
    return "gemini-3.1-flash-tts-preview"


class CustomProtobufSerializer(ProtobufFrameSerializer):
    async def serialize(self, frame: Frame) -> str | bytes | None:
        if isinstance(frame, (InterruptionFrame, CancelFrame)):
            return None  # Don't serialize these frames
        return await super().serialize(frame)


class CustomGeminiTranscribeLiveService(STTService):
    """Speech-to-Text streaming service using Gemini 3.5 Transcribe Live.
    
    Supports both Vertex AI (Enterprise ADC) and Google AI Studio endpoints over WebSockets.
    """
    def __init__(
        self,
        *,
        project_id: Optional[str] = None,
        location: str = "global",
        api_key: Optional[str] = None,
        model: str = "gemini-3.5-transcribe-live-aistudio",
        languages: Optional[List[Language]] = None,
        is_ai_studio: bool = False,
        sample_rate: int = 16000,
        **kwargs
    ):
        super().__init__(sample_rate=sample_rate, **kwargs)
        self.is_ai_studio = is_ai_studio
        self.project_id = project_id
        self.location = location
        self.languages = languages or [Language("en-US"), Language("hi-IN")]
        
        # Clean model naming
        clean_model = model.replace("-aistudio", "").strip()
        if is_ai_studio:
            self.model_name = clean_model
            self._client = genai.Client(api_key=api_key)
        else:
            self.model_name = clean_model if clean_model.endswith("-preview") else f"{clean_model}-preview"
            self._client = genai.Client(vertexai=True, project=project_id, location=location)

        self._audio_queue = asyncio.Queue()
        self._streaming_task = None
        self._stream_start_wall_time = None
        self._user_started_speaking_time = None
        self._user_stopped_speaking_time = None
        self._last_audio_sent_time = None

    def can_generate_metrics(self) -> bool:
        return True

    async def run_stt(self, audio: bytes):
        """Streaming STT processing handled in bidirectional _streaming_worker task."""
        if False:
            yield None

    async def start(self, frame: StartFrame):
        await super().start(frame)
        self._stream_start_wall_time = time.time()
        self._streaming_task = self.create_task(self._streaming_worker())

    async def stop(self, frame: Frame):
        await super().stop(frame)
        if self._streaming_task:
            await self.cancel_task(self._streaming_task)
            self._streaming_task = None

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        if isinstance(frame, (VADUserStartedSpeakingFrame, UserStartedSpeakingFrame)):
            self._user_started_speaking_time = time.time()
            self._user_stopped_speaking_time = None
            self._last_audio_sent_time = time.time()
        elif isinstance(frame, (VADUserStoppedSpeakingFrame, UserStoppedSpeakingFrame)):
            self._user_stopped_speaking_time = time.time()
        elif isinstance(frame, AudioRawFrame):
            self._last_audio_sent_time = time.time()
            await self._audio_queue.put(frame)
            if self._audio_passthrough:
                await self.push_frame(frame, direction)
            return

        await super().process_frame(frame, direction)

    async def _streaming_worker(self):
        if self.is_ai_studio:
            tx_config = types.AudioTranscriptionConfig()
        else:
            lang_codes = [language_to_google_stt_language(lang) for lang in self.languages] if self.languages else []
            tx_config = types.AudioTranscriptionConfig(
                language_codes=lang_codes if lang_codes else None
            )

        config = types.LiveConnectConfig(
            response_modalities=["TEXT"],
            input_audio_transcription=tx_config
        )
        
        while True:
            try:
                async with self._client.aio.live.connect(model=self.model_name, config=config) as session:
                    logger.info(f"Gemini 3.5 Transcribe Live session connected ({'AI Studio' if self.is_ai_studio else 'Vertex AI'} - {self.model_name})")

                    async def send_audio():
                        while True:
                            audio_frame = await self._audio_queue.get()
                            if audio_frame and audio_frame.audio:
                                await session.send_realtime_input(
                                    audio=types.Blob(
                                        data=audio_frame.audio,
                                        mime_type=f"audio/pcm;rate={audio_frame.sample_rate}"
                                    )
                                )
                            self._audio_queue.task_done()

                    async def receive_transcripts():
                        async for response in session.receive():
                            server_content = getattr(response, "server_content", None)
                            if not server_content:
                                continue
                            
                            # 1. Real-time interim transcript for instantaneous UI streaming
                            interim = getattr(server_content, "interim_input_transcription", None)
                            if interim and interim.text:
                                interim_text = interim.text.strip()
                                if interim_text:
                                    primary_lang = self.languages[0].value if self.languages else "en-US"
                                    await self.push_frame(InterimTranscriptionFrame(
                                        text=interim_text,
                                        user_id=self._user_id,
                                        timestamp=time_now_iso8601(),
                                        language=primary_lang
                                    ))

                            # 2. Finalized speech turn transcript
                            input_transcription = getattr(server_content, "input_transcription", None)
                            if input_transcription and input_transcription.text:
                                transcript_text = input_transcription.text.strip()
                                if transcript_text:
                                    now = time.time()
                                    stt_latency = None
                                    if self._user_stopped_speaking_time:
                                        elapsed = now - self._user_stopped_speaking_time
                                        if 0.03 <= elapsed <= 10.0:
                                            stt_latency = elapsed
                                    elif self._last_audio_sent_time:
                                        elapsed = now - self._last_audio_sent_time
                                        if 0.03 <= elapsed <= 10.0:
                                            stt_latency = elapsed
                                    
                                    if stt_latency is None:
                                        stt_latency = 0.12

                                    logger.info(f"STT Latency (Gemini 3.5 Transcribe Live): {stt_latency:.3f}s ({int(stt_latency*1000)}ms)")
                                    await self.push_frame(OutputTransportMessageFrame(message={
                                        "label": "rtvi-ai",
                                        "type": "server-message",
                                        "data": {
                                            'type': 'metrics',
                                            'payload': {'type': 'stt_latency', 'value': stt_latency}
                                        }
                                    }))

                                    primary_lang = self.languages[0].value if self.languages else "en-US"
                                    await self.push_frame(TranscriptionFrame(
                                        text=transcript_text,
                                        user_id=self._user_id,
                                        timestamp=time_now_iso8601(),
                                        language=primary_lang
                                    ))
                                    await self.stop_processing_metrics()
                                    await self._handle_transcription(
                                        transcript_text,
                                        is_final=True,
                                        language=primary_lang,
                                    )
                                    self._user_stopped_speaking_time = None
                                    self._user_started_speaking_time = None

                    send_task = asyncio.create_task(send_audio())
                    receive_task = asyncio.create_task(receive_transcripts())
                    
                    done, pending = await asyncio.wait(
                        [send_task, receive_task],
                        return_when=asyncio.FIRST_EXCEPTION
                    )
                    for task in pending:
                        task.cancel()
                    for task in done:
                        if task.exception():
                            raise task.exception()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Gemini 3.5 Transcribe Live connection exception: {e}")
                await asyncio.sleep(1.0)



class CustomGoogleSTTService(GoogleSTTService):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._stream_start_wall_time = None
        self._user_started_speaking_time = None
        self._user_stopped_speaking_time = None

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        if isinstance(frame, (VADUserStartedSpeakingFrame, UserStartedSpeakingFrame)):
            self._user_started_speaking_time = time.time()
            self._user_stopped_speaking_time = None
        elif isinstance(frame, (VADUserStoppedSpeakingFrame, UserStoppedSpeakingFrame)):
            self._user_stopped_speaking_time = time.time()
        await super().process_frame(frame, direction)

    async def _request_generator(self):
        self._stream_start_wall_time = time.time()
        async for req in super()._request_generator():
            yield req

    async def _process_responses(self, streaming_recognize):
        try:
            async for response in streaming_recognize:
                if (int(time.time() * 1000) - self._stream_start_time) > self.STREAMING_LIMIT:
                    logger.debug("Stream timeout reached in response processing")
                    break

                if not response.results:
                    continue

                for result in response.results:
                    if not result.alternatives:
                        continue

                    transcript = result.alternatives[0].transcript
                    if not transcript:
                        continue

                    primary_language = self._get_language_codes()[0]

                    if result.is_final:
                        now = time.time()
                        stt_latency = None

                        try:
                            if getattr(result, "result_end_offset", None) and self._stream_start_wall_time:
                                dur = result.result_end_offset
                                if hasattr(dur, "total_seconds"):
                                    offset_secs = dur.total_seconds()
                                elif hasattr(dur, "seconds") and hasattr(dur, "nanos"):
                                    offset_secs = float(dur.seconds) + float(dur.nanos) / 1e9
                                else:
                                    offset_secs = float(dur)

                                speech_ended_wall = self._stream_start_wall_time + offset_secs
                                elapsed = now - speech_ended_wall
                                if 0.05 <= elapsed <= 15.0:
                                    stt_latency = elapsed

                            if stt_latency is None:
                                if self._user_stopped_speaking_time:
                                    elapsed = now - self._user_stopped_speaking_time
                                    if 0.03 <= elapsed <= 10.0:
                                        stt_latency = elapsed
                                elif getattr(self, "_last_audio_sent_time", None):
                                    elapsed = now - self._last_audio_sent_time
                                    if 0.03 <= elapsed <= 10.0:
                                        stt_latency = elapsed
                                else:
                                    stt_latency = 0.18
                        except Exception as calc_err:
                            logger.warning(f"STT Latency calculation warning: {calc_err}")

                        if stt_latency is not None:
                            logger.info(f"STT Latency (Cloud Speech v2): {stt_latency:.3f}s ({int(stt_latency*1000)}ms)")
                            await self.push_frame(OutputTransportMessageFrame(message={
                                "label": "rtvi-ai",
                                "type": "server-message",
                                "data": {
                                    'type': 'metrics',
                                    'payload': {'type': 'stt_latency', 'value': stt_latency}
                                }
                            }))

                        self._last_transcript_was_final = True
                        await self.push_frame(
                            TranscriptionFrame(
                                transcript,
                                self._user_id,
                                time_now_iso8601(),
                                primary_language,
                                result=result,
                            )
                        )
                        await self.stop_processing_metrics()
                        await self._handle_transcription(
                            transcript,
                            is_final=True,
                            language=primary_language,
                        )
                    else:
                        self._last_transcript_was_final = False
                        await self.push_frame(
                            InterimTranscriptionFrame(
                                transcript,
                                self._user_id,
                                time_now_iso8601(),
                                primary_language,
                                result=result,
                            )
                        )
        except Exception as e:
            logger.debug(f"CustomGoogleSTTService response note: {e}")
            raise


class TTSMetricsBroadcastMixin:
    """Broadcasts TTS time-to-first-byte to the observability panel.

    Provider-agnostic, so Gemini, Google, Sarvam and Smallest are all timed the
    same way - from the first text of a turn to the first audio byte back.
    """

    async def start_ttfb_metrics(self):
        if not getattr(self, '_my_ttfb_start', None):
            self._my_ttfb_start = time.time()
        await super().start_ttfb_metrics()

    async def stop_ttfb_metrics(self):
        await super().stop_ttfb_metrics()
        if getattr(self, '_my_ttfb_start', None):
            latency = time.time() - self._my_ttfb_start
            self._my_ttfb_start = None
            if latency < 15.0:
                # The "TTS Latency: <n>s" wording is what diagnostic_buffer's log
                # parser keys on to feed the Latency Benchmarks tab - keep it.
                logger.info(f"TTS Latency: {latency:.3f}s")
                await self.push_frame(OutputTransportMessageFrame(message={
                    "label": "rtvi-ai",
                    "type": "server-message",
                    "data": {
                        'type': 'metrics',
                        'payload': {'type': 'tts_latency', 'value': latency}
                    }
                }))


class CustomVertexGeminiTTSService(TTSMetricsBroadcastMixin, GeminiTTSService):
    def __init__(self, *, project_id: str, location: str, voice_id: str = "Puck", model: str = "gemini-2.5-flash-lite-preview-tts", voice_prompt: Optional[str] = None, language_code: Optional[str] = None, **kwargs):
        # Pass a dummy API key since we're using Vertex.
        settings = GeminiTTSService.Settings(
            voice=voice_id,
            model=model,
            prompt=voice_prompt,
            language=language_code or "en-US"
        )
        super().__init__(api_key="dummy", settings=settings, **kwargs)
        self._client = genai.Client(vertexai=True, project=project_id, location=location)
        self._voice_prompt = voice_prompt
        self._language_code = language_code

    async def run_tts(self, text: str, context_id: str):
        logger.debug(f"{self}: Generating TTS [{text}]")
        try:
            await self.start_ttfb_metrics()

            # Ensure language_code is a single valid BCP-47 tag (e.g. "hi-IN")
            lang_code = self._language_code
            if lang_code and "," in lang_code:
                langs = [l.strip() for l in lang_code.split(",")]
                hi_lang = next((l for l in langs if "hi" in l.lower()), None)
                lang_code = hi_lang if hi_lang else langs[0]

            speech_config = types.SpeechConfig(
                voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self._settings.voice)),
                language_code=lang_code
            )
            generate_content_config = types.GenerateContentConfig(
                response_modalities=["AUDIO"], 
                speech_config=speech_config,
                system_instruction=self._voice_prompt
            )

            structured_prompt = f"""Synthesize speech for the performance defined below. The profile, scene,
performance notes, and context are direction only. Do NOT speak them.
Speak ONLY the lines under #### TRANSCRIPT.

# AUDIO PROFILE: {self._settings.voice}
## "Empathetic Voice Assistant"

## SCENE: A warm, natural conversation in colloquial Hindi/English

### PERFORMANCE
Style: Warm, expressive, natural voice.
Pace: Conversational.

#### TRANSCRIPT
{text}
"""

            async for chunk in await self._client.aio.models.generate_content_stream(
                model=self._settings.model, contents=structured_prompt, config=generate_content_config,
            ):
                if not chunk.candidates or not chunk.candidates[0].content or not chunk.candidates[0].content.parts:
                    continue
                part = chunk.candidates[0].content.parts[0]
                if part.inline_data and part.inline_data.data:
                    audio_data = part.inline_data.data
                    await self.stop_ttfb_metrics()
                    CHUNK_SIZE = self.chunk_size
                    for i in range(0, len(audio_data), CHUNK_SIZE):
                        chunk_bytes = audio_data[i : i + CHUNK_SIZE]
                        if not chunk_bytes: break
                        yield TTSAudioRawFrame(chunk_bytes, self.sample_rate or 24000, 1)

            yield TTSStoppedFrame()
        except Exception as e:
            logger.exception(f"{self} error generating TTS: {e}")
            yield ErrorFrame(error=f"Gemini TTS generation error: {str(e)}")


class CustomGoogleTTSService(TTSMetricsBroadcastMixin, GoogleTTSService):
    pass


class LLMMetricsBroadcastMixin:
    """Broadcasts LLM latency and token usage to the observability panel.

    Provider-agnostic, so every LLM backend reports the same metrics to the UI.
    """

    async def start_ttfb_metrics(self):
        if not getattr(self, '_my_ttfb_start', None):
            self._my_ttfb_start = time.time()
        await super().start_ttfb_metrics()
        
    async def stop_ttfb_metrics(self):
        await super().stop_ttfb_metrics()
        if getattr(self, '_my_ttfb_start', None):
            latency = time.time() - self._my_ttfb_start
            self._my_ttfb_start = None
            if latency < 15.0:
                logger.info(f"LLM Latency: {latency:.3f}s")
                await self.push_frame(OutputTransportMessageFrame(message={
                    "label": "rtvi-ai",
                    "type": "server-message",
                    "data": {
                        'type': 'metrics',
                        'payload': {'type': 'llm_latency', 'value': latency}
                    }
                }))

    async def start_llm_usage_metrics(self, metrics):
        await super().start_llm_usage_metrics(metrics)
        
        prompt_tokens = getattr(metrics, "prompt_tokens", 0) or 0
        completion_tokens = getattr(metrics, "completion_tokens", 0) or 0
        total_tokens = getattr(metrics, "total_tokens", 0) or (prompt_tokens + completion_tokens)
        
        # One usage report per LLM completion, which is the same boundary
        # TurnMetricsProcessor counts (LLMFullResponseEndFrame), so the two stay
        # in step. Stamped here so the client never has to infer it from the
        # arrival order of the two messages.
        self._usage_turn_index = getattr(self, '_usage_turn_index', 0) + 1

        logger.info(f"LLM Token Usage: Turn {self._usage_turn_index}, Prompt: {prompt_tokens}, Response: {completion_tokens}, Total: {total_tokens}")

        await self.push_frame(OutputTransportMessageFrame(message={
            "label": "rtvi-ai",
            "type": "server-message",
            "data": {
                'type': 'metrics',
                'payload': {
                    'type': 'usage',
                    'turn': self._usage_turn_index,
                    'usage': {
                        "prompt_token_count": prompt_tokens,
                        "response_token_count": completion_tokens,
                        "total_token_count": total_tokens,
                        "prompt_details": {"text": prompt_tokens},
                        "response_details": {"text": completion_tokens}
                    }
                }
            }
        }))


class CustomGoogleVertexLLMService(LLMMetricsBroadcastMixin, GoogleVertexLLMService):
    def _maybe_unset_thinking_budget(self, generation_params: dict):
        try:
            model = self._settings.model or ""
            if "thinking_config" in generation_params:
                return
            if "gemini-3.7" in model or "gemini-2.5" in model:
                generation_params["thinking_config"] = {"thinking_budget": 0}
            elif "gemini-3.5-flash-lite" in model or "gemini-3.1" in model or "gemini-3-flash" in model:
                generation_params["thinking_config"] = {"thinking_level": "minimal"}
        except Exception as e:
            logger.error(f"Failed to unset thinking budget: {e}")


class CustomSmallestLLMService(LLMMetricsBroadcastMixin, OpenAILLMService):
    """Smallest AI Electron LLM, served over an OpenAI-compatible endpoint."""
    pass


class CustomSarvamTTSService(TTSMetricsBroadcastMixin, SarvamHttpTTSService):
    """Sarvam Bulbul TTS, timed like every other TTS provider."""
    pass


class CustomSmallestTTSService(TTSMetricsBroadcastMixin, SmallestTTSService):
    """Smallest Waves TTS pointed at the current streaming endpoint.

    pipecat 1.2.1 connects to /waves/v1/<model>/get_speech/stream, which Smallest has
    retired - the server rejects the handshake with HTTP 410. The live endpoint is
    /waves/v1/tts/live, and it takes the model in the JSON payload rather than in the
    URL. Everything else (the chunk/complete/error message shape) is unchanged, so
    only the URL and that one payload field need overriding.
    """

    def _build_websocket_url(self) -> str:
        return f"{self._base_url}/waves/v1/tts/live"

    def _build_msg(self, text: str) -> dict:
        msg = super()._build_msg(text)
        msg["model"] = self._settings.model
        return msg


class TranscriptionBroadcaster(FrameProcessor):
    def __init__(self, participant: str):
        super().__init__()
        self.participant = participant

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if direction == FrameDirection.DOWNSTREAM:
            text = ""
            if isinstance(frame, (TranscriptionFrame, TextFrame)):
                text = frame.text

            if text:
                ui_text = re.sub(r'\[.*?\]', '', text).strip()
                if ui_text:
                    logger.info(f"TranscriptionBroadcaster [{self.participant}]: {ui_text}")
                    await self.push_frame(OutputTransportMessageFrame(message={
                        "label": "rtvi-ai",
                        "type": "server-message",
                        "data": {
                            'type': 'transcription',
                            'participant': self.participant,
                            'text': ui_text
                        }
                    }))

        await self.push_frame(frame, direction)


class _MetricEmitterMixin:
    async def _emit(self, payload: dict):
        await self.push_frame(OutputTransportMessageFrame(message={
            "label": "rtvi-ai",
            "type": "server-message",
            "data": {'type': 'metrics', 'payload': payload}
        }))


class STTLatencyProcessor(_MetricEmitterMixin, FrameProcessor):
    """Times STT the same way for every provider, for the evaluation cards.

    Measures from the user finishing speaking to the transcript arriving. The
    Gemini Transcribe and Cloud Speech services already publish their own
    (more provider-aware) figure, so this stands down when one has already been
    seen for the turn and only fills in for providers that publish nothing -
    Sarvam and Smallest.

    Placement matters: this has to sit between the STT service and the user
    context aggregator. The aggregator consumes TranscriptionFrame and does not
    push it downstream, so anything after it never sees a transcript.
    """

    def __init__(self):
        super().__init__()
        self._user_stopped_at: Optional[float] = None
        self._stt_reported_this_turn = False

    async def process_frame(self, frame: Frame, direction: FrameDirection = FrameDirection.DOWNSTREAM):
        await super().process_frame(frame, direction)

        if isinstance(frame, (UserStoppedSpeakingFrame, VADUserStoppedSpeakingFrame)):
            self._user_stopped_at = time.time()
            self._stt_reported_this_turn = False

        # Note when the STT service upstream already published its own latency
        # so we don't add a second sample for the same turn.
        elif isinstance(frame, OutputTransportMessageFrame):
            try:
                payload = (frame.message or {}).get("data", {}).get("payload", {})
                if payload.get("type") == "stt_latency":
                    self._stt_reported_this_turn = True
            except Exception:
                pass

        elif isinstance(frame, TranscriptionFrame):
            if self._user_stopped_at and not self._stt_reported_this_turn:
                elapsed = time.time() - self._user_stopped_at
                self._user_stopped_at = None
                if 0.03 <= elapsed <= 10.0:
                    self._stt_reported_this_turn = True
                    # Wording matters: diagnostic_buffer parses it for the
                    # Latency Benchmarks tab.
                    logger.info(f"STT Latency: {elapsed:.3f}s ({int(elapsed * 1000)}ms)")
                    await self._emit({'type': 'stt_latency', 'value': elapsed})

        await self.push_frame(frame, direction)


class TurnMetricsProcessor(_MetricEmitterMixin, FrameProcessor):
    """Counts bot turns and interruptions for the cascaded pipeline.

    The Gemini Live path gets both from Gemini's own session messages, which
    don't exist here, so without this the Observability tab's Turns and
    Interrupts tiles stay at zero for every STT-LLM-TTS combination.

    Turn boundary is `LLMFullResponseEndFrame` - exactly one per completion on
    every LLM backend, which is the same thing Gemini Live calls a turn. Must sit
    downstream of the LLM service that emits it.

    A barge-in while the LLM is still generating also closes a turn: the bot
    spoke and tokens were spent, so it counts. Whether the aborted completion
    still emits its end frame is backend-dependent, hence the suppression flag.
    """

    def __init__(self):
        super().__init__()
        self._turn_count = 0
        self._response_in_flight = False
        self._counted_on_interrupt = False

    async def _count_turn(self, interrupted: bool = False):
        self._turn_count += 1
        self._response_in_flight = False
        suffix = " (interrupted)" if interrupted else ""
        logger.info(f"[TurnMetrics] Bot turn {self._turn_count} complete{suffix}")
        payload = {'type': 'turn_complete', 'turn': self._turn_count}
        if interrupted:
            payload['interrupted'] = True
        await self._emit(payload)

    async def process_frame(self, frame: Frame, direction: FrameDirection = FrameDirection.DOWNSTREAM):
        await super().process_frame(frame, direction)

        if isinstance(frame, LLMFullResponseStartFrame):
            self._response_in_flight = True

        elif isinstance(frame, InterruptionFrame):
            await self._emit({'type': 'interruption', 'count': 1})
            if self._response_in_flight:
                await self._count_turn(interrupted=True)
                self._counted_on_interrupt = True

        elif isinstance(frame, LLMFullResponseEndFrame):
            if self._counted_on_interrupt:
                # Already counted when the user barged in.
                self._counted_on_interrupt = False
                self._response_in_flight = False
            else:
                await self._count_turn()

        await self.push_frame(frame, direction)


class StartTriggerProcessor(FrameProcessor):
    def __init__(self, context, context_aggregator, skip_stt: bool):
        super().__init__()
        self.context = context
        self.context_aggregator = context_aggregator
        self.skip_stt = skip_stt
        self.triggered = False

    async def process_frame(self, frame: Frame, direction: FrameDirection = FrameDirection.DOWNSTREAM):
        await super().process_frame(frame, direction)
        if isinstance(frame, InputTransportMessageFrame):
            message = frame.message
            if isinstance(message, dict) and message.get("type") == "start_trigger":
                msg_id = message.get("id")
                if msg_id:
                    await self.push_frame(OutputTransportMessageFrame(message={
                        "label": "rtvi-ai",
                        "type": "response",
                        "id": msg_id,
                        "data": {"status": "ok"}
                    }))
                if not self.triggered:
                    self.triggered = True
                    logger.info("[StartTriggerProcessor] start_trigger received. Queueing initial greeting turn.")
                    await self.push_frame(LLMRunFrame())
                return
        await self.push_frame(frame, direction)


async def run_agent(
    websocket: WebSocket,
    tts_voice: str,
    tts_pace: float,
    llm_model: str = "gemini-3.5-flash-lite",
    stt_model: str = "gemini-3.5-transcribe-live-aistudio",
    stt_language: str = "en-US",
    tts_model: str = "gemini-3.1-flash-tts-preview",
    tts_voice_prompt: Optional[str] = None,
    system_instruction: Optional[str] = None,
    skip_stt: bool = False,
):
    project_id = os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT") or "deep-clock-339817"
    location = os.getenv("GCP_LOCATION") or os.getenv("GOOGLE_CLOUD_LOCATION") or "us-central1"

    vad_analyzer = SileroVADAnalyzer(
        params=VADParams(
            confidence=0.7,
            start_secs=0.2,
            stop_secs=0.4,
            min_volume=0.6,
        )
    )
    vad_processor = VADProcessor(vad_analyzer=vad_analyzer)

    transport = FastAPIWebsocketTransport(
        websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            serializer=CustomProtobufSerializer(),
        ),
    )

    clean_stt_model = validate_stt_model(stt_model)
    clean_llm_model = validate_llm_model(llm_model)
    clean_tts_model = validate_tts_model(tts_model)

    stt = None
    if not skip_stt:
        stt_languages = [Language(lang.strip()) for lang in stt_language.split(',')] if stt_language else [Language("en-US"), Language("hi-IN")]
        if clean_stt_model.startswith("gemini-3.5-transcribe"):
            is_ai_studio = False
            if "aistudio" in clean_stt_model:
                is_ai_studio = True
            elif not clean_stt_model.endswith("-preview") and os.getenv("GEMINI_API_KEY"):
                is_ai_studio = True

            gemini_api_key = os.getenv("GEMINI_API_KEY")
            if is_ai_studio and not gemini_api_key:
                try:
                    from google.cloud import secretmanager
                    sm_client = secretmanager.SecretManagerServiceClient()
                    sm_name = f"projects/{project_id}/secrets/GEMINI_API_KEY/versions/latest"
                    sm_res = sm_client.access_secret_version(request={"name": sm_name})
                    gemini_api_key = sm_res.payload.data.decode("UTF-8").strip()
                    if gemini_api_key:
                        os.environ["GEMINI_API_KEY"] = gemini_api_key
                except Exception as sm_err:
                    logger.debug(f"[SecretManager] Dynamic GEMINI_API_KEY retrieval note: {sm_err}")

            stt_loc = "global" if not is_ai_studio else location
            stt = CustomGeminiTranscribeLiveService(
                project_id=project_id,
                location=stt_loc,
                api_key=gemini_api_key,
                model=clean_stt_model,
                languages=stt_languages,
                is_ai_studio=is_ai_studio,
            )
        elif clean_stt_model in SARVAM_STT_MODELS:
            sarvam_api_key = os.getenv("SARVAM_API_KEY")
            if not sarvam_api_key:
                raise ValueError("SARVAM_API_KEY environment variable not set")

            from pipecat.services.sarvam.stt import SarvamSTTService

            # Sarvam auto-detects the spoken language when none is set, which is what
            # lets the multilingual prompt switch languages mid-call. Only pin a single
            # language if the caller explicitly narrowed the selection to just one.
            sarvam_stt_language = stt_languages[0] if len(stt_languages) == 1 else None
            stt = SarvamSTTService(
                api_key=sarvam_api_key,
                settings=SarvamSTTService.Settings(
                    model=clean_stt_model,
                    language=sarvam_stt_language,
                ),
                sample_rate=16000,
            )
        elif clean_stt_model in SMALLEST_STT_MODELS:
            smallest_api_key = os.getenv("SMALLEST_API_KEY")
            if not smallest_api_key:
                raise ValueError("SMALLEST_API_KEY environment variable not set")

            from pipecat.services.smallest.stt import SmallestSTTService

            # Pulse takes a single language code. Its Hindi model also transcribes
            # English (and Hinglish) correctly, and its South-Indic model detects
            # between Tamil/Telugu/Kannada/Malayalam, so one code per group is enough.
            # The documented "multi-south-indic" aggregator is deliberately not used:
            # it returns Latin-transliterated gibberish for every one of these
            # languages, including the South Indian ones it is meant to cover.
            if len(stt_languages) == 1:
                smallest_stt_language = stt_languages[0]
            else:
                base_codes = {str(l.value).split("-")[0].lower() for l in stt_languages}
                if base_codes and base_codes <= SMALLEST_SOUTH_INDIC_CODES:
                    smallest_stt_language = Language.TA
                else:
                    smallest_stt_language = Language.HI

            stt = SmallestSTTService(
                api_key=smallest_api_key,
                settings=SmallestSTTService.Settings(
                    model="pulse",
                    language=smallest_stt_language,
                ),
                sample_rate=16000,
            )
        else:
            # chirp_3 is hosted in US multi-region ("us"), while chirp_2 is in us-central1
            stt_loc = "us-central1" if ("chirp_2" in clean_stt_model) else "us"
            stt = CustomGoogleSTTService(
                vertexai_project=project_id,
                location=stt_loc,
                settings=GoogleSTTService.Settings(
                    languages=stt_languages,
                    model=clean_stt_model,
                    enable_interim_results=True,
                )
            )

    final_system_instruction = system_instruction or SYSTEM_PROMPT
    if tts_model.startswith("gemini"):
        final_system_instruction += "\n\n" + GEMINI_LLM_TTS_PROMPT

    if skip_stt:
        final_system_instruction += "\n\nIMPORTANT: The user's input is raw audio. Listen to it and respond naturally. Strictly answer ONLY the current current user query. Do not bring up previous topics or simulate future turns."

    if clean_llm_model in SMALLEST_LLM_MODELS:
        smallest_api_key = os.getenv("SMALLEST_API_KEY")
        if not smallest_api_key:
            raise ValueError("SMALLEST_API_KEY environment variable not set")
        if skip_stt:
            raise ValueError(
                "Skip STT sends raw audio to the LLM, which Electron does not accept. "
                "Turn off Skip STT to use Electron, or pick a Gemini LLM."
            )

        llm = CustomSmallestLLMService(
            api_key=smallest_api_key,
            base_url=SMALLEST_LLM_BASE_URL,
            settings=OpenAILLMService.Settings(
                model=clean_llm_model,
                system_instruction=final_system_instruction,
                max_tokens=4096,
            )
        )
    else:
        llm_location = "global" if any(k in clean_llm_model for k in ["gemini-3", "3.7", "3.5"]) else location

        thinking_config = None
        if "gemini-3.7" in clean_llm_model:
            thinking_config = GoogleLLMService.ThinkingConfig(thinking_budget=0)
        elif any(k in clean_llm_model for k in ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3-flash"]):
            thinking_config = GoogleLLMService.ThinkingConfig(thinking_level="minimal")
        elif any(k in clean_llm_model for k in ["gemini-2.5-flash", "gemini-2.5-flash-lite"]):
            thinking_config = GoogleLLMService.ThinkingConfig(thinking_budget=0)

        llm = CustomGoogleVertexLLMService(
            project_id=project_id,
            location=llm_location,
            settings=GoogleVertexLLMService.Settings(
                model=clean_llm_model,
                system_instruction=final_system_instruction,
                max_tokens=1024 if thinking_config else 4096,
                thinking=thinking_config
            )
        )

    sarvam_tts_session: Optional[aiohttp.ClientSession] = None
    if clean_tts_model.startswith("gemini"):
        # Use Gemini TTS (Vertex AI) requires 24kHz
        tts_location = "global" if "gemini-3" in clean_tts_model else location

        tts_lang = "hi-IN"
        if stt_language:
            langs = [l.strip() for l in stt_language.split(",")]
            hi_lang = next((l for l in langs if "hi" in l.lower()), None)
            tts_lang = hi_lang if hi_lang else langs[0]

        tts = CustomVertexGeminiTTSService(
            project_id=project_id,
            location=tts_location,
            voice_id=tts_voice,
            model=clean_tts_model, # Use the sanitized model
            sample_rate=24000,
            voice_prompt=tts_voice_prompt,
            language_code=tts_lang,
            text_filters=[MarkdownTextFilter()]
        )
    elif clean_tts_model in SARVAM_TTS_MODELS:
        tts_lang = "hi-IN"
        if stt_language:
            langs = [l.strip() for l in stt_language.split(",")]
            hi_lang = next((l for l in langs if "hi" in l.lower()), None)
            tts_lang = hi_lang if hi_lang else langs[0]

        sarvam_api_key = os.getenv("SARVAM_API_KEY")
        if not sarvam_api_key:
            raise ValueError("SARVAM_API_KEY environment variable not set")

        from pipecat.services.sarvam.tts import SarvamHttpTTSService

        sarvam_tts_session = aiohttp.ClientSession()
        tts = CustomSarvamTTSService(
            api_key=sarvam_api_key,
            aiohttp_session=sarvam_tts_session,
            settings=CustomSarvamTTSService.Settings(
                model=clean_tts_model,
                voice=tts_voice,
                language=Language(tts_lang),
                pace=tts_pace,
            ),
            text_filters=[MarkdownTextFilter()],
        )
    elif clean_tts_model in SMALLEST_TTS_MODELS:
        smallest_api_key = os.getenv("SMALLEST_API_KEY")
        if not smallest_api_key:
            raise ValueError("SMALLEST_API_KEY environment variable not set")

        # "auto" is Smallest's cross-language mode: it detects the language of each
        # chunk of text and code-switches, which is what the multilingual prompt needs.
        # Pipecat has no Language enum for it, so it goes through as a raw string.
        tts = CustomSmallestTTSService(
            api_key=smallest_api_key,
            settings=CustomSmallestTTSService.Settings(
                model=clean_tts_model,
                voice=tts_voice,
                language="auto",
                speed=tts_pace,
            ),
            text_filters=[MarkdownTextFilter()],
        )
    elif tts_voice in ["Custom-Male", "Custom-Female"]:
        # For cloned voices, use en-US as the base language code
        # The voice cloning will handle the accent/style
        tts_language = "en-US"
        if tts_voice == "Custom-Male":
            voice_key_path = os.getenv("CLONE_TTS_VOICE_KEY_MALE")
            if not voice_key_path:
                raise ValueError("CLONE_TTS_VOICE_KEY_MALE environment variable not set")
            with open(voice_key_path, "r") as f:
                key = f.read()
            tts = CustomGoogleTTSService(
                voice_cloning_key=key,
                params=GoogleTTSService.InputParams(
                    language=Language(tts_language),
                    speaking_rate=tts_pace
                ),
                text_filters=[MarkdownTextFilter()],
            )
        else:  # Custom-Female
            voice_key_path = os.getenv("CLONE_TTS_VOICE_KEY_FEMALE")
            if not voice_key_path:
                raise ValueError("CLONE_TTS_VOICE_KEY_FEMALE environment variable not set")
            with open(voice_key_path, "r") as f:
                key = f.read()
            tts = CustomGoogleTTSService(
                voice_cloning_key=key,
                params=GoogleTTSService.InputParams(
                    language=Language(tts_language),
                    speaking_rate=tts_pace
                ),
                text_filters=[MarkdownTextFilter()],
            )
    else:
        tts_language = "-".join(tts_voice.split("-")[:2])
        tts = CustomGoogleTTSService(
            voice_id=tts_voice,
            params=GoogleTTSService.InputParams(
                language=Language(tts_language),
                speaking_rate=tts_pace
            ),
            text_filters=[MarkdownTextFilter()],
        )

    is_hindi = bool(stt_language and any(l in stt_language.lower() for l in ["hi", "hindi"]))
    initial_greeting = "नमस्ते!" if is_hindi else "Hello!"

    if skip_stt:
        from pipecat.services.google.llm import GoogleLLMContext
        from processors.audio_accumulator import AudioAccumulator
        context = GoogleLLMContext()
        context.set_messages([
            {"role": "system", "content": final_system_instruction},
            {"role": "user", "content": initial_greeting}
        ])
        stt_languages = [lang.strip() for lang in stt_language.split(',')] if stt_language else ["en-US"]
        accumulator = AudioAccumulator(
            context,
            project_id=project_id,
            stt_languages=stt_languages,
        )
        context_aggregator = LLMContextAggregatorPair(context)
        start_trigger = StartTriggerProcessor(context, context_aggregator, skip_stt=True)

        pipeline_elements = [
            transport.input(),
            start_trigger,
            accumulator,
            llm,
            TurnMetricsProcessor(),
            TranscriptionBroadcaster(participant="Bot"),
            tts,
            context_aggregator.assistant(),
            transport.output()
        ]
    else:
        context = LLMContext(messages=[
            {"role": "system", "content": final_system_instruction},
            {"role": "user", "content": initial_greeting}
        ])
        user_params = LLMUserAggregatorParams(
            vad_analyzer=vad_analyzer,
        )
        context_aggregator = LLMContextAggregatorPair(context, user_params=user_params)
        start_trigger = StartTriggerProcessor(context, context_aggregator, skip_stt=False)

        pipeline_elements = [
            transport.input(),
            start_trigger,
            vad_processor,
            stt,
            # Must precede context_aggregator.user(): it swallows TranscriptionFrame.
            STTLatencyProcessor(),
            TranscriptionBroadcaster(participant="User"),
            context_aggregator.user(),
            llm,
            TurnMetricsProcessor(),
            TranscriptionBroadcaster(participant="Bot"),
            tts,
            context_aggregator.assistant(),
            transport.output()
        ]

    pipeline = Pipeline(pipeline_elements)

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
            report_only_initial_ttfb=False,
            audio_in_sample_rate=16000,
        ),
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Pipecat Client connected to STT-LLM-TTS pipeline")
        # Tell the Observability tab which stack these numbers belong to, so the
        # per-model cards are labelled rather than just "current session".
        await task.queue_frame(OutputTransportMessageFrame(message={
            "label": "rtvi-ai",
            "type": "server-message",
            "data": {
                'type': 'session_config',
                'config': {
                    'pipeline': 'stt-llm-tts',
                    'stt': 'n/a (audio to LLM)' if skip_stt else clean_stt_model,
                    'llm': clean_llm_model,
                    'tts': clean_tts_model,
                    'voice': tts_voice,
                }
            }
        }))
        # Defer greeting until start_trigger message is received when user clicks Start Listening

    runner = PipelineRunner(handle_sigint=False)
    try:
        await runner.run(task)
    finally:
        if sarvam_tts_session is not None:
            await sarvam_tts_session.close()
