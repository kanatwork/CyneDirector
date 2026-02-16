# [FILE: workers/transcriber.py]
import os
import json
import time
import torch
from PyQt6.QtCore import QThread, pyqtSignal
from core.ai_models import AIBackend
from core.database import Database
from core.settings_manager import get_whisper_language_hint


class TranscriberWorker(QThread):
    # Signals matching MainWindow requirements
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal()
    file_finished_signal = pyqtSignal(str)

    def __init__(self, file_paths, project_path, mode="speed"):
        super().__init__()
        self.file_paths = file_paths
        self.project_path = project_path
        self.is_running = True
        self.mode = mode  # "speed" or "accuracy"

    def run(self):
        self.log_signal.emit("Initializing Whisper AI...")
        
        # 1. Load the shared AI Backend
        # This respects the hardware detection logic we fixed in ai_models.py
        ai = AIBackend()
        db = Database(self.project_path)
        
        try:
            if self.mode == "accuracy":
                self.log_signal.emit("Loading Whisper Large-v3 model (this may take a moment)...")
                model = ai.load_whisper()
                self.log_signal.emit("Whisper model loaded successfully")
            else:  # speed mode
                model_name, whisper_device, compute_type = ai.get_whisper_params("speed")
                self.log_signal.emit(f"Loading Whisper {model_name} [{whisper_device}] for faster processing...")
                from faster_whisper import WhisperModel
                try:
                    model = WhisperModel(model_name, device=whisper_device, compute_type=compute_type)
                    self.log_signal.emit(f"Whisper {model_name} model loaded successfully")
                except Exception:
                    # Fallback to large-v3 with same device settings
                    model = WhisperModel("large-v3", device=whisper_device, compute_type=compute_type)
                    self.log_signal.emit(f"Whisper Large-v3 ({compute_type}) loaded for speed")
        except Exception as e:
            self.log_signal.emit(f"CRITICAL: Audio Model Failed - {e}")
            self.finished_signal.emit()
            return

        whisper_language = get_whisper_language_hint()
        if whisper_language:
            self.log_signal.emit(f"Using transcription language preference: {whisper_language}")

        total_files = len(self.file_paths)
        
        for idx, video_path in enumerate(self.file_paths):
            if not self.is_running: break
            
            filename = os.path.basename(video_path)
            self.log_signal.emit(f"Processing {idx + 1}/{total_files}: {filename}")
            
            # Check if transcript already exists
            meta = db.get_video_metadata(video_path)
            existing_transcript = meta.get("transcript", [])
            
            if existing_transcript and isinstance(existing_transcript, list) and len(existing_transcript) > 0:
                # Check if file was modified since last transcription
                try:
                    file_mtime = os.path.getmtime(video_path)
                    last_scanned = meta.get("last_scanned", 0)
                    file_modified = file_mtime > last_scanned if last_scanned > 0 else True
                    
                    if not file_modified:
                        self.log_signal.emit(f"  → Transcript already exists ({len(existing_transcript)} segments), skipping...")
                        self.file_finished_signal.emit(video_path)
                        progress = int(((idx + 1) / total_files) * 100)
                        self.progress_signal.emit(progress)
                        continue
                    else:
                        self.log_signal.emit(f"  → File modified since last transcription, re-transcribing...")
                except OSError:
                    # If we can't get mtime, proceed with transcription
                    pass
            
            self.log_signal.emit(f"  → Starting transcription with VAD...")
            
            # Emit initial progress
            base_progress = int((idx / total_files) * 100)
            self.progress_signal.emit(base_progress)
            
            try:
                # 2. Transcribe with VAD (Voice Activity Detection)
                # Mode-based VAD settings - more sensitive for better completeness
                self.log_signal.emit(f"  → Loading audio and analyzing...")
                if self.mode == "accuracy":
                    # More sensitive VAD for better segment detection
                    transcribe_kwargs = {
                        "beam_size": 5,
                        "vad_filter": True,
                        "vad_parameters": dict(min_silence_duration_ms=200),  # More sensitive to catch all dialogue
                    }
                    if whisper_language:
                        transcribe_kwargs["language"] = whisper_language
                    segments, info = model.transcribe(video_path, **transcribe_kwargs)
                else:  # speed mode
                    # Less sensitive VAD but still more sensitive than before
                    transcribe_kwargs = {
                        "beam_size": 5,
                        "vad_filter": True,
                        "vad_parameters": dict(min_silence_duration_ms=300),  # More sensitive than before
                    }
                    if whisper_language:
                        transcribe_kwargs["language"] = whisper_language
                    segments, info = model.transcribe(video_path, **transcribe_kwargs)
                
                # Capture detected language from Whisper
                detected_language = getattr(info, 'language', None)
                if detected_language:
                    self.log_signal.emit(f"  → Detected language: {detected_language}")
                    db.update_metadata_key(video_path, "transcript_language", detected_language)
                
                self.log_signal.emit(f"  → Processing transcript segments...")
                segment_list = []
                full_text = ""
                segment_count = 0
                
                # Convert generator to list with progress updates
                for segment in segments:
                    if not self.is_running: break
                    
                    text = segment.text.strip()
                    if not text: continue

                    seg_dict = {
                        "start": segment.start,
                        "end": segment.end,
                        "text": text
                    }
                    # Detect and store language for each segment
                    from core.translator import detect_segment_language
                    detect_segment_language(seg_dict)
                    segment_list.append(seg_dict)
                    full_text += text + " "
                    segment_count += 1
                    
                    # Emit progress every 10 segments
                    if segment_count % 10 == 0:
                        # Update progress: base progress + portion for current file
                        current_progress = int((idx / total_files) * 100 + (segment_count / max(1, segment_count + 10) * (100 / total_files)))
                        self.progress_signal.emit(min(99, current_progress))
                        self.log_signal.emit(f"  → Processed {segment_count} segments...")

                if not self.is_running: break

                # Detect gaps in transcription
                # Estimate duration from last segment end time (add small buffer)
                duration = segment_list[-1]['end'] + 1.0 if segment_list else 0
                
                from core.translator import detect_transcription_gaps
                gaps = detect_transcription_gaps(segment_list, duration, max_gap_seconds=2.0)
                if gaps:
                    total_gap_time = sum(g['duration'] for g in gaps)
                    self.log_signal.emit(f"  → Warning: Detected {len(gaps)} potential gaps totaling {total_gap_time:.1f}s")
                    db.update_metadata_key(video_path, "transcription_gaps", gaps)

                # Update progress before saving
                save_progress = int(((idx + 0.8) / total_files) * 100)
                self.progress_signal.emit(save_progress)

                # 3. Save Transcript to Database
                self.log_signal.emit(f"  → Saving {len(segment_list)} transcript segments...")
                db.save_transcript(video_path, segment_list)
                
                # Update last_scanned timestamp for incremental indexing
                try:
                    file_mtime = os.path.getmtime(video_path)
                    db.update_metadata_key(video_path, "last_scanned", file_mtime)
                except OSError:
                    db.update_metadata_key(video_path, "last_scanned", time.time())
                
                # 4. Generate embeddings for semantic search (only in accuracy mode for speed)
                if self.mode == "accuracy":
                    try:
                        self.log_signal.emit(f"  → Generating transcript embeddings for semantic search...")
                        # Use CLIP text encoder for dialogue embeddings
                        ai_backend = AIBackend()
                        if ai_backend.clip_model is None:
                            try:
                                ai_backend.load_clip()
                            except Exception as clip_error:
                                self.log_signal.emit(f"  WARNING: CLIP loading failed: {clip_error}. Skipping embeddings.")
                                # Continue without embeddings - transcription still works
                                pass
                        
                        if ai_backend.clip_model and ai_backend.clip_processor:
                            # Generate embeddings for each segment
                            segment_texts = [seg["text"] for seg in segment_list]
                            if segment_texts:
                                # Process in batches
                                batch_size = 32
                                all_embeddings = []
                                all_ids = []
                                all_metadatas = []
                                total_batches = (len(segment_texts) + batch_size - 1) // batch_size
                                
                                for i in range(0, len(segment_texts), batch_size):
                                    if not self.is_running: break
                                    batch = segment_texts[i:i+batch_size]
                                    batch_num = (i // batch_size) + 1
                                    
                                    # Progress update
                                    if batch_num % 5 == 0 or batch_num == total_batches:
                                        self.log_signal.emit(f"  → Processing embedding batch {batch_num}/{total_batches}...")
                                    
                                    inputs = ai_backend.clip_processor(text=batch, return_tensors="pt", padding=True).to(ai_backend.device)
                                    
                                    with torch.no_grad():
                                        text_features = ai_backend.clip_model.get_text_features(**inputs)
                                        text_features /= text_features.norm(p=2, dim=-1, keepdim=True)
                                        embeddings = text_features.cpu().numpy().tolist()
                                    
                                    all_embeddings.extend(embeddings)
                                    
                                    # Create IDs and metadata
                                    for j, seg in enumerate(segment_list[i:i+batch_size]):
                                        seg_id = f"{video_path}_transcript_{seg['start']}"
                                        all_ids.append(seg_id)
                                        all_metadatas.append({
                                            "source": video_path,
                                            "start": seg['start'],
                                            "end": seg['end'],
                                            "text": seg['text']
                                        })
                                
                                # Store in ChromaDB transcripts collection
                                if all_embeddings:
                                    db.transcripts.upsert(ids=all_ids, embeddings=all_embeddings, metadatas=all_metadatas)
                                    self.log_signal.emit(f"  → Stored {len(all_embeddings)} transcript embeddings")
                    except Exception as e:
                        self.log_signal.emit(f"  WARNING: Transcript embedding error: {e}")
                        # Don't fail the whole transcription if embedding fails
                
                # 5. Generate Summary (fast template-based, skip slow LLM in speed mode)
                current_meta = db.get_video_metadata(video_path)
                visual_descriptions_temp = current_meta.get("visual_descriptions_temp", [])
                
                try:
                    if visual_descriptions_temp:
                        # Both visual and audio data exist
                        if self.mode == "accuracy":
                            # Try LLM summary in accuracy mode only
                            self.log_signal.emit(f"  → Generating unified summary...")
                            try:
                                from core.summary_generator import generate_contextual_summary
                                
                                emotions = current_meta.get("emotions", [])
                                objects = current_meta.get("objects", [])
                                
                                # Try LLM with timeout protection
                                unified_summary = generate_contextual_summary(
                                    visual_descriptions=visual_descriptions_temp,
                                    transcript_text=full_text,
                                    emotions=emotions,
                                    objects=objects
                                )
                                
                                if unified_summary and len(unified_summary) > 20:
                                    db.save_summary(video_path, unified_summary)
                                    db.update_metadata_key(video_path, "visual_descriptions_temp", None)
                                    self.log_signal.emit(f"  → Generated unified summary")
                                else:
                                    # Fallback to template
                                    raise Exception("LLM summary too short, using template")
                            except Exception as e:
                                # Fallback to fast template-based summary
                                self.log_signal.emit(f"  → Using fast template summary (LLM unavailable)")
                                audio_preview = (full_text[:200] + "...") if len(full_text) > 200 else full_text
                                visual_text = ". ".join(visual_descriptions_temp[:3])  # Top 3 only
                                db.save_summary(video_path, f"{visual_text}. Audio: \"{audio_preview}\"")
                                db.update_metadata_key(video_path, "visual_descriptions_temp", None)
                        else:
                            # Speed mode: Use fast template summary
                            self.log_signal.emit(f"  → Generating fast template summary...")
                            audio_preview = (full_text[:200] + "...") if len(full_text) > 200 else full_text
                            visual_text = ". ".join(visual_descriptions_temp[:3])  # Top 3 only
                            db.save_summary(video_path, f"{visual_text}. Audio: \"{audio_preview}\"")
                            db.update_metadata_key(video_path, "visual_descriptions_temp", None)
                    else:
                        # Only audio data - save audio-only summary
                        self.log_signal.emit(f"  → Generating audio summary...")
                        audio_preview = (full_text[:200] + "...") if len(full_text) > 200 else full_text
                        db.save_summary(video_path, f"Audio: \"{audio_preview}\"")
                except Exception as e:
                    # Final fallback - don't crash on summary errors
                    self.log_signal.emit(f"  WARNING: Summary generation error: {e}")
                    try:
                        audio_preview = (full_text[:200] + "...") if len(full_text) > 200 else full_text
                        db.save_summary(video_path, f"Audio: \"{audio_preview}\"")
                    except:
                        pass  # If even this fails, skip summary

                # Tell UI this file is done (Adds Green Checkmark)
                self.file_finished_signal.emit(video_path)
                self.log_signal.emit(f"  Completed: {filename} ({len(segment_list)} segments, {len(full_text)} chars)")

            except Exception as e:
                self.log_signal.emit(f"Error on {filename}: {str(e)}")

            # Update progress bar
            progress = int(((idx + 1) / total_files) * 100)
            self.progress_signal.emit(progress)

        # 5. Cleanup Resources
        # Critical: Release VRAM so the user can switch to Visual Search/Indexing immediately
        ai.unload_models()
        
        self.log_signal.emit("Transcription Complete.")
        self.finished_signal.emit()

    def stop(self):
        self.is_running = False
