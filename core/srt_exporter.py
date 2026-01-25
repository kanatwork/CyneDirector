# [FILE: core/srt_exporter.py]
import os
from typing import List, Dict
from core.translator import merge_transcript_segments, split_into_sentences, split_segments_into_sentences

class SRTExporter:
    """Exports transcripts to SRT subtitle format."""
    
    # SRT standard: max 42 characters per line, max 2 lines per subtitle
    MAX_CHARS_PER_LINE = 42
    MAX_LINES_PER_SUBTITLE = 2
    
    @staticmethod
    def format_timestamp(seconds: float) -> str:
        """Convert seconds to SRT timestamp format (HH:MM:SS,mmm)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
    
    @staticmethod
    def _format_text_for_srt(text: str) -> str:
        """
        Format text for SRT according to standards.
        Split long lines and ensure max 2 lines per subtitle.
        
        Args:
            text: Text to format
        
        Returns:
            Formatted text (max 2 lines, max 42 chars per line)
        """
        text = text.strip()
        if not text:
            return ""
        
        # If text is short enough, return as-is
        if len(text) <= SRTExporter.MAX_CHARS_PER_LINE:
            return text
        
        # Split into words
        words = text.split()
        lines = []
        current_line = ""
        
        for word in words:
            # Check if adding this word would exceed line length
            test_line = f"{current_line} {word}".strip() if current_line else word
            
            if len(test_line) <= SRTExporter.MAX_CHARS_PER_LINE:
                current_line = test_line
            else:
                # Current line is full, start new line
                if current_line:
                    lines.append(current_line)
                    current_line = word
                else:
                    # Single word is too long, split it
                    if len(word) > SRTExporter.MAX_CHARS_PER_LINE:
                        # Break long word (shouldn't happen often)
                        while len(word) > SRTExporter.MAX_CHARS_PER_LINE:
                            lines.append(word[:SRTExporter.MAX_CHARS_PER_LINE])
                            word = word[SRTExporter.MAX_CHARS_PER_LINE:]
                        current_line = word
                    else:
                        current_line = word
                
                # Check if we've reached max lines
                if len(lines) >= SRTExporter.MAX_LINES_PER_SUBTITLE:
                    break
        
        # Add remaining line
        if current_line and len(lines) < SRTExporter.MAX_LINES_PER_SUBTITLE:
            lines.append(current_line)
        
        return "\n".join(lines)
    
    @staticmethod
    def export_transcript_to_srt(transcript: List[Dict], output_path: str, 
                                  one_sentence_per_subtitle: bool = True) -> bool:
        """
        Export transcript segments to SRT file.
        By default, splits segments into sentences to ensure one sentence per subtitle.
        
        Args:
            transcript: List of dicts with 'start', 'end', 'text' keys
            output_path: Path to save SRT file
            one_sentence_per_subtitle: If True, split segments into sentences (default: True)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Split into sentences if requested
            if one_sentence_per_subtitle:
                transcript = split_segments_into_sentences(transcript)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                subtitle_idx = 1
                for segment in transcript:
                    start_time = segment.get('start', 0)
                    end_time = segment.get('end', 0)
                    text = segment.get('text', '').strip()
                    
                    if not text:
                        continue
                    
                    # Ensure minimum duration of 1 second
                    if end_time - start_time < 1.0:
                        end_time = start_time + 1.0
                    
                    # Format text according to SRT standards
                    formatted_text = SRTExporter._format_text_for_srt(text)
                    
                    if not formatted_text:
                        continue
                    
                    # SRT format:
                    # 1
                    # 00:00:00,000 --> 00:00:05,000
                    # Text content here
                    # (blank line)
                    start_str = SRTExporter.format_timestamp(start_time)
                    end_str = SRTExporter.format_timestamp(end_time)
                    
                    f.write(f"{subtitle_idx}\n")
                    f.write(f"{start_str} --> {end_str}\n")
                    f.write(f"{formatted_text}\n")
                    f.write("\n")
                    
                    subtitle_idx += 1
            
            return True
        except Exception as e:
            print(f"SRT Export Error: {e}")
            return False
    
    @staticmethod
    def export_multiple_transcripts(transcripts_dict: Dict[str, List[Dict]], output_dir: str) -> Dict[str, bool]:
        """
        Export multiple transcripts to SRT files.
        
        Args:
            transcripts_dict: Dict mapping video_path -> transcript list
            output_dir: Directory to save SRT files
        
        Returns:
            Dict mapping video_path -> success bool
        """
        os.makedirs(output_dir, exist_ok=True)
        results = {}
        
        for video_path, transcript in transcripts_dict.items():
            # Generate output filename
            base_name = os.path.splitext(os.path.basename(video_path))[0]
            output_path = os.path.join(output_dir, f"{base_name}.srt")
            
            # Use sentence-aware export for proper SRT format
            success = SRTExporter.export_transcript_to_srt(transcript, output_path, one_sentence_per_subtitle=True)
            results[video_path] = success
        
        return results
    
    @staticmethod
    def export_translated_srt(transcript: List[Dict], output_path: str, merge_segments: bool = False) -> bool:
        """
        Export transcript to SRT file with one sentence per subtitle.
        Uses split_segments_into_sentences to preserve original timing while splitting sentences.
        
        Args:
            transcript: List of dicts with 'start', 'end', 'text' keys
            output_path: Path to save SRT file
            merge_segments: If True, merge segments before splitting (not recommended - loses timing)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            if merge_segments:
                # Legacy mode: merge and redistribute (not recommended)
                merged_text = merge_transcript_segments(transcript)
                sentences = split_into_sentences(merged_text)
                
                if not transcript or not sentences:
                    return False
                
                total_duration = transcript[-1]['end'] - transcript[0]['start']
                duration_per_sentence = total_duration / len(sentences) if sentences else 0
                
                sentence_segments = []
                start_time = transcript[0]['start']
                
                for i, sentence in enumerate(sentences):
                    end_time = start_time + duration_per_sentence
                    if i == len(sentences) - 1:
                        end_time = transcript[-1]['end']
                    
                    sentence_segments.append({
                        'start': start_time,
                        'end': end_time,
                        'text': sentence
                    })
                    start_time = end_time
                
                return SRTExporter.export_transcript_to_srt(sentence_segments, output_path, one_sentence_per_subtitle=False)
            else:
                # Preferred: split segments into sentences while preserving timing
                sentence_segments = split_segments_into_sentences(transcript)
                return SRTExporter.export_transcript_to_srt(sentence_segments, output_path, one_sentence_per_subtitle=False)
        except Exception as e:
            print(f"SRT Export Error: {e}")
            return False



