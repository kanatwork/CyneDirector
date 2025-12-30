# [FILE: core/summary_generator.py]
"""
LLM-based summary generation that combines visual and audio context.
"""
import torch
from core.ai_models import AIBackend

def generate_contextual_summary(visual_descriptions, transcript_text, emotions=None, objects=None):
    """
    Generate a coherent summary using LLM that understands both visual and audio context.
    
    Args:
        visual_descriptions: List of BLIP-2 scene descriptions
        transcript_text: Full transcript text from Whisper
        emotions: List of detected emotions (optional)
        objects: List of detected objects (optional)
    
    Returns:
        str: Generated summary paragraph, or None if LLM unavailable
    """
    ai = AIBackend()
    
    # Try to load LLM
    llm_model, llm_tokenizer = ai.load_llm()
    
    if llm_model is None or llm_tokenizer is None:
        # Fallback to template-based approach
        return _generate_template_summary(visual_descriptions, transcript_text, emotions, objects)
    
    try:
        # Format visual descriptions
        if isinstance(visual_descriptions, list):
            visual_text = ". ".join(visual_descriptions) if visual_descriptions else "No visual descriptions available."
        else:
            visual_text = str(visual_descriptions) if visual_descriptions else "No visual descriptions available."
        
        # Format emotions and objects
        emotions_text = ", ".join(emotions) if emotions else "None detected"
        objects_text = ", ".join(objects) if objects else "None detected"
        
        # Use ENTIRE transcript - no truncation for LLM context
        # The model will handle long contexts, and we want full dialogue understanding
        # Only truncate if extremely long (over 8000 words) to avoid token limits
        # Most models can handle 4k-8k tokens, so 8000 words is a safe limit
        transcript_words = transcript_text.split()
        if len(transcript_words) > 8000:
            # Take first 6000 and last 2000 words for context
            first_part = " ".join(transcript_words[:6000])
            last_part = " ".join(transcript_words[-2000:])
            transcript_preview = f"{first_part} ... [middle section omitted] ... {last_part}"
        else:
            transcript_preview = transcript_text.strip()
        
        # Create prompt - adapt based on model type
        # Check if it's Llama format or Phi-3 format
        if "llama" in str(type(llm_model)).lower() or "llama" in str(type(llm_tokenizer)).lower():
            # Llama format
            prompt = f"""<|begin_of_text|><|start_header_id|>system<|end_header_id|>

You are a video analysis assistant. Generate a concise, coherent paragraph (2-3 sentences) summarizing what's happening in a video based on the provided information.<|eot_id|><|start_header_id|>user<|end_header_id|>

Given the following information about a video:

Visual descriptions: {visual_text}

Audio transcript: {transcript_preview}

Detected emotions: {emotions_text}

Detected objects: {objects_text}

Generate a concise, coherent paragraph (2-3 sentences) summarizing what's happening in this video. Focus on the main action, context, and key details. Be specific and descriptive.<|eot_id|><|start_header_id|>assistant<|end_header_id|>

"""
        else:
            # Phi-3 format
            prompt = f"""<|system|>
You are a video analysis assistant. Generate a concise, coherent paragraph (2-3 sentences) summarizing what's happening in a video based on the provided information.<|end|>
<|user|>
Given the following information about a video:

Visual descriptions: {visual_text}

Audio transcript: {transcript_preview}

Detected emotions: {emotions_text}

Detected objects: {objects_text}

Generate a concise, coherent paragraph (2-3 sentences) summarizing what's happening in this video. Focus on the main action, context, and key details. Be specific and descriptive.<|end|>
<|assistant|>
"""
        
        # Tokenize and generate
        inputs = llm_tokenizer(prompt, return_tensors="pt").to(ai.device)
        
        with torch.no_grad():
            outputs = llm_model.generate(
                **inputs,
                max_new_tokens=150,
                temperature=0.7,
                do_sample=True,
                top_p=0.9,
                pad_token_id=llm_tokenizer.eos_token_id
            )
        
        # Decode response
        generated_text = llm_tokenizer.decode(outputs[0], skip_special_tokens=True)
        
        # Extract only the assistant's response (after the prompt)
        if "<|start_header_id|>assistant<|end_header_id|>" in generated_text:
            summary = generated_text.split("<|start_header_id|>assistant<|end_header_id|>")[-1].strip()
            summary = summary.split("<|eot_id|>")[0].strip()
        elif "<|assistant|>" in generated_text:
            summary = generated_text.split("<|assistant|>")[-1].strip()
            summary = summary.split("<|end|>")[0].strip()
        else:
            # Fallback: take everything after the prompt
            summary = generated_text[len(prompt):].strip()
        
        # Clean up summary - take first paragraph only
        if summary:
            # Try to get first paragraph (split by double newline)
            paragraphs = summary.split("\n\n")
            if paragraphs:
                summary = paragraphs[0].strip()
            # If still empty or very short, try single newline
            if not summary or len(summary) < 10:
                lines = summary.split("\n") if summary else []
                if not lines:
                    # Get from original generated text
                    lines = generated_text[len(prompt):].strip().split("\n")
                if lines:
                    summary = lines[0].strip()
        
        return summary if summary else _generate_template_summary(visual_descriptions, transcript_text, emotions, objects)
        
    except Exception as e:
        print(f"LLM summary generation error: {e}")
        # Fallback to template-based approach
        return _generate_template_summary(visual_descriptions, transcript_text, emotions, objects)

def _generate_template_summary(visual_descriptions, transcript_text, emotions=None, objects=None):
    """
    Fallback template-based summary generation when LLM is unavailable.
    Attempts to intelligently merge visual and audio context.
    Uses the ENTIRE transcript for better context understanding.
    """
    # Use the full transcript - don't truncate unnecessarily
    transcript_summary = None
    if transcript_text:
        # Use entire transcript, but format it nicely
        words = transcript_text.split()
        
        # If transcript is very long, create a smart summary
        if len(words) > 500:
            # Take first 300 words, middle 200 words, and last 200 words
            first_part = " ".join(words[:300])
            middle_start = len(words) // 2 - 100
            middle_end = len(words) // 2 + 100
            middle_part = " ".join(words[middle_start:middle_end])
            last_part = " ".join(words[-200:])
            transcript_summary = f"{first_part} ... [continues] ... {middle_part} ... [continues] ... {last_part}"
        else:
            # Use full transcript if it's reasonable length
            transcript_summary = transcript_text
    
    # Visual descriptions
    if visual_descriptions:
        if isinstance(visual_descriptions, list):
            visual_summary = ". ".join(visual_descriptions[:3])  # Top 3 visual descriptions
        else:
            visual_summary = str(visual_descriptions)
    else:
        visual_summary = None
    
    # Merge intelligently
    if visual_summary and transcript_summary:
        # Combine: visual context + what's being discussed
        return f"{visual_summary}. The audio reveals: {transcript_summary}."
    elif visual_summary:
        return f"{visual_summary}."
    elif transcript_summary:
        return f"The audio transcript indicates: {transcript_summary}."
    else:
        return "Video content analyzed."

