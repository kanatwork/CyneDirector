import os
import cv2
import face_recognition
import numpy as np
import tempfile

def test_ai_system():
    print("--- CYNE DIAGNOSTIC TOOL ---")
    
    # TEST 1: Check Library Health with Synthetic Data
    print("\n[TEST 1] Generating Synthetic Image (RAM Mode)...")
    try:
        # Create a pure black image with a white square (fake face)
        # This guarantees PERFECT memory layout
        img = np.zeros((500, 500, 3), dtype=np.uint8)
        cv2.rectangle(img, (100, 100), (300, 300), (255, 255, 255), -1)
        
        print(f"   Image Shape: {img.shape}")
        print(f"   Image Dtype: {img.dtype}")
        
        # Try detection
        faces = face_recognition.face_locations(img, model="hog")
        print(f"✅ TEST 1 PASSED! Detection successful. Found: {len(faces)} faces (Expected 0 or 1)")
    except Exception as e:
        print(f"❌ TEST 1 FAILED: {e}")
        print("   CRITICAL: Your 'dlib' library is broken or incompatible.")
        return

    # TEST 2: Check File System & OneDrive Bypass
    print("\n[TEST 2] Testing System Temp Folder (OneDrive Bypass)...")
    try:
        # Use Windows %TEMP% folder (OneDrive cannot touch this)
        fd, temp_path = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
        
        # Write image
        cv2.imwrite(temp_path, img)
        print(f"   Saved temp file to: {temp_path}")
        
        # Read back
        loaded_img = face_recognition.load_image_file(temp_path)
        print(f"   Loaded Shape: {loaded_img.shape}")
        
        # Detect
        faces = face_recognition.face_locations(loaded_img, model="hog")
        print(f"✅ TEST 2 PASSED! Disk buffer works.")
        
        os.remove(temp_path)
    except Exception as e:
        print(f"❌ TEST 2 FAILED: {e}")
        print("   CRITICAL: Cannot write/read from System Temp folder.")

    print("\n--- DIAGNOSTIC COMPLETE ---")

if __name__ == "__main__":
    test_ai_system()