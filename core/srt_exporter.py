# [FILE: core/srt_exporter.py]
import os
from typing import List, Dict

class SRTExporter:
    """Exports transcripts to SRT subtitle format."""
    
    @staticmethod
    def format_timestamp(seconds: float) -> str:
        """Convert seconds to SRT timestamp format (HH:MM:SS,mmm)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
    
    @staticmethod
    def export_transcript_to_srt(transcript: List[Dict], output_path: str) -> bool:
        """
        Export transcript segments to SRT file.
        
        Args:
            transcript: List of dicts with 'start', 'end', 'text' keys
            output_path: Path to save SRT file
        
        Returns:
            True if successful, False otherwise
        """
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                for idx, segment in enumerate(transcript, start=1):
                    start_time = SRTExporter.format_timestamp(segment['start'])
                    end_time = SRTExporter.format_timestamp(segment['end'])
                    text = segment['text'].strip()
                    
                    # SRT format:
                    # 1
                    # 00:00:00,000 --> 00:00:05,000
                    # Text content here
                    # (blank line)
                    f.write(f"{idx}\n")
                    f.write(f"{start_time} --> {end_time}\n")
                    f.write(f"{text}\n")
                    f.write("\n")
            
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
            
            success = SRTExporter.export_transcript_to_srt(transcript, output_path)
            results[video_path] = success
        
        return results


