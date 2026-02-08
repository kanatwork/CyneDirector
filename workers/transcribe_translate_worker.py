# [FILE: workers/transcribe_translate_worker.py]
import os
from PyQt6.QtCore import QThread, pyqtSignal
from core.ai_models import AIBackend
from core.database import Database
from core.translator import (
    get_translator, 
    merge_transcript_segments,
    split_into_sentences,
    detect_language,
    is_english,
    filter_english_segments
)
from core.logger import get_logger

logger = get_logger(__name__)


class TranscribeTranslateWorker(QThread):
    """Worker thread for transcribing and translating audio."""
    
    # Signals
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(bool, str)  # success, error message
    transcription_complete_signal = pyqtSignal(list)  # original language segments
    translation_complete_signal = pyqtSignal(list)  # translated segments
    
    def __init__(self, video_path: str, project_path: str, deepl_api_key: str = None, 
                 mode: str = "accuracy", should_transcribe: bool = True, should_translate: bool = False):
        """
        Initialize worker.
        
        Args:
            video_path: Path to video file
            project_path: Project path for database
            deepl_api_key: DeepL API key (optional)
            mode: "speed" or "accuracy" for transcription
            should_transcribe: Whether to transcribe (in original language)
            should_translate: Whether to translate to English
        """
        super().__init__()
        self.video_path = video_path
        self.project_path = project_path
        self.deepl_api_key = deepl_api_key
        self.mode = mode
        self.should_transcribe = should_transcribe
        self.should_translate = should_translate
        self.is_running = True
    
    def stop(self):
        """Stop the worker."""
        self.is_running = False
    
    def run(self):
        """Main worker execution."""
        try:
            db = Database(self.project_path)
            ai = AIBackend()
            
            original_segments = None
            translated_segments = None
            
            # Step 1: Transcribe if requested
            if self.should_transcribe:
                self.log_signal.emit("Checking for existing transcript...")
                self.progress_signal.emit(5)
                
                meta = db.get_video_metadata(self.video_path)
                transcript = meta.get("transcript", [])
                
                # Transcribe if needed
                if not transcript or not isinstance(transcript, list) or len(transcript) == 0:
                    self.log_signal.emit("Transcribing audio in original language...")
                    original_segments = self._transcribe_audio(ai, db)
                    if not original_segments:
                        self.finished_signal.emit(False, "Transcription failed")
                        return
                else:
                    self.log_signal.emit(f"Found existing transcript with {len(transcript)} segments")
                    original_segments = transcript
                
                # Emit transcription complete signal
                self.transcription_complete_signal.emit(original_segments)
                self.progress_signal.emit(50)
            else:
                # If not transcribing, try to get existing transcript for translation
                meta = db.get_video_metadata(self.video_path)
                original_segments = meta.get("transcript", [])
                if not original_segments:
                    self.finished_signal.emit(False, "No transcript available. Please transcribe first.")
                    return
                self.progress_signal.emit(50)
            
            # Step 2: Translate if requested
            if self.should_translate:
                if not original_segments:
                    self.finished_signal.emit(False, "No transcript available for translation.")
                    return
                
                if not isinstance(original_segments, list) or len(original_segments) == 0:
                    self.finished_signal.emit(False, "Transcript is empty or invalid.")
                    return
                
                self.log_signal.emit(f"Starting translation of {len(original_segments)} segments...")
                translated_segments = self._translate_transcript(original_segments, ai)
                
                if not translated_segments:
                    self.finished_signal.emit(False, "Translation failed - no segments returned")
                    return
                
                if len(translated_segments) == 0:
                    self.finished_signal.emit(False, "Translation failed - empty result")
                    return
                
                # Phase 3: Validate segment count matches original
                original_count = len(original_segments)
                translated_count = len(translated_segments)
                if translated_count < original_count:
                    self.log_signal.emit(f"Warning: Translation returned {translated_count} segments, but original had {original_count}. Some segments may be missing.")
                    logger.warning(f"Segment count mismatch after translation: original={original_count}, translated={translated_count}")
                elif translated_count > original_count:
                    self.log_signal.emit(f"Info: Translation returned {translated_count} segments (original had {original_count}). This is normal if sentences were split.")
                else:
                    self.log_signal.emit(f"Translation complete: {translated_count} segments (matches original)")
                
                # Verify translation actually changed something
                original_text = ' '.join(seg.get('text', '') for seg in original_segments)
                translated_text = ' '.join(seg.get('text', '') for seg in translated_segments)
                if original_text == translated_text:
                    self.log_signal.emit("Warning: Translation returned identical text. This may indicate translation failed.")
                
                # Validate that translation actually removed non-English text
                # Check if any segments still contain Hindi (Devanagari script)
                hindi_segments = []
                for seg in translated_segments:
                    text = seg.get('text', '')
                    if any('\u0900' <= char <= '\u097F' for char in text):
                        hindi_segments.append(seg)
                
                if hindi_segments:
                    self.log_signal.emit(f"Warning: {len(hindi_segments)} segments still contain Hindi text after translation. This may indicate translation failed.")
                    logger.warning(f"Translation validation failed: {len(hindi_segments)} segments still contain Hindi")
                    # Try to filter them out or mark them for retry
                    # For now, we'll continue but log the issue
                
                # Format translated segments (pass original segments for fallback)
                self.log_signal.emit(f"Formatting {len(translated_segments)} translated segments...")
                formatted_segments = self._format_translated_segments(translated_segments, original_segments)
                
                # Final validation: check for Hindi but don't filter - just warn
                # We want to preserve all segments, even if translation partially failed
                final_hindi_count = sum(1 for seg in formatted_segments if any('\u0900' <= char <= '\u097F' for char in seg.get('text', '')))
                if final_hindi_count > 0:
                    self.log_signal.emit(f"Warning: {final_hindi_count} formatted segments still contain Hindi text (translation may be incomplete)")
                    logger.warning(f"Formatted segments validation: {final_hindi_count} segments still contain Hindi")
                    # Don't filter them out - keep them but mark them
                    for seg in formatted_segments:
                        if any('\u0900' <= char <= '\u097F' for char in seg.get('text', '')):
                            seg['translation_failed'] = True
                            # Add a note to the text
                            seg['text'] = f"[Translation incomplete] {seg.get('text', '')}"
                
                if not formatted_segments:
                    # Log detailed error information
                    logger.error(f"Failed to format translated segments. Input had {len(translated_segments)} segments.")
                    if translated_segments:
                        logger.error(f"First segment sample: {translated_segments[0] if translated_segments else 'N/A'}")
                    self.finished_signal.emit(False, f"Failed to format translated segments (input had {len(translated_segments)} segments, but formatting returned empty)")
                    return
                
                # Phase 3: Final validation - ensure formatted segment count matches original
                final_count = len(formatted_segments)
                if final_count < original_count:
                    self.log_signal.emit(f"Warning: After formatting, {final_count} segments remain (original had {original_count}). Missing segments have been preserved with fallback text.")
                    logger.warning(f"Final segment count after formatting: {final_count} (original: {original_count})")
                elif final_count == original_count:
                    self.log_signal.emit(f"Success: All {final_count} segments preserved in translation")
                else:
                    self.log_signal.emit(f"Info: Formatted segments: {final_count} (original: {original_count})")
                
                # Save translated transcript to database with translation method and timestamp
                self.log_signal.emit("Saving translated transcript to database...")
                db.update_metadata_key(self.video_path, "transcript_translated", formatted_segments)
                # Store translation method and timestamp for tracking
                translation_method = getattr(self, '_translation_method_used', 'whisper')
                db.update_metadata_key(self.video_path, "translation_method", translation_method)
                import time
                db.update_metadata_key(self.video_path, "translation_timestamp", time.time())
                
                self.log_signal.emit(f"Translation complete! Method: {translation_method}, Segments: {len(formatted_segments)}")
                
                # Emit translation complete signal
                self.translation_complete_signal.emit(formatted_segments)
                self.progress_signal.emit(95)
            
            self.progress_signal.emit(100)
            self.log_signal.emit("Processing complete!")
            
            # Emit success
            self.finished_signal.emit(True, "")
            
        except Exception as e:
            logger.error(f"TranscribeTranslateWorker error: {e}")
            self.finished_signal.emit(False, str(e))
    
    def _transcribe_audio(self, ai: AIBackend, db: Database) -> list:
        """Transcribe audio if not already done."""
        try:
            self.log_signal.emit("Loading Whisper model...")
            
            if self.mode == "accuracy":
                model = ai.load_whisper()
            else:
                model_name, whisper_device, compute_type = ai.get_whisper_params("speed")
                from faster_whisper import WhisperModel
                try:
                    model = WhisperModel(model_name, device=whisper_device, compute_type=compute_type)
                except Exception:
                    model = WhisperModel("large-v3", device=whisper_device, compute_type=compute_type)
            
            self.log_signal.emit("Transcribing audio in original language...")
            # Don't use task="translate" here - we want the original language
            # More sensitive VAD to catch all dialogue
            segments, info = model.transcribe(
                self.video_path,
                beam_size=5,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=200)  # More sensitive
            )
            
            # Capture detected language from Whisper
            detected_language = getattr(info, 'language', None)
            if detected_language:
                self.log_signal.emit(f"Detected language: {detected_language}")
                db.update_metadata_key(self.video_path, "transcript_language", detected_language)
            
            segment_list = []
            from core.translator import detect_segment_language
            for segment in segments:
                if not self.is_running:
                    break
                
                text = segment.text.strip()
                if text:
                    seg_dict = {
                        "start": segment.start,
                        "end": segment.end,
                        "text": text
                    }
                    # Detect and store language for each segment
                    detect_segment_language(seg_dict)
                    segment_list.append(seg_dict)
            
            # Detect gaps in transcription
            # Estimate duration from last segment end time (add small buffer)
            duration = segment_list[-1]['end'] + 1.0 if segment_list else 0
            
            from core.translator import detect_transcription_gaps
            gaps = detect_transcription_gaps(segment_list, duration, max_gap_seconds=2.0)
            if gaps:
                total_gap_time = sum(g['duration'] for g in gaps)
                self.log_signal.emit(f"Warning: Detected {len(gaps)} potential gaps totaling {total_gap_time:.1f}s")
                db.update_metadata_key(self.video_path, "transcription_gaps", gaps)
            
            # Save transcript to database
            if segment_list:
                db.save_transcript(self.video_path, segment_list)
                self.log_signal.emit(f"Saved {len(segment_list)} transcript segments")
            
            return segment_list
            
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            self.log_signal.emit(f"Transcription error: {e}")
            return []
    
    def _translate_transcript(self, transcript: list, ai: AIBackend) -> list:
        """Translate transcript to English. Tries DeepL first, falls back to Whisper.
        Intelligently handles mixed-language transcripts by only translating non-English segments."""
        from core.translator import detect_segment_language, translate_mixed_language_transcript
        
        # Detect language for all segments if not already done
        english_count = 0
        non_english_count = 0
        for seg in transcript:
            lang = detect_segment_language(seg)
            if lang == 'en':
                english_count += 1
            elif lang:
                non_english_count += 1
        
        self.log_signal.emit(f"Analyzing transcript: {english_count} English segments, {non_english_count} non-English segments")
        
        # If all segments are English, no translation needed
        if non_english_count == 0:
            self.log_signal.emit("All segments are already in English. No translation needed.")
            # Return segments with language marked as English
            for seg in transcript:
                seg['language'] = 'en'
            return transcript
        
        # Try DeepL first
        deepl_translator = get_translator(self.deepl_api_key)
        
        # Add explicit logging
        if self.deepl_api_key:
            self.log_signal.emit(f"DeepL API key provided: {self.deepl_api_key[:10]}...")
        else:
            self.log_signal.emit("No DeepL API key provided")
        
        # Attempt DeepL translation if available
        if deepl_translator and deepl_translator.available:
            try:
                self.log_signal.emit("Using DeepL API for translation (translating only non-English segments)...")
                self._translation_method_used = 'deepl'  # Track method used
                
                # Create translator function for mixed-language translation
                def deepl_translate_func(text):
                    return deepl_translator.translate(text)
                
                # Use mixed-language translation (keeps English segments unchanged)
                return translate_mixed_language_transcript(transcript, deepl_translate_func)
                
            except Exception as deepl_error:
                # Enhanced error handling for DeepL
                error_msg = str(deepl_error).lower()
                if "quota" in error_msg or "limit" in error_msg:
                    self.log_signal.emit("DeepL API rate limit reached. Falling back to Whisper translation...")
                    self._translation_method_used = 'whisper'
                elif "invalid" in error_msg or "auth" in error_msg or "key" in error_msg:
                    self.log_signal.emit("DeepL API key is invalid or expired. Falling back to Whisper translation...")
                    self._translation_method_used = 'whisper'
                else:
                    self.log_signal.emit(f"DeepL translation error: {deepl_error}. Falling back to Whisper...")
                    self._translation_method_used = 'whisper'
                # Fall through to Whisper
        else:
            if deepl_translator:
                self.log_signal.emit("DeepL translator not available (check logs for reason)")
            else:
                self.log_signal.emit("Failed to create DeepL translator")
        
        # Fallback: Use Whisper's built-in translation
        # Note: Whisper translate requires re-transcribing the audio with task="translate"
        self.log_signal.emit("Falling back to Whisper built-in translation (re-transcribing with translate mode)...")
        self._translation_method_used = 'whisper'  # Track method used
        return self._translate_with_whisper(transcript, ai)
    
    def _translate_with_deepl(self, deepl_translator, transcript: list) -> list:
        """Translate using DeepL API."""
        # Merge segments and translate
        merged_text = merge_transcript_segments(transcript)
        
        if not merged_text or not merged_text.strip():
            self.log_signal.emit("Warning: No text to translate")
            return []
        
        # Translate in chunks if text is too long (DeepL has character limits)
        max_chunk_size = 50000  # DeepL free tier is 500k chars, but be safe
        if len(merged_text) > max_chunk_size:
            self.log_signal.emit("Text is long, translating in chunks...")
            translated_chunks = []
            chunk_count = (len(merged_text) + max_chunk_size - 1) // max_chunk_size
            for i in range(0, len(merged_text), max_chunk_size):
                if not self.is_running:
                    break
                chunk = merged_text[i:i+max_chunk_size]
                chunk_num = (i // max_chunk_size) + 1
                self.log_signal.emit(f"Translating chunk {chunk_num}/{chunk_count}...")
                
                # Retry logic for chunk translation
                max_retries = 3
                retry_count = 0
                translated_chunk = None
                while retry_count < max_retries:
                    try:
                        translated_chunk = deepl_translator.translate(chunk)
                        break
                    except Exception as chunk_error:
                        retry_count += 1
                        if retry_count < max_retries:
                            self.log_signal.emit(f"Chunk {chunk_num} translation failed, retrying ({retry_count}/{max_retries})...")
                            import time
                            time.sleep(1)  # Brief delay before retry
                        else:
                            # If all retries fail, raise to trigger Whisper fallback
                            raise Exception(f"Failed to translate chunk {chunk_num} after {max_retries} attempts: {chunk_error}")
                
                if translated_chunk:
                    translated_chunks.append(translated_chunk)
            
            if translated_chunks:
                translated_text = ' '.join(translated_chunks)
            else:
                raise Exception("All translation chunks failed")
        else:
            self.log_signal.emit(f"Translating {len(merged_text)} characters...")
            translated_text = deepl_translator.translate(merged_text)
        
        self.log_signal.emit(f"Translation complete. Original: {len(merged_text)} chars, Translated: {len(translated_text)} chars")
        
        # Verify translation actually happened (text should be different)
        if translated_text == merged_text:
            self.log_signal.emit("Warning: Translated text is identical to original. Translation may have failed.")
        
        # Verify translation is actually in English
        detected_lang = detect_language(translated_text)
        if detected_lang and detected_lang != 'en':
            self.log_signal.emit(f"Warning: Translation detected as {detected_lang}, not English. Filtering non-English segments...")
        elif detected_lang == 'en':
            self.log_signal.emit("Translation verified as English")
        
        # Split into sentences
        sentences = split_into_sentences(translated_text)
        self.log_signal.emit(f"Split into {len(sentences)} sentences")
        
        # Distribute sentences across original segment timings
        if not transcript:
            return []
        
        total_duration = transcript[-1]['end'] - transcript[0]['start']
        duration_per_sentence = total_duration / len(sentences) if sentences else 0
        
        translated_segments = []
        start_time = transcript[0]['start']
        
        for i, sentence in enumerate(sentences):
            end_time = start_time + duration_per_sentence
            if i == len(sentences) - 1:
                end_time = transcript[-1]['end']
            
            translated_segments.append({
                'start': start_time,
                'end': end_time,
                'text': sentence
            })
            
            start_time = end_time
        
        self.log_signal.emit(f"Created {len(translated_segments)} translated segments")
        return translated_segments
    
    def _translate_with_whisper(self, transcript: list, ai: AIBackend) -> list:
        """Translate using Whisper's built-in translation."""
        try:
            
            # Load Whisper model if not already loaded
            if not ai.whisper_model:
                if self.mode == "accuracy":
                    model = ai.load_whisper()
                else:
                    model_name, whisper_device, compute_type = ai.get_whisper_params("speed")
                    from faster_whisper import WhisperModel
                    try:
                        model = WhisperModel(model_name, device=whisper_device, compute_type=compute_type)
                    except Exception:
                        model = WhisperModel("large-v3", device=whisper_device, compute_type=compute_type)
            else:
                model = ai.whisper_model
            
            # Re-transcribe with translate task - THIS IS KEY: task="translate" translates to English
            self.log_signal.emit("Re-transcribing audio with translation to English...")
            segments, info = model.transcribe(
                self.video_path,
                task="translate",  # This translates to English
                beam_size=5,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=300)
            )
            
            translated_segments = []
            for segment in segments:
                if not self.is_running:
                    break
                text = segment.text.strip()
                if text:
                    translated_segments.append({
                        "start": segment.start,
                        "end": segment.end,
                        "text": text
                    })
            
            # Filter out non-English segments
            original_count = len(translated_segments)
            translated_segments = filter_english_segments(translated_segments)
            filtered_count = original_count - len(translated_segments)
            if filtered_count > 0:
                self.log_signal.emit(f"Filtered out {filtered_count} non-English segments from translation")
            
            self.log_signal.emit(f"Whisper translation complete: {len(translated_segments)} segments")
            return translated_segments
                
        except Exception as e:
            logger.error(f"Whisper translation error: {e}")
            self.log_signal.emit(f"Whisper translation error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # Return empty list to indicate failure, not original transcript
            return []
    
    def _format_translated_segments(self, segments: list, original_segments: list = None) -> list:
        """Format translated segments with proper punctuation and cleaning.
        All segments should already be in English (from mixed-language translation).
        
        Args:
            segments: Translated segments to format
            original_segments: Original segments (for fallback if translated segment is empty)
        """
        if not segments:
            logger.warning("_format_translated_segments: No segments provided")
            return []
        
        # Create a map of original segments by timing for fallback lookup
        original_map = {}
        if original_segments:
            for orig_seg in original_segments:
                start = orig_seg.get('start')
                end = orig_seg.get('end')
                if start is not None and end is not None:
                    # Use start time as key (with small tolerance)
                    key = round(start, 2)
                    original_map[key] = orig_seg
        
        formatted = []
        for seg in segments:
            # Validate segment structure
            if not isinstance(seg, dict):
                logger.warning(f"_format_translated_segments: Invalid segment type: {type(seg)}")
                continue
            
            # Get required fields
            start = seg.get('start')
            end = seg.get('end')
            text = seg.get('text', '').strip()
            
            # Skip if missing required fields
            if start is None or end is None:
                logger.warning(f"_format_translated_segments: Missing start/end in segment: {seg}")
                continue
            
            # Phase 1 Fix: Don't skip empty segments - use original text as fallback
            if not text:
                logger.warning(f"_format_translated_segments: Empty segment at {start}-{end}, attempting to use original text as fallback")
                # Try to find corresponding original segment
                key = round(start, 2)
                if key in original_map:
                    orig_text = original_map[key].get('text', '').strip()
                    if orig_text:
                        text = f"[Translation unavailable - original: {orig_text}]"
                        logger.info(f"Using original text as fallback for empty segment at {start}-{end}")
                    else:
                        text = "[Translation unavailable]"
                else:
                    text = "[Translation unavailable]"
                # Continue processing - don't skip the segment
            
            # For mixed-language translation, segments should already be in English
            # Trust the language field if it's set to 'en', or if translated=True
            # Since we're using translate_mixed_language_transcript, all segments should be English
            lang = seg.get('language', 'en')
            translated_flag = seg.get('translated', False)
            
            # If language is explicitly NOT 'en' AND not translated, check with language detection
            # Otherwise, trust that it's English (from mixed-language translation)
            if lang != 'en' and not translated_flag:
                # Only filter if we're really sure it's not English
                if not is_english(text):
                    logger.debug(f"Filtering non-English segment (lang={lang}): {text[:50]}...")
                    continue
            # If lang is 'en' or translated=True, or if lang is None (defaults to 'en'), assume it's English
            
            # Ensure proper capitalization
            if text and not text[0].isupper():
                text = text[0].upper() + text[1:] if len(text) > 1 else text.upper()
            
            # Ensure sentence ends with punctuation
            if text and text[-1] not in '.!?':
                text += '.'
            
            formatted.append({
                'start': start,
                'end': end,
                'text': text,
                'language': 'en'  # Ensure language is marked as English
            })
        
        # Phase 1 Fix: Validate segment count matches original
        if original_segments:
            original_count = len(original_segments)
            formatted_count = len(formatted)
            if formatted_count < original_count:
                logger.warning(f"_format_translated_segments: Segment count mismatch! Original: {original_count}, Formatted: {formatted_count}")
                self.log_signal.emit(f"Warning: {original_count - formatted_count} segments may be missing from translation")
                # Try to add missing segments from original
                formatted_starts = {round(seg.get('start', 0), 2) for seg in formatted}
                missing_count = 0
                for orig_seg in original_segments:
                    orig_start = round(orig_seg.get('start', 0), 2)
                    if orig_start not in formatted_starts:
                        # Add missing segment with original text marked as untranslated
                        missing_seg = {
                            'start': orig_seg.get('start'),
                            'end': orig_seg.get('end'),
                            'text': f"[Translation unavailable - original: {orig_seg.get('text', '')}]",
                            'language': 'en',
                            'translation_failed': True
                        }
                        formatted.append(missing_seg)
                        missing_count += 1
                if missing_count > 0:
                    logger.info(f"Added {missing_count} missing segments from original transcript")
                    # Sort by start time to maintain chronological order
                    formatted.sort(key=lambda x: x.get('start', 0))
        
        if not formatted:
            logger.error(f"_format_translated_segments: No valid segments after formatting (input had {len(segments)} segments)")
        
        return formatted

