"""
Content Moderation Utility using NudeNet v3.x
FIXED: Updated for actual NudeNet 3.x label names and detection logic
"""

import os
import tempfile
import logging
from PIL import Image
from django.conf import settings
from django.core.files.uploadedfile import InMemoryUploadedFile

# Setup logging
logger = logging.getLogger(__name__)


class NudeNetContentModerator:
    """
    Content moderation service using NudeNet v3.x
    FIXED: Corrected label names and detection logic
    """
    
    def __init__(self):
        self.enabled = getattr(settings, 'CONTENT_MODERATION_ENABLED', True)
        self.detector = None
        
        # CRITICAL: Lower threshold = stricter detection
        # For zero-tolerance NSFW content, use 0.3-0.4
        self.unsafe_threshold = 0.35  # Balanced threshold
        
        if self.enabled:
            self._init_models()
    
    def _init_models(self):
        """Initialize NudeNet v3.x detector"""
        try:
            logger.info("=" * 60)
            logger.info("Initializing NudeNet v3.x...")
            
            from nudenet import NudeDetector
            
            # Initialize detector
            self.detector = NudeDetector()
            
            logger.info("✓ NudeNet v3.x detector initialized")
            logger.info(f"✓ Unsafe threshold: {self.unsafe_threshold}")
            logger.info("=" * 60)
            
        except ImportError as e:
            logger.error(f"NudeNet not installed: {e}")
            logger.error("Install with: pip install nudenet")
            self.enabled = False
        except Exception as e:
            logger.error(f"Error initializing NudeNet: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.enabled = False
    
    def check_image(self, image_file):
        """
        Check image for NSFW content using NudeNet v3.x
        FIXED: Proper label detection and file handling
        """
        if not self.enabled:
            logger.warning("⚠️  Content moderation DISABLED - approving by default")
            return {
                'is_safe': True,
                'message': 'Content moderation disabled',
                'confidence': None,
                'details': {'reason': 'moderation_disabled'}
            }
        
        if self.detector is None:
            logger.error("❌ NudeNet detector not initialized")
            # SECURITY: Reject if detector fails
            return {
                'is_safe': False,
                'message': 'Content moderation not available',
                'confidence': None,
                'details': {'reason': 'detector_not_initialized'}
            }
        
        temp_file_path = None
        
        try:
            # Reset file pointer
            if hasattr(image_file, 'seek'):
                image_file.seek(0)
            
            filename = getattr(image_file, 'name', 'unknown')
            logger.info("=" * 60)
            logger.info(f"🔍 Checking image: {filename}")
            
            # Save to temp file
            temp_file_path = self._save_temp_file(image_file)
            logger.info(f"💾 Temp file: {temp_file_path}")
            
            # Reset file pointer after saving
            if hasattr(image_file, 'seek'):
                image_file.seek(0)
            
            # Run NudeNet detection
            logger.info("🤖 Running NudeNet detection...")
            detections = self.detector.detect(temp_file_path)
            
            logger.info(f"📦 Detections found: {len(detections)}")
            logger.info(f"📦 Raw output: {detections}")
            
            # FIXED: Correct NudeNet v3.x label names
            # These are the actual labels returned by NudeNet v3.x
            UNSAFE_LABELS = {
                # Primary NSFW labels (NudeNet v3.x)
                'FEMALE_GENITALIA_EXPOSED',
                'MALE_GENITALIA_EXPOSED',
                'FEMALE_BREAST_EXPOSED',
                'BUTTOCKS_EXPOSED',
                'ANUS_EXPOSED',
                
                # Alternative label formats (some versions use these)
                'EXPOSED_GENITALIA_F',
                'EXPOSED_GENITALIA_M',
                'EXPOSED_BREAST_F',
                'EXPOSED_BUTTOCKS',
                'EXPOSED_ANUS',
                
                # Additional exposed body parts
                'MALE_BREAST_EXPOSED',
                'BELLY_EXPOSED',
                'ARMPITS_EXPOSED',
                
                # Underwear/lingerie (optional - uncomment to block)
                # 'FACE_F',
                # 'FACE_M',
            }
            
            # Analyze detections
            unsafe_detections = []
            max_unsafe_score = 0.0
            all_labels = set()
            
            for detection in detections:
                # Get label (handle both 'class' and 'label' keys)
                label = detection.get('class') or detection.get('label', '')
                score = detection.get('score', 0.0)
                all_labels.add(label)
                
                logger.info(f"   - Detected: {label} (score: {score:.4f})")
                
                # Check if label is unsafe
                if label in UNSAFE_LABELS and score >= self.unsafe_threshold:
                    unsafe_detections.append({
                        'label': label,
                        'score': score,
                        'box': detection.get('box', [])
                    })
                    max_unsafe_score = max(max_unsafe_score, score)
            
            # Calculate safety
            is_unsafe = len(unsafe_detections) > 0
            safe_score = 1.0 - max_unsafe_score if unsafe_detections else 1.0
            unsafe_score = max_unsafe_score
            
            # Log results
            logger.info("📊 Analysis Results:")
            logger.info(f"   Total detections:  {len(detections)}")
            logger.info(f"   All labels found:  {all_labels}")
            logger.info(f"   Unsafe detections: {len(unsafe_detections)}")
            logger.info(f"   Max unsafe score:  {unsafe_score:.4f} ({unsafe_score*100:.2f}%)")
            logger.info(f"   Threshold:         {self.unsafe_threshold:.4f}")
            
            if unsafe_detections:
                logger.info("   ⚠️  Unsafe content detected:")
                for det in unsafe_detections:
                    logger.info(f"      - {det['label']}: {det['score']:.4f}")
            
            is_safe = not is_unsafe
            
            if is_safe:
                logger.info(f"✅ APPROVED: Image passed moderation")
            else:
                logger.warning(f"❌ REJECTED: Unsafe content detected")
            
            logger.info("=" * 60)
            
            return {
                'is_safe': is_safe,
                'message': 'Content checked successfully',
                'confidence': {
                    'safe': round(safe_score, 4),
                    'unsafe': round(unsafe_score, 4)
                },
                'details': {
                    'total_detections': len(detections),
                    'all_labels': list(all_labels),
                    'unsafe_detections': len(unsafe_detections),
                    'unsafe_parts': [{'label': d['label'], 'score': d['score']} for d in unsafe_detections],
                    'threshold': self.unsafe_threshold,
                    'decision': 'approved' if is_safe else 'rejected',
                    'reason': f"Max unsafe score {unsafe_score:.4f} {'<' if is_safe else '>='} threshold {self.unsafe_threshold:.4f}"
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Content moderation error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            # SECURITY: Reject on error for safety
            return {
                'is_safe': False,
                'message': f'Moderation check failed: {str(e)}',
                'confidence': None,
                'details': {'error': str(e)}
            }
        
        finally:
            # Reset file pointer
            if hasattr(image_file, 'seek'):
                try:
                    image_file.seek(0)
                except:
                    pass
            
            # Clean up temp file
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                    logger.debug(f"🗑️  Cleaned up: {temp_file_path}")
                except Exception as e:
                    logger.warning(f"⚠️  Cleanup failed: {e}")
    
    def _save_temp_file(self, image_file):
        """Save uploaded file to temporary location"""
        if hasattr(image_file, 'seek'):
            image_file.seek(0)
        
        suffix = self._get_file_extension(image_file)
        temp_fd, temp_path = tempfile.mkstemp(suffix=suffix)
        
        try:
            with os.fdopen(temp_fd, 'wb') as temp_file:
                if isinstance(image_file, InMemoryUploadedFile):
                    for chunk in image_file.chunks():
                        temp_file.write(chunk)
                elif hasattr(image_file, 'read'):
                    content = image_file.read()
                    temp_file.write(content)
                else:
                    raise ValueError(f"Unsupported file type: {type(image_file)}")
            
            # Reset file pointer
            if hasattr(image_file, 'seek'):
                image_file.seek(0)
            
            return temp_path
            
        except Exception as e:
            logger.error(f"❌ Error saving temp file: {e}")
            raise
    
    def _get_file_extension(self, image_file):
        """Get file extension"""
        if hasattr(image_file, 'name'):
            ext = os.path.splitext(image_file.name)[1]
            return ext if ext else '.jpg'
        return '.jpg'


class SimpleImageValidator:
    """Basic image validation"""
    
    ALLOWED_EXTENSIONS = ['.jpg', '.jpeg', '.png']
    ALLOWED_MIME_TYPES = ['image/jpeg', 'image/png', 'image/jpg']
    MAX_SIZE = 20 * 1024 * 1024  # 20MB
    MAX_DIMENSION = 10000
    
    @classmethod
    def validate_image(cls, image_file):
        """Validate image file"""
        try:
            if hasattr(image_file, 'seek'):
                image_file.seek(0)
            
            # Check extension
            ext = os.path.splitext(image_file.name)[1].lower()
            if ext not in cls.ALLOWED_EXTENSIONS:
                return {
                    'is_safe': False,
                    'message': f'Invalid file format: {ext}. Only JPG and PNG allowed.',
                    'details': {}
                }
            
            # Check content type
            content_type = getattr(image_file, 'content_type', None)
            if content_type and content_type not in cls.ALLOWED_MIME_TYPES:
                return {
                    'is_safe': False,
                    'message': f'Invalid content type: {content_type}',
                    'details': {}
                }
            
            # Check size
            if image_file.size > cls.MAX_SIZE:
                size_mb = round(image_file.size / (1024 * 1024), 2)
                return {
                    'is_safe': False,
                    'message': f'File too large: {size_mb}MB (max 20MB)',
                    'details': {}
                }
            
            # Validate with PIL
            try:
                image = Image.open(image_file)
                image.verify()
                
                if hasattr(image_file, 'seek'):
                    image_file.seek(0)
                
                image = Image.open(image_file)
                width, height = image.size
                image_format = image.format
                
                if width > cls.MAX_DIMENSION or height > cls.MAX_DIMENSION:
                    return {
                        'is_safe': False,
                        'message': f'Image too large: {width}x{height}',
                        'details': {}
                    }
                
                logger.info(f"✅ Image valid: {width}x{height} {image_format}")
                
                return {
                    'is_safe': True,
                    'message': 'Image validated',
                    'details': {
                        'width': width,
                        'height': height,
                        'format': image_format
                    }
                }
                
            except Exception as e:
                return {
                    'is_safe': False,
                    'message': f'Invalid image: {str(e)}',
                    'details': {}
                }
            
        finally:
            if hasattr(image_file, 'seek'):
                try:
                    image_file.seek(0)
                except:
                    pass


class ImageModerationService:
    """Combined validation and moderation service"""
    
    def __init__(self):
        self.validator = SimpleImageValidator()
        self.moderator = NudeNetContentModerator()
        logger.info("🚀 ImageModerationService initialized")
    
    def check_image(self, image_file):
        """Complete image check"""
        if hasattr(image_file, 'seek'):
            image_file.seek(0)
        
        logger.info("=" * 70)
        logger.info(f"🔍 STARTING MODERATION: {getattr(image_file, 'name', 'unknown')}")
        logger.info("=" * 70)
        
        # Step 1: Validation
        logger.info("📋 Step 1: Basic Validation")
        validation_result = self.validator.validate_image(image_file)
        
        if not validation_result['is_safe']:
            logger.warning(f"❌ Validation failed: {validation_result['message']}")
            return {
                'is_safe': False,
                'message': validation_result['message'],
                'stage': 'validation',
                'validation': validation_result,
                'moderation': None
            }
        
        logger.info("✅ Validation passed\n")
        
        # Step 2: NSFW Detection
        logger.info("🤖 Step 2: NSFW Detection")
        moderation_result = self.moderator.check_image(image_file)
        
        if not moderation_result['is_safe']:
            logger.warning(f"❌ Moderation failed: {moderation_result['message']}")
            return {
                'is_safe': False,
                'message': 'Image contains inappropriate content',
                'stage': 'moderation',
                'validation': validation_result,
                'moderation': moderation_result
            }
        
        logger.info("=" * 70)
        logger.info("✅ IMAGE APPROVED")
        logger.info("=" * 70)
        
        if hasattr(image_file, 'seek'):
            image_file.seek(0)
        
        return {
            'is_safe': True,
            'message': 'Image passed all checks',
            'stage': 'completed',
            'validation': validation_result,
            'moderation': moderation_result
        }