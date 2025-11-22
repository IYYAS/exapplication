"""
Video Content Moderation Utility using NudeNet v3.x
File: MainApplication/Post/video_content_moderator.py

Extracts frames from videos and checks them for NSFW content
"""

import os
import tempfile
import shutil
import logging
import cv2
from django.conf import settings
from django.core.files.uploadedfile import InMemoryUploadedFile
from .post_content_moderator import NudeNetContentModerator

logger = logging.getLogger(__name__)


class VideoValidator:
    """Basic video file validation"""
    
    ALLOWED_EXTENSIONS = ['.mp4', '.avi', '.mov', '.mkv', '.webm']
    ALLOWED_MIME_TYPES = [
        'video/mp4', 'video/avi', 'video/quicktime',
        'video/x-matroska', 'video/webm'
    ]
    MAX_SIZE = 20 * 1024 * 1024  # 20MB
    
    @classmethod
    def validate_video(cls, video_file):
        """Validate video file format and size"""
        try:
            if hasattr(video_file, 'seek'):
                video_file.seek(0)
            
            # Check extension
            ext = os.path.splitext(video_file.name)[1].lower()
            if ext not in cls.ALLOWED_EXTENSIONS:
                return {
                    'is_valid': False,
                    'message': f'Invalid format: {ext}. Allowed: {", ".join(cls.ALLOWED_EXTENSIONS)}'
                }
            
            # Check content type
            content_type = getattr(video_file, 'content_type', None)
            if content_type and content_type not in cls.ALLOWED_MIME_TYPES:
                return {
                    'is_valid': False,
                    'message': f'Invalid content type: {content_type}'
                }
            
            # Check size
            if video_file.size > cls.MAX_SIZE:
                size_mb = round(video_file.size / (1024 * 1024), 2)
                return {
                    'is_valid': False,
                    'message': f'File too large: {size_mb}MB (max 20MB)'
                }
            
            logger.info(f"✅ Video validated: {video_file.name}, {video_file.size} bytes")
            
            return {
                'is_valid': True,
                'message': 'Video validated',
                'details': {
                    'filename': video_file.name,
                    'size': video_file.size,
                    'extension': ext,
                    'content_type': content_type
                }
            }
            
        except Exception as e:
            return {
                'is_valid': False,
                'message': f'Validation error: {str(e)}'
            }
        finally:
            if hasattr(video_file, 'seek'):
                try:
                    video_file.seek(0)
                except:
                    pass


class NudeNetVideoModerator:
    """
    Video content moderation using NudeNet v3.x
    Extracts frames and analyzes them for NSFW content
    """
    
    # Frame extraction settings
    DEFAULT_FRAME_INTERVAL = 2  # Extract 1 frame every N seconds
    MAX_FRAMES = 30             # Maximum frames to analyze
    MIN_FRAMES = 5              # Minimum frames to analyze
    
    def __init__(self):
        self.enabled = getattr(settings, 'CONTENT_MODERATION_ENABLED', True)
        self.image_moderator = NudeNetContentModerator()
        logger.info("🎬 NudeNetVideoModerator initialized")
    
    def check_video(self, video_file, frame_interval=None):
        """
        Check video for NSFW content by extracting and analyzing frames
        
        Args:
            video_file: Uploaded video file
            frame_interval: Seconds between frame extractions (default: 2)
        
        Returns:
            dict with is_safe, message, confidence, and details
        """
        if not self.enabled:
            logger.warning("⚠️ Video moderation DISABLED - approving by default")
            return {
                'is_safe': True,
                'message': 'Video moderation disabled',
                'confidence': None,
                'details': {'reason': 'moderation_disabled'}
            }
        
        if frame_interval is None:
            frame_interval = self.DEFAULT_FRAME_INTERVAL
        
        temp_video_path = None
        temp_frames_dir = None
        
        try:
            # Reset file pointer
            if hasattr(video_file, 'seek'):
                video_file.seek(0)
            
            filename = getattr(video_file, 'name', 'unknown')
            logger.info("=" * 60)
            logger.info(f"🎬 Checking video: {filename}")
            logger.info("=" * 60)
            
            # Save video to temp file
            temp_video_path = self._save_temp_video(video_file)
            logger.info(f"💾 Temp video: {temp_video_path}")
            
            # Extract frames
            logger.info(f"🎞️ Extracting frames (interval: {frame_interval}s)...")
            extraction_result = self._extract_frames(temp_video_path, frame_interval)
            
            if not extraction_result['success']:
                return {
                    'is_safe': False,
                    'message': extraction_result['message'],
                    'confidence': None,
                    'details': extraction_result
                }
            
            frame_paths = extraction_result['frames']
            temp_frames_dir = extraction_result['temp_dir']
            duration = extraction_result.get('duration', 0)
            
            logger.info(f"✅ Extracted {len(frame_paths)} frames")
            logger.info(f"📊 Video duration: {duration:.2f}s")
            
            # Analyze each frame
            logger.info("🔍 Analyzing frames...")
            unsafe_frames = []
            max_unsafe_score = 0.0
            
            for idx, frame_path in enumerate(frame_paths):
                frame_num = extraction_result['frame_numbers'][idx]
                timestamp = extraction_result['timestamps'][idx]
                
                # Check frame with image moderator
                result = self._check_frame(frame_path)
                
                unsafe_score = result.get('confidence', {}).get('unsafe', 0)
                max_unsafe_score = max(max_unsafe_score, unsafe_score)
                
                if not result['is_safe']:
                    unsafe_frames.append({
                        'frame_index': idx,
                        'frame_number': frame_num,
                        'timestamp': round(timestamp, 2),
                        'unsafe_score': unsafe_score,
                        'details': result.get('details', {})
                    })
                    logger.warning(f"   ❌ Frame {idx+1} ({timestamp:.2f}s): UNSAFE")
                else:
                    logger.info(f"   ✅ Frame {idx+1} ({timestamp:.2f}s): safe")
            
            # Calculate results
            is_safe = len(unsafe_frames) == 0
            safe_score = 1.0 - max_unsafe_score
            
            logger.info("=" * 60)
            logger.info(f"📊 Video Analysis Results:")
            logger.info(f"   Frames checked:   {len(frame_paths)}")
            logger.info(f"   Unsafe frames:    {len(unsafe_frames)}")
            logger.info(f"   Max unsafe score: {max_unsafe_score:.4f}")
            
            if is_safe:
                logger.info(f"✅ VIDEO APPROVED")
            else:
                logger.warning(f"❌ VIDEO REJECTED")
                for uf in unsafe_frames:
                    logger.warning(f"   - {uf['timestamp']}s: score {uf['unsafe_score']:.4f}")
            
            logger.info("=" * 60)
            
            return {
                'is_safe': is_safe,
                'message': 'Video passed moderation' if is_safe else 
                          f'Inappropriate content found in {len(unsafe_frames)} frame(s)',
                'confidence': {
                    'safe': round(safe_score, 4),
                    'unsafe': round(max_unsafe_score, 4)
                },
                'details': {
                    'duration': round(duration, 2),
                    'frames_checked': len(frame_paths),
                    'unsafe_frames_count': len(unsafe_frames),
                    'unsafe_frames': unsafe_frames,
                    'frame_interval': frame_interval,
                    'decision': 'approved' if is_safe else 'rejected'
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Video moderation error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            # SECURITY: Reject on error
            return {
                'is_safe': False,
                'message': f'Video moderation failed: {str(e)}',
                'confidence': None,
                'details': {'error': str(e)}
            }
        
        finally:
            # Reset file pointer
            if hasattr(video_file, 'seek'):
                try:
                    video_file.seek(0)
                except:
                    pass
            
            # Cleanup temp files
            self._cleanup(temp_video_path, temp_frames_dir)
    
    def _save_temp_video(self, video_file):
        """Save uploaded video to temporary file"""
        if hasattr(video_file, 'seek'):
            video_file.seek(0)
        
        ext = os.path.splitext(video_file.name)[1] or '.mp4'
        temp_fd, temp_path = tempfile.mkstemp(suffix=ext)
        
        try:
            with os.fdopen(temp_fd, 'wb') as f:
                if isinstance(video_file, InMemoryUploadedFile):
                    for chunk in video_file.chunks():
                        f.write(chunk)
                elif hasattr(video_file, 'read'):
                    f.write(video_file.read())
                else:
                    raise ValueError(f"Unsupported file type: {type(video_file)}")
            
            if hasattr(video_file, 'seek'):
                video_file.seek(0)
            
            return temp_path
            
        except Exception as e:
            logger.error(f"❌ Error saving temp video: {e}")
            raise
    
    def _extract_frames(self, video_path, interval_seconds):
        """Extract frames from video at specified intervals"""
        temp_dir = tempfile.mkdtemp(prefix='video_mod_')
        frame_paths = []
        frame_numbers = []
        timestamps = []
        
        try:
            cap = cv2.VideoCapture(video_path)
            
            if not cap.isOpened():
                return {
                    'success': False,
                    'message': 'Failed to open video file',
                    'frames': [],
                    'temp_dir': temp_dir
                }
            
            # Get video properties
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = total_frames / fps if fps > 0 else 0
            
            logger.info(f"   📹 {duration:.2f}s | {fps:.2f}fps | {total_frames} total frames")
            
            # Calculate which frames to extract
            frame_interval = max(1, int(fps * interval_seconds))
            frames_to_extract = list(range(0, total_frames, frame_interval))
            
            # Limit frames
            if len(frames_to_extract) > self.MAX_FRAMES:
                step = len(frames_to_extract) // self.MAX_FRAMES
                frames_to_extract = frames_to_extract[::step][:self.MAX_FRAMES]
            
            # Ensure minimum
            if len(frames_to_extract) < self.MIN_FRAMES and total_frames >= self.MIN_FRAMES:
                step = max(1, total_frames // self.MIN_FRAMES)
                frames_to_extract = list(range(0, total_frames, step))[:self.MIN_FRAMES]
            
            # Extract frames
            for idx, frame_num in enumerate(frames_to_extract):
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                ret, frame = cap.read()
                
                if ret:
                    frame_path = os.path.join(temp_dir, f'frame_{idx:04d}.jpg')
                    cv2.imwrite(frame_path, frame)
                    
                    frame_paths.append(frame_path)
                    frame_numbers.append(frame_num)
                    timestamps.append(frame_num / fps if fps > 0 else 0)
            
            cap.release()
            
            return {
                'success': True,
                'frames': frame_paths,
                'frame_numbers': frame_numbers,
                'timestamps': timestamps,
                'temp_dir': temp_dir,
                'duration': duration,
                'fps': fps,
                'total_frames': total_frames
            }
            
        except Exception as e:
            logger.error(f"❌ Frame extraction error: {e}")
            return {
                'success': False,
                'message': f'Frame extraction failed: {str(e)}',
                'frames': [],
                'temp_dir': temp_dir
            }
    
    def _check_frame(self, frame_path):
        """Check a single frame using the image moderator"""
        try:
            if self.image_moderator.detector is None:
                return {
                    'is_safe': False,
                    'message': 'Detector not initialized',
                    'confidence': None,
                    'details': {}
                }
            
            detections = self.image_moderator.detector.detect(frame_path)
            
            UNSAFE_LABELS = {
                'FEMALE_GENITALIA_EXPOSED', 'MALE_GENITALIA_EXPOSED',
                'FEMALE_BREAST_EXPOSED', 'BUTTOCKS_EXPOSED', 'ANUS_EXPOSED',
                'EXPOSED_GENITALIA_F', 'EXPOSED_GENITALIA_M',
                'EXPOSED_BREAST_F', 'EXPOSED_BUTTOCKS', 'EXPOSED_ANUS',
                'MALE_BREAST_EXPOSED', 'BELLY_EXPOSED',
            }
            
            unsafe_parts = []
            max_score = 0.0
            
            for det in detections:
                label = det.get('class') or det.get('label', '')
                score = det.get('score', 0.0)
                
                if label in UNSAFE_LABELS and score >= self.image_moderator.unsafe_threshold:
                    unsafe_parts.append({'label': label, 'score': score})
                    max_score = max(max_score, score)
            
            is_safe = len(unsafe_parts) == 0
            
            return {
                'is_safe': is_safe,
                'message': 'Frame checked',
                'confidence': {
                    'safe': round(1.0 - max_score, 4),
                    'unsafe': round(max_score, 4)
                },
                'details': {
                    'unsafe_parts': unsafe_parts
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Frame check error: {e}")
            return {
                'is_safe': False,
                'message': f'Check failed: {str(e)}',
                'confidence': None,
                'details': {'error': str(e)}
            }
    
    def _cleanup(self, video_path, frames_dir):
        """Clean up temporary files"""
        try:
            if video_path and os.path.exists(video_path):
                os.remove(video_path)
                logger.debug(f"🗑️ Removed: {video_path}")
        except Exception as e:
            logger.warning(f"⚠️ Cleanup video failed: {e}")
        
        try:
            if frames_dir and os.path.exists(frames_dir):
                shutil.rmtree(frames_dir)
                logger.debug(f"🗑️ Removed: {frames_dir}")
        except Exception as e:
            logger.warning(f"⚠️ Cleanup frames failed: {e}")


class VideoModerationService:
    """Combined validation and moderation service for videos"""
    
    def __init__(self):
        self.validator = VideoValidator()
        self.moderator = NudeNetVideoModerator()
        logger.info("🚀 VideoModerationService initialized")
    
    def check_video(self, video_file, frame_interval=None):
        """Complete video check: validation + NSFW detection"""
        if hasattr(video_file, 'seek'):
            video_file.seek(0)
        
        logger.info("=" * 70)
        logger.info(f"🎬 STARTING VIDEO MODERATION: {getattr(video_file, 'name', 'unknown')}")
        logger.info("=" * 70)
        
        # Step 1: Validation
        logger.info("📋 Step 1: Basic Validation")
        validation = self.validator.validate_video(video_file)
        
        if not validation['is_valid']:
            logger.warning(f"❌ Validation failed: {validation['message']}")
            return {
                'is_safe': False,
                'message': validation['message'],
                'stage': 'validation',
                'validation': validation,
                'moderation': None
            }
        
        logger.info("✅ Validation passed\n")
        
        # Step 2: NSFW Detection
        logger.info("🤖 Step 2: NSFW Detection")
        moderation = self.moderator.check_video(video_file, frame_interval)
        
        if not moderation['is_safe']:
            logger.warning(f"❌ Moderation failed: {moderation['message']}")
            return {
                'is_safe': False,
                'message': moderation['message'],
                'stage': 'moderation',
                'validation': validation,
                'moderation': moderation
            }
        
        logger.info("=" * 70)
        logger.info("✅ VIDEO APPROVED")
        logger.info("=" * 70)
        
        if hasattr(video_file, 'seek'):
            video_file.seek(0)
        
        return {
            'is_safe': True,
            'message': 'Video passed all checks',
            'stage': 'completed',
            'validation': validation,
            'moderation': moderation
        }