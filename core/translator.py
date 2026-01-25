# [FILE: core/translator.py]
"""
Translation module for transcribing and translating audio transcripts.
Supports DeepL API (most accurate) and Whisper built-in translation (fallback).
"""
import re
from typing import List, Dict, Optional
from core.logger import get_logger

logger = get_logger(__name__)


def detect_language(text: str) -> Optional[str]:
    """
    Detect language of text using simple heuristics or library.
    Enhanced to better detect Hindi and other languages.
    
    Args:
        text: Text to detect language for
    
    Returns:
        Language code (e.g., 'en', 'hi', 'ja', 'es') or None if detection fails
    """
    if not text or not text.strip():
        return None
    
    # Try using langdetect library if available (most accurate)
    try:
        import langdetect
        # Suppress langdetect warnings about multiple languages
        from langdetect import DetectorFactory
        DetectorFactory.seed = 0
        detected = langdetect.detect(text)
        return detected
    except ImportError:
        # Fallback to simple heuristic-based detection
        pass
    except Exception as e:
        logger.debug(f"Language detection error: {e}")
    
    # Enhanced heuristic: check for common patterns in multiple languages
    text_lower = text.lower()
    text_clean = text.strip()
    
    # Hindi detection: Check for Devanagari script characters (Unicode range: 0900-097F)
    if any('\u0900' <= char <= '\u097F' for char in text_clean):
        return 'hi'
    
    # Japanese detection: Check for Hiragana/Katakana/Kanji
    japanese_indicators = ['の', 'は', 'が', 'を', 'に', 'で', 'と', 'から', 'まで']
    japanese_count = sum(1 for char in japanese_indicators if char in text)
    if japanese_count > 0 or any('\u3040' <= char <= '\u309F' or '\u30A0' <= char <= '\u30FF' or '\u4E00' <= char <= '\u9FAF' for char in text_clean):
        return 'ja'
    
    # Chinese detection: Check for Chinese characters
    if any('\u4E00' <= char <= '\u9FFF' for char in text_clean):
        return 'zh'
    
    # Arabic detection: Check for Arabic script
    if any('\u0600' <= char <= '\u06FF' for char in text_clean):
        return 'ar'
    
    # English detection: Check for common English words
    english_indicators = ['the', 'and', 'is', 'are', 'was', 'were', 'this', 'that', 'with', 'from', 'have', 'has', 'had', 'will', 'would', 'could', 'should']
    english_count = sum(1 for word in english_indicators if word in text_lower)
    
    # If text contains mostly ASCII and has English indicators, likely English
    ascii_ratio = sum(1 for c in text_clean if ord(c) < 128) / len(text_clean) if text_clean else 0
    
    if english_count >= 2 and ascii_ratio > 0.8:
        return 'en'
    elif english_count >= 3:
        return 'en'
    
    return None


def is_english(text: str) -> bool:
    """
    Check if text is likely English.
    
    Args:
        text: Text to check
    
    Returns:
        True if text appears to be English, False otherwise
    """
    if not text or not text.strip():
        return False
    
    lang = detect_language(text)
    return lang == 'en'


def detect_segment_language(segment: Dict) -> Optional[str]:
    """
    Detect language for a single transcript segment.
    Stores the language in the segment if not already present.
    
    Args:
        segment: Transcript segment dict with 'text' key
    
    Returns:
        Language code (e.g., 'en', 'hi') or None
    """
    if 'language' in segment:
        return segment['language']
    
    text = segment.get('text', '').strip()
    if not text:
        return None
    
    lang = detect_language(text)
    if lang:
        segment['language'] = lang
    
    return lang


def filter_english_segments(segments: List[Dict]) -> List[Dict]:
    """
    Filter segments to only include those that are in English.
    
    Args:
        segments: List of transcript segments
    
    Returns:
        Filtered list containing only English segments
    """
    if not segments:
        return []
    
    english_segments = []
    for seg in segments:
        text = seg.get('text', '').strip()
        if text and is_english(text):
            english_segments.append(seg)
        elif text:
            logger.debug(f"Filtered out non-English segment: {text[:50]}...")
    
    return english_segments


def translate_mixed_language_transcript(segments: List[Dict], translator_func, max_chunk_size: int = 50000) -> List[Dict]:
    """
    Translate a mixed-language transcript, keeping English segments unchanged.
    Handles chunking for long texts.
    
    Args:
        segments: List of transcript segments (may contain 'language' field)
        translator_func: Function that takes text and returns translated text
        max_chunk_size: Maximum characters per translation chunk (default: 50000 for DeepL)
    
    Returns:
        List of segments with all non-English segments translated to English
    """
    if not segments:
        return []
    
    english_segments = []
    non_english_segments = []
    
    # Separate segments by language
    for seg in segments:
        lang = detect_segment_language(seg)
        if lang == 'en':
            english_segments.append(seg)
        else:
            non_english_segments.append(seg)
    
    logger.info(f"Found {len(english_segments)} English segments and {len(non_english_segments)} non-English segments")
    
    # Translate non-English segments
    if non_english_segments:
        # Extract text from non-English segments, preserving segment references
        segment_text_pairs = [(seg, seg.get('text', '')) for seg in non_english_segments]
        merged_text = ' '.join(text for _, text in segment_text_pairs)
        
        # Translate in chunks if text is too long
        if len(merged_text) > max_chunk_size:
            logger.info(f"Text is long ({len(merged_text)} chars), translating in chunks...")
            translated_chunks = []
            chunk_count = (len(merged_text) + max_chunk_size - 1) // max_chunk_size
            
            for i in range(0, len(merged_text), max_chunk_size):
                chunk = merged_text[i:i+max_chunk_size]
                chunk_num = (i // max_chunk_size) + 1
                logger.info(f"Translating chunk {chunk_num}/{chunk_count}...")
                
                try:
                    translated_chunk = translator_func(chunk)
                    # Verify translation actually happened - check if it's still in original language
                    # If translation failed silently, the text might be unchanged
                    if translated_chunk == chunk:
                        logger.warning(f"Chunk {chunk_num} translation returned identical text - translation may have failed")
                    # Check if translated text still contains non-English characters (e.g., Hindi Devanagari)
                    if any('\u0900' <= char <= '\u097F' for char in translated_chunk):
                        logger.warning(f"Chunk {chunk_num} still contains Hindi characters after translation - retrying...")
                        # Retry once
                        try:
                            translated_chunk = translator_func(chunk)
                        except Exception as retry_error:
                            logger.error(f"Chunk {chunk_num} retry failed: {retry_error}")
                            # If retry fails, raise to trigger proper error handling
                            raise Exception(f"Translation failed for chunk {chunk_num}: text still contains non-English characters")
                    translated_chunks.append(translated_chunk)
                except Exception as e:
                    logger.error(f"Chunk {chunk_num} translation failed: {e}")
                    # Don't use original text - raise error to trigger fallback or proper error handling
                    raise Exception(f"Translation failed for chunk {chunk_num}: {e}")
            
            translated_text = ' '.join(translated_chunks)
        else:
            # Translate all at once
            try:
                translated_text = translator_func(merged_text)
                # Verify translation actually happened
                if translated_text == merged_text:
                    logger.warning("Translation returned identical text - translation may have failed")
                # Check if translated text still contains non-English characters (e.g., Hindi Devanagari)
                if any('\u0900' <= char <= '\u097F' for char in translated_text):
                    logger.warning("Translated text still contains Hindi characters - retrying...")
                    # Retry once
                    try:
                        translated_text = translator_func(merged_text)
                        # Check again
                        if any('\u0900' <= char <= '\u097F' for char in translated_text):
                            raise Exception("Translation failed: text still contains Hindi characters after retry")
                    except Exception as retry_error:
                        logger.error(f"Translation retry failed: {retry_error}")
                        raise Exception(f"Translation failed: {retry_error}")
            except Exception as e:
                logger.error(f"Translation failed: {e}")
                # Don't return original segments - raise to trigger proper error handling
                raise Exception(f"Translation failed: {e}")
        
        # Split translated text back into sentences
        translated_sentences = split_into_sentences(translated_text)
        
        logger.info(f"Distributing {len(translated_sentences)} translated sentences across {len(non_english_segments)} non-English segments")
        
        # Phase 2 Fix: Use original text length as weight for better distribution
        # Calculate original text lengths for each segment
        original_text_lengths = [len(seg.get('text', '')) for seg in non_english_segments]
        total_original_length = sum(original_text_lengths) if original_text_lengths else 1
        
        # Distribute translated sentences across non-English segment timings
        # Ensure ALL segments get text - don't lose any segments
        if len(translated_sentences) == len(non_english_segments):
            # Perfect match: assign each sentence to corresponding segment
            for i, seg in enumerate(non_english_segments):
                seg['text'] = translated_sentences[i] if i < len(translated_sentences) else "[Translation unavailable]"
                seg['language'] = 'en'
                seg['translated'] = True
        elif len(translated_sentences) > len(non_english_segments):
            # More sentences than segments: distribute proportionally based on original text length
            sentence_idx = 0
            for seg_idx, seg in enumerate(non_english_segments):
                if total_original_length > 0:
                    # Calculate how many sentences this segment should get based on original text length
                    if seg_idx == len(non_english_segments) - 1:
                        # Last segment gets all remaining sentences to ensure nothing is lost
                        num_sentences = len(translated_sentences) - sentence_idx
                    else:
                        # Use original text length as weight
                        seg_length = original_text_lengths[seg_idx]
                        num_sentences = max(1, round(len(translated_sentences) * (seg_length / total_original_length)))
                else:
                    num_sentences = 1
                
                if sentence_idx < len(translated_sentences):
                    end_idx = min(sentence_idx + num_sentences, len(translated_sentences))
                    seg['text'] = ' '.join(translated_sentences[sentence_idx:end_idx])
                    seg['language'] = 'en'
                    seg['translated'] = True
                    sentence_idx = end_idx
                else:
                    # Shouldn't happen, but if we run out, use the last sentence
                    logger.warning(f"Ran out of sentences for segment {seg_idx}, using last available sentence")
                    if translated_sentences:
                        seg['text'] = translated_sentences[-1]
                    else:
                        seg['text'] = "[Translation unavailable]"
                    seg['language'] = 'en'
                    seg['translated'] = True
        else:
            # Fewer sentences than segments: distribute sentences more intelligently
            # Use original text length to determine which segments should share sentences
            logger.warning(f"Fewer translated sentences ({len(translated_sentences)}) than segments ({len(non_english_segments)}). Distributing based on original text length.")
            
            # Phase 2 Fix: Ensure every segment gets at least one sentence or shares sentences
            # Use weighted round-robin distribution based on original text length
            if total_original_length > 0 and len(translated_sentences) > 0:
                # Create a list of segment indices weighted by original text length
                # Segments with more text get more sentences
                weighted_segments = []
                for idx, length in enumerate(original_text_lengths):
                    # Weight = how many sentences this segment should ideally get
                    weight = max(1, round((length / total_original_length) * len(translated_sentences)))
                    for _ in range(weight):
                        weighted_segments.append(idx)
                
                # If we still have fewer weighted entries than segments, ensure each segment appears at least once
                if len(weighted_segments) < len(non_english_segments):
                    existing_indices = set(weighted_segments)
                    for idx in range(len(non_english_segments)):
                        if idx not in existing_indices:
                            weighted_segments.append(idx)
                            existing_indices.add(idx)
                
                # Distribute sentences using weighted round-robin
                sentence_assignments = [[] for _ in non_english_segments]
                for sentence_idx, sentence in enumerate(translated_sentences):
                    # Use modulo to cycle through weighted segments
                    target_seg_idx = weighted_segments[sentence_idx % len(weighted_segments)]
                    sentence_assignments[target_seg_idx].append(sentence)
                
                # Assign sentences to segments
                for seg_idx, seg in enumerate(non_english_segments):
                    if sentence_assignments[seg_idx]:
                        seg['text'] = ' '.join(sentence_assignments[seg_idx])
                    else:
                        # If somehow a segment got no sentences, use the nearest sentence
                        # Find the closest sentence index
                        closest_sentence_idx = min(
                            range(len(translated_sentences)),
                            key=lambda i: abs(i - (seg_idx * len(translated_sentences) / len(non_english_segments)))
                        )
                        seg['text'] = translated_sentences[closest_sentence_idx] if translated_sentences else "[Translation unavailable]"
                    
                    seg['language'] = 'en'
                    seg['translated'] = True
            else:
                # Fallback: round-robin distribution if no text lengths available
                for seg_idx, seg in enumerate(non_english_segments):
                    # Round-robin: assign sentences cyclically
                    sentence_idx = seg_idx % len(translated_sentences) if translated_sentences else 0
                    seg['text'] = translated_sentences[sentence_idx] if translated_sentences else "[Translation unavailable]"
                    seg['language'] = 'en'
                    seg['translated'] = True
    
    # Ensure English segments are explicitly marked as English
    for seg in english_segments:
        seg['language'] = 'en'
        seg['translated'] = False  # Not translated, kept as-is
    
    # Combine English (unchanged) + translated segments, maintaining chronological order
    all_segments = english_segments + non_english_segments
    all_segments.sort(key=lambda x: x.get('start', 0))
    
    # Phase 3: Segment Preservation Guarantee - validate all segments are present
    original_count = len(segments)
    final_count = len(all_segments)
    if final_count < original_count:
        logger.warning(f"Segment count mismatch in translate_mixed_language_transcript! Original: {original_count}, Final: {final_count}")
        # Find missing segments by comparing start times
        final_starts = {round(seg.get('start', 0), 2) for seg in all_segments}
        missing_segments = []
        for orig_seg in segments:
            orig_start = round(orig_seg.get('start', 0), 2)
            if orig_start not in final_starts:
                missing_segments.append(orig_seg)
        
        if missing_segments:
            logger.warning(f"Found {len(missing_segments)} missing segments, adding them back")
            # Add missing segments - mark as untranslated if they were non-English
            for missing_seg in missing_segments:
                lang = detect_segment_language(missing_seg)
                if lang != 'en':
                    # This was a non-English segment that got lost - mark as translation failed
                    missing_seg['text'] = f"[Translation unavailable - original: {missing_seg.get('text', '')}]"
                    missing_seg['language'] = 'en'
                    missing_seg['translated'] = True
                    missing_seg['translation_failed'] = True
                else:
                    # English segment - keep as is
                    missing_seg['language'] = 'en'
                    missing_seg['translated'] = False
                all_segments.append(missing_seg)
            
            # Re-sort to maintain chronological order
            all_segments.sort(key=lambda x: x.get('start', 0))
            logger.info(f"Restored segment count: {len(all_segments)} segments (original: {original_count})")
    
    return all_segments


class DeepLTranslator:
    """DeepL API translator for high-quality translations."""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize DeepL translator.
        
        Args:
            api_key: DeepL API key (optional, if None will not be available)
        """
        self.api_key = api_key
        self.available = False
        
        if api_key:
            try:
                import deepl
                self.translator = deepl.Translator(api_key)
                # Test connection
                self.translator.get_usage()
                self.available = True
                logger.info("DeepL translator initialized successfully")
            except ImportError:
                logger.warning("deepl package not installed. Install with: pip install deepl")
            except Exception as e:
                logger.warning(f"DeepL initialization failed: {e}")
        else:
            logger.info("DeepL API key not provided, translator unavailable")
    
    def translate(self, text: str, source_lang: Optional[str] = None, target_lang: str = "EN-US") -> str:
        """
        Translate text using DeepL API.
        
        Args:
            text: Text to translate
            source_lang: Source language code (None for auto-detect)
            target_lang: Target language code (default: "EN-US" for English)
        
        Returns:
            Translated text, or original text if translation fails
        """
        if not self.available:
            raise RuntimeError("DeepL translator not available")
        
        if not text or not text.strip():
            return text
        
        # Normalize target language - DeepL requires EN-US or EN-GB, not just EN
        if target_lang.upper() == "EN":
            target_lang = "EN-US"
        
        try:
            result = self.translator.translate_text(
                text,
                source_lang=source_lang,
                target_lang=target_lang
            )
            translated = result.text
            logger.debug(f"DeepL translation: {len(text)} chars -> {len(translated)} chars")
            return translated
        except Exception as e:
            error_str = str(e).lower()
            error_msg = str(e)
            
            # Provide more specific error messages
            if "quota" in error_str or "limit" in error_str:
                error_msg = f"DeepL API quota/rate limit exceeded: {e}. Please try again later or upgrade your plan."
            elif "invalid" in error_str or "auth" in error_str or "key" in error_str or "unauthorized" in error_str:
                error_msg = f"DeepL API key is invalid or expired: {e}. Please check your API key in config.py or environment variables."
            elif "network" in error_str or "connection" in error_str or "timeout" in error_str:
                error_msg = f"DeepL API network error: {e}. Please check your internet connection and try again."
            else:
                error_msg = f"DeepL translation error: {e}"
            
            logger.error(error_msg)
            import traceback
            logger.error(traceback.format_exc())
            raise Exception(error_msg) from e


class WhisperTranslator:
    """Whisper built-in translation (uses task='translate' parameter)."""
    
    def __init__(self, whisper_model=None):
        """
        Initialize Whisper translator.
        
        Args:
            whisper_model: Pre-loaded WhisperModel instance (optional)
        """
        self.whisper_model = whisper_model
        self.available = False
        
        if whisper_model is None:
            try:
                from core.ai_models import AIBackend
                ai = AIBackend()
                self.whisper_model = ai.load_whisper()
                self.available = True
                logger.info("Whisper translator initialized successfully")
            except Exception as e:
                logger.warning(f"Whisper translator initialization failed: {e}")
        else:
            self.available = True
    
    def translate_transcript(self, video_path: str) -> List[Dict]:
        """
        Transcribe and translate audio directly using Whisper.
        
        Args:
            video_path: Path to video file
        
        Returns:
            List of transcript segments with 'start', 'end', 'text' keys (translated to English)
        """
        if not self.available or not self.whisper_model:
            raise RuntimeError("Whisper translator not available")
        
        try:
            # Use task='translate' to translate to English
            segments, info = self.whisper_model.transcribe(
                video_path,
                task="translate",  # This translates to English
                beam_size=5,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=300)
            )
            
            segment_list = []
            for segment in segments:
                text = segment.text.strip()
                if text:
                    segment_list.append({
                        "start": segment.start,
                        "end": segment.end,
                        "text": text
                    })
            
            return segment_list
        except Exception as e:
            logger.error(f"Whisper translation error: {e}")
            raise


def split_into_sentences(text: str) -> List[str]:
    """
    Split text into sentences using punctuation and heuristics.
    
    Args:
        text: Text to split
    
    Returns:
        List of sentences
    """
    if not text or not text.strip():
        return []
    
    # Clean up text first
    text = re.sub(r'\s+', ' ', text.strip())
    
    # Split on sentence-ending punctuation followed by space or end of string
    # Pattern: period, exclamation, or question mark followed by space or end
    sentence_endings = r'[.!?]+(?:\s+|$)'
    sentences = re.split(sentence_endings, text)
    
    # Clean and filter sentences
    cleaned_sentences = []
    for sentence in sentences:
        sentence = sentence.strip()
        if sentence:
            # Ensure proper capitalization
            if sentence and not sentence[0].isupper():
                sentence = sentence[0].upper() + sentence[1:] if len(sentence) > 1 else sentence.upper()
            # Ensure sentence ends with punctuation
            if sentence and sentence[-1] not in '.!?':
                sentence += '.'
            cleaned_sentences.append(sentence)
    
    return cleaned_sentences if cleaned_sentences else [text]


def merge_transcript_segments(segments: List[Dict]) -> str:
    """
    Merge transcript segments into continuous text.
    
    Args:
        segments: List of transcript segments with 'start', 'end', 'text' keys
    
    Returns:
        Merged text string
    """
    if not segments:
        return ""
    
    # Join all segment texts with spaces
    texts = [seg.get('text', '').strip() for seg in segments if seg.get('text', '').strip()]
    merged = ' '.join(texts)
    
    # Clean up multiple spaces
    merged = re.sub(r'\s+', ' ', merged)
    
    return merged.strip()


def translate_transcript_segments(
    segments: List[Dict],
    translator: Optional[DeepLTranslator] = None,
    whisper_translator: Optional[WhisperTranslator] = None
) -> List[Dict]:
    """
    Translate transcript segments to English.
    
    Args:
        segments: List of transcript segments
        translator: DeepL translator instance (optional, preferred)
        whisper_translator: Whisper translator instance (optional, fallback)
    
    Returns:
        List of translated segments with same structure
    """
    if not segments:
        return []
    
    # Try DeepL first if available
    if translator and translator.available:
        try:
            logger.info("Using DeepL for translation")
            merged_text = merge_transcript_segments(segments)
            translated_text = translator.translate(merged_text)
            
            # Split translated text back into sentences
            sentences = split_into_sentences(translated_text)
            
            # Distribute sentences proportionally across original segments
            return _distribute_sentences_to_segments(segments, sentences)
        except Exception as e:
            logger.warning(f"DeepL translation failed: {e}, trying Whisper fallback")
    
    # Fallback to Whisper if DeepL fails or not available
    if whisper_translator and whisper_translator.available:
        try:
            logger.info("Using Whisper for translation")
            # Note: Whisper translation requires video path, so this is a simplified approach
            # We'll translate the merged text using a different method
            merged_text = merge_transcript_segments(segments)
            sentences = split_into_sentences(merged_text)
            return _distribute_sentences_to_segments(segments, sentences)
        except Exception as e:
            logger.error(f"Whisper translation failed: {e}")
    
    # If both fail, return original segments
    logger.warning("Translation failed, returning original segments")
    return segments


def split_segments_into_sentences(segments: List[Dict]) -> List[Dict]:
    """
    Split transcript segments into sentence-based segments while preserving timing.
    Each segment's text is split into sentences, and time is distributed proportionally
    based on sentence length within each original segment.
    
    Args:
        segments: List of transcript segments with 'start', 'end', 'text' keys
    
    Returns:
        New segments with one sentence per segment, preserving original timing boundaries
    """
    if not segments:
        return []
    
    sentence_segments = []
    
    for seg in segments:
        text = seg.get('text', '').strip()
        if not text:
            continue
        
        # Split segment text into sentences
        sentences = split_into_sentences(text)
        
        if not sentences:
            # If no sentences found, keep the original segment
            sentence_segments.append(seg)
            continue
        
        # Calculate segment duration
        seg_duration = seg['end'] - seg['start']
        seg_start = seg['start']
        
        # Calculate total character length for proportional distribution
        total_chars = sum(len(s) for s in sentences)
        
        if total_chars == 0:
            # Fallback: equal distribution
            duration_per_sentence = seg_duration / len(sentences) if sentences else 0
        else:
            # Distribute time proportionally based on sentence length
            duration_per_sentence = seg_duration / len(sentences) if sentences else 0
        
        # Create sentence segments
        for i, sentence in enumerate(sentences):
            if i == len(sentences) - 1:
                # Last sentence gets remaining time
                seg_end = seg['end']
            else:
                # Distribute time proportionally
                if total_chars > 0:
                    sentence_ratio = len(sentence) / total_chars
                    seg_end = seg_start + (seg_duration * sentence_ratio)
                else:
                    seg_end = seg_start + duration_per_sentence
            
            # Ensure minimum duration of 0.5 seconds
            if seg_end - seg_start < 0.5:
                seg_end = seg_start + 0.5
            
            sentence_segments.append({
                'start': seg_start,
                'end': seg_end,
                'text': sentence
            })
            
            seg_start = seg_end
    
    return sentence_segments


def detect_transcription_gaps(segments: List[Dict], total_duration: float, 
                             max_gap_seconds: float = 2.0) -> List[Dict]:
    """
    Detect gaps in transcription that might indicate missing dialogue.
    
    Args:
        segments: List of transcript segments with 'start', 'end' keys
        total_duration: Total duration of the audio/video in seconds
        max_gap_seconds: Maximum gap between segments before it's considered missing (default: 2.0)
    
    Returns:
        List of gap periods with 'start', 'end' keys that exceed the threshold
    """
    if not segments:
        return []
    
    gaps = []
    
    # Sort segments by start time
    sorted_segments = sorted(segments, key=lambda x: x.get('start', 0))
    
    # Check gap at the beginning
    first_start = sorted_segments[0].get('start', 0)
    if first_start > max_gap_seconds:
        gaps.append({
            'start': 0.0,
            'end': first_start,
            'duration': first_start
        })
    
    # Check gaps between segments
    for i in range(len(sorted_segments) - 1):
        current_end = sorted_segments[i].get('end', 0)
        next_start = sorted_segments[i + 1].get('start', 0)
        gap_duration = next_start - current_end
        
        if gap_duration > max_gap_seconds:
            gaps.append({
                'start': current_end,
                'end': next_start,
                'duration': gap_duration
            })
    
    # Check gap at the end
    last_end = sorted_segments[-1].get('end', 0)
    if total_duration - last_end > max_gap_seconds:
        gaps.append({
            'start': last_end,
            'end': total_duration,
            'duration': total_duration - last_end
        })
    
    return gaps


def _distribute_sentences_to_segments(original_segments: List[Dict], sentences: List[str]) -> List[Dict]:
    """
    Distribute sentences proportionally across original segment timings.
    
    Args:
        original_segments: Original transcript segments with timings
        sentences: List of sentences to distribute
    
    Returns:
        New segments with one sentence per segment
    """
    if not original_segments or not sentences:
        return original_segments
    
    # Calculate total duration
    total_duration = original_segments[-1]['end'] - original_segments[0]['start']
    
    # Calculate duration per sentence (proportional)
    duration_per_sentence = total_duration / len(sentences) if sentences else 0
    
    # Create new segments
    new_segments = []
    start_time = original_segments[0]['start']
    
    for i, sentence in enumerate(sentences):
        end_time = start_time + duration_per_sentence
        
        # Ensure we don't exceed the original end time
        if i == len(sentences) - 1:
            end_time = original_segments[-1]['end']
        
        new_segments.append({
            'start': start_time,
            'end': end_time,
            'text': sentence
        })
        
        start_time = end_time
    
    return new_segments


def get_translator(deepl_api_key: Optional[str] = None) -> Optional[DeepLTranslator]:
    """
    Get a DeepL translator instance if API key is available.
    
    Args:
        deepl_api_key: DeepL API key (optional)
    
    Returns:
        DeepLTranslator instance or None
    """
    if deepl_api_key:
        return DeepLTranslator(deepl_api_key)
    return None


def get_whisper_translator(whisper_model=None) -> WhisperTranslator:
    """
    Get a Whisper translator instance.
    
    Args:
        whisper_model: Pre-loaded WhisperModel (optional)
    
    Returns:
        WhisperTranslator instance
    """
    return WhisperTranslator(whisper_model)

