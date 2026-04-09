import asyncio
import random
import time
from loguru import logger

from pipecat.frames.frames import (
    Frame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    TTSSpeakFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)

from pipecat.pipeline.pipeline import FrameDirection
from pipecat.processors.frame_processor import FrameProcessor
from pipecat.processors.transcript_processor import TranscriptionUpdateFrame
from app.schemas.services.agent import FillerWordsConfig


class FillerWordsProcessor(FrameProcessor):
    def __init__(self, config: FillerWordsConfig):
        super().__init__()
        self._config = config

        self._timer_task = None
        self._last_user_text: str | None = None
        self._transcript_timestamp: float | None = None
        self._accumulated_user_text: list[str] = []
        self._waiting_for_user_stop: bool = False
        self._user_stopped_speaking: bool = False
        self._vad_fallback_task: asyncio.Task | None = None
        self._vad_fallback_timeout: float = 2.0
        
        if config.enabled:
            logger.info(f"[Filler] Initialized - Delay: {config.delay_seconds}s")
    
    def _is_task_still_active(self, current_task) -> bool:
        """Check if the current task is still the active filler task."""
        if self._timer_task is None:
            return False
        if self._timer_task is not current_task:
            return False
        if current_task.done():
            return False
        if self._transcript_timestamp is None:
            return False
        return True

    async def _speak_filler(self, accumulated_text: str | None = None):
        """Start Groq call with accumulated text (if VAD detected user stopped) or immediately (if not using VAD)."""
        transcript_timestamp = self._transcript_timestamp
        if not transcript_timestamp:
            logger.warning("[Filler] No transcript timestamp available - cannot proceed")
            return

        phrase = None
        groq_start_time: float | None = None
        
        user_text_for_groq = accumulated_text if accumulated_text else self._last_user_text
        
        if self._config.enabled and user_text_for_groq:
            try:
                from app.services.sllm.base_small_talk import small_talk_response

                llm_config = self._config.sllm_config
                groq_start_time = time.perf_counter()
                
                try:
                    phrase = await small_talk_response(
                        user_text=user_text_for_groq,
                        llm_config=llm_config,
                        system_prompt=llm_config.system_prompt,
                    )
                    if not phrase:
                        logger.warning("[Filler] Groq returned None, falling back to random phrase")
                except asyncio.CancelledError:
                    raise
            except asyncio.CancelledError:
                return
            except Exception as e:
                if groq_start_time is not None:
                    groq_duration = (time.perf_counter() - groq_start_time) * 1000
                    logger.error(f"[Filler] Groq error after {groq_duration:.2f}ms: {e}", exc_info=True)
                else:
                    logger.error(f"[Filler] Groq error: {e}", exc_info=True)

        if not phrase:
            phrase = random.choice(self._config.filler_phrases)

        elapsed_time = time.perf_counter() - transcript_timestamp
        delay_ms = self._config.delay_seconds * 1000

        if elapsed_time >= self._config.delay_seconds:
            current_task = asyncio.current_task()
            if not self._is_task_still_active(current_task):
                return
            
            await self.push_frame(TTSSpeakFrame(phrase))
            logger.info(f"[Filler] Filler phrase sent: \"{phrase}\"")
        else:
            remaining_time = self._config.delay_seconds - elapsed_time
            try:
                await asyncio.sleep(remaining_time)
                
                current_task = asyncio.current_task()
                if not self._is_task_still_active(current_task):
                    return
                
                await self.push_frame(TTSSpeakFrame(phrase))
                logger.info(f"[Filler] Filler phrase sent: \"{phrase}\"")
            except asyncio.CancelledError:
                raise

    async def process_frame(self, frame: Frame, direction):
        await super().process_frame(frame, direction)

        frame_name = type(frame).__name__
       
        if not self._config.enabled:
            return

        if direction == FrameDirection.DOWNSTREAM and isinstance(frame, TranscriptionUpdateFrame):
            messages = getattr(frame, "messages", [])
            
            user_found = False
            for message in reversed(messages):
                role = getattr(message, "role", None)
                if role == "user":
                    text = getattr(message, "text", "") or getattr(message, "content", "")
                    if text and len(str(text).strip()) > 0:
                        user_text = str(text).strip()
                        self._last_user_text = user_text
                        
                        if user_text not in self._accumulated_user_text:
                            self._accumulated_user_text.append(user_text)
                        
                        if self._transcript_timestamp is None:
                            self._transcript_timestamp = time.perf_counter()
                            
                            if self._user_stopped_speaking:
                                complete_text = " ".join(self._accumulated_user_text).strip()
                                
                                if self._vad_fallback_task and not self._vad_fallback_task.done():
                                    self._vad_fallback_task.cancel()
                                    self._vad_fallback_task = None
                                
                                if self._timer_task and not self._timer_task.done():
                                    self._timer_task.cancel()
                                
                                self._timer_task = asyncio.create_task(self._speak_filler(accumulated_text=complete_text))
                                self._waiting_for_user_stop = False
                                self._user_stopped_speaking = False
                            else:
                                self._waiting_for_user_stop = True
                                
                                if self._vad_fallback_task and not self._vad_fallback_task.done():
                                    self._vad_fallback_task.cancel()
                                
                                async def vad_fallback():
                                    await asyncio.sleep(self._vad_fallback_timeout)
                                    if self._waiting_for_user_stop and self._accumulated_user_text and not self._user_stopped_speaking:
                                        complete_text = " ".join(self._accumulated_user_text).strip()
                                        
                                        if self._timer_task and not self._timer_task.done():
                                            self._timer_task.cancel()
                                        
                                        self._timer_task = asyncio.create_task(self._speak_filler(accumulated_text=complete_text))
                                        self._waiting_for_user_stop = False
                                
                                self._vad_fallback_task = asyncio.create_task(vad_fallback())
                        
                        if self._timer_task and not self._timer_task.done():
                            self._timer_task.cancel()
                        
                        user_found = True
                        break
        
        if isinstance(frame, UserStartedSpeakingFrame):
            if self._accumulated_user_text:
                self._accumulated_user_text = []
                self._waiting_for_user_stop = False
                self._user_stopped_speaking = False
                self._transcript_timestamp = None
                if self._vad_fallback_task and not self._vad_fallback_task.done():
                    self._vad_fallback_task.cancel()
                    self._vad_fallback_task = None
        
        if isinstance(frame, UserStoppedSpeakingFrame):
            self._user_stopped_speaking = True
            
            if self._accumulated_user_text:
                if self._vad_fallback_task and not self._vad_fallback_task.done():
                    self._vad_fallback_task.cancel()
                    self._vad_fallback_task = None
                
                complete_text = " ".join(self._accumulated_user_text).strip()
                
                if self._timer_task and not self._timer_task.done():
                    self._timer_task.cancel()
                
                self._timer_task = asyncio.create_task(self._speak_filler(accumulated_text=complete_text))
                self._waiting_for_user_stop = False
                self._user_stopped_speaking = False

        if frame_name == "OpenAILLMContextFrame" or isinstance(frame, (LLMFullResponseStartFrame, LLMTextFrame)):
            if self._timer_task and not self._timer_task.done():
                self._timer_task.cancel()
                self._timer_task = None
                self._transcript_timestamp = None
                self._accumulated_user_text = []
                self._waiting_for_user_stop = False
                self._user_stopped_speaking = False
                if self._vad_fallback_task and not self._vad_fallback_task.done():
                    self._vad_fallback_task.cancel()
                    self._vad_fallback_task = None

        if isinstance(frame, TTSSpeakFrame):
            if self._timer_task and not self._timer_task.done():
                self._timer_task.cancel()
                self._timer_task = None
                self._transcript_timestamp = None
                self._accumulated_user_text = []
                self._waiting_for_user_stop = False
                self._user_stopped_speaking = False
                if self._vad_fallback_task and not self._vad_fallback_task.done():
                    self._vad_fallback_task.cancel()
                    self._vad_fallback_task = None

        await self.push_frame(frame, direction)