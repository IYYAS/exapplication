from rest_framework import serializers
from django.core.files.uploadedfile import InMemoryUploadedFile
from PIL import Image
import io
import logging
from .post_content_moderator import ImageModerationService
from .video_content_moderator import VideoModerationService  # NEW IMPORT

from .post_models import Post, PostComment, PostImage, PostLike, PostRating, PostSave, PostShare

logger = logging.getLogger(__name__)


class PostImageSerializer(serializers.ModelSerializer):
    """Serializer for post images"""
    image_url = serializers.SerializerMethodField()
    
    class Meta:
        model = PostImage
        fields = ['image_id', 'image_url', 'alt_text', 'order', 'created_at']  # Added alt_text
        read_only_fields = ['image_id', 'created_at']
    
    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image and hasattr(obj.image, 'url'):
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None

class PostCommentSerializer(serializers.ModelSerializer):
    """Serializer for post comments"""
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_username = serializers.CharField(source='user.username', read_only=True)
    comment_text = serializers.CharField(source='text')  # ← Map comment_text to text

    class Meta:
        model = PostComment
        fields = ['comment_id', 'user', 'user_email', 'user_username', 
                  'comment_text', 'created_at']
        read_only_fields = ['comment_id', 'user', 'created_at']


class PostSerializer(serializers.ModelSerializer):
    """Serializer for reading posts"""
    images = PostImageSerializer(many=True, read_only=True)
    comments = PostCommentSerializer(many=True, read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_username = serializers.CharField(source='user.username', read_only=True)
    is_liked = serializers.SerializerMethodField()
    video_url = serializers.SerializerMethodField()
    is_saved = serializers.SerializerMethodField()
    user_rating = serializers.SerializerMethodField()
    class Meta:
        model = Post
        fields = [
            'post_id', 'user', 'user_email', 'user_username',
            'post_type', 'caption', 'images', 'video_url',
            'likes_count', 'comments_count', 'shares_count', 'saves_count',
            'rating_count', 'average_rating',
            'is_liked', 'is_saved', 'user_rating', 'comments', 
            'content_status', 'created_at', 'updated_at'
        ]
        read_only_fields = ['post_id', 'user', 'created_at', 'updated_at']
    
    def get_is_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return PostLike.objects.filter(post=obj, user=request.user).exists()
        return False
    
    def get_video_url(self, obj):
        request = self.context.get('request')
        if obj.video and hasattr(obj.video, 'url'):
            if request:
                return request.build_absolute_uri(obj.video.url)
            return obj.video.url
        return None


    def get_is_saved(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return PostSave.objects.filter(post=obj, user=request.user).exists()
        return False

    def get_user_rating(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            rating = PostRating.objects.filter(post=obj, user=request.user).first()
            return rating.rating if rating else None
        return None

class PostCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating posts
    FIXED: Proper handling of images and video fields
    """
    images = serializers.ListField(
        child=serializers.FileField(max_length=100000, allow_empty_file=False),
        required=False,
        allow_empty=True,
        max_length=5,
        write_only=True  # ← Add this
    )
    video = serializers.FileField(required=False, allow_null=True, write_only=True)  # ← Add write_only
    
    class Meta:
        model = Post
        fields = ['post_type', 'caption', 'images', 'video']
    
    def validate_images(self, images):
        """
        Validate images with moderation service
        This runs BEFORE post creation
        """
        if not images:
            return images
        
        if len(images) > 5:
            raise serializers.ValidationError("Maximum 5 images allowed")
        
        logger.info(f"🔍 Starting moderation for {len(images)} image(s)")
        
        # Initialize moderation service
        moderation_service = ImageModerationService()
        rejected_images = []
        
        for idx, image_file in enumerate(images):
            # Reset file pointer
            if hasattr(image_file, 'seek'):
                image_file.seek(0)
            
            logger.info(f"📷 Checking image {idx + 1}/{len(images)}: {image_file.name}")
            
            # Check the image
            check_result = moderation_service.check_image(image_file)
            
            if not check_result['is_safe']:
                moderation_data = check_result.get('moderation', {})
                confidence = moderation_data.get('confidence', {})
                
                logger.warning(f"❌ Image {idx + 1} REJECTED: {check_result['message']}")
                
                rejected_images.append({
                    'index': idx + 1,
                    'filename': image_file.name,
                    'reason': check_result['message'],
                    'stage': check_result['stage'],
                    'unsafe_score': confidence.get('unsafe', 0) if confidence else 0,
                    'details': moderation_data.get('details', {})
                })
            else:
                logger.info(f"✅ Image {idx + 1} APPROVED")
        
        # If any images failed, raise validation error
        if rejected_images:
            logger.error(f"🚫 {len(rejected_images)} image(s) failed moderation")
            
            # Create detailed error message
            error_details = []
            for r in rejected_images:
                unsafe_parts = r.get('details', {}).get('unsafe_parts', [])
                if unsafe_parts:
                    parts_str = ', '.join([f"{p['label']} ({p['score']:.2f})" for p in unsafe_parts])
                    error_details.append(f"{r['filename']}: {parts_str}")
                else:
                    error_details.append(f"{r['filename']}: {r['reason']}")
            
            error_msg = f"Content moderation failed for {len(rejected_images)} image(s): " + "; ".join(error_details)
            raise serializers.ValidationError(error_msg)
        
        logger.info(f"✅ All {len(images)} image(s) passed moderation")
        return images
    def validate_video(self, video):
        """
        Validate video with moderation service
        Extracts frames and checks them for NSFW content
        """
        if not video:
            return video
        
        logger.info(f"🎬 Starting video moderation for: {video.name}")
        
        # Initialize video moderation service
        video_service = VideoModerationService()
        
        # Check video (extracts frames and analyzes them)
        result = video_service.check_video(video)
        
        if not result['is_safe']:
            moderation_data = result.get('moderation', {})
            details = moderation_data.get('details', {}) if moderation_data else {}
            unsafe_count = details.get('unsafe_frames_count', 0)
            unsafe_frames = details.get('unsafe_frames', [])
            
            # Create detailed error message
            if unsafe_frames:
                timestamps = [f"{uf['timestamp']}s" for uf in unsafe_frames[:3]]
                error_msg = (
                    f"Video contains inappropriate content. "
                    f"{unsafe_count} unsafe frame(s) detected at: {', '.join(timestamps)}"
                    f"{' ...' if len(unsafe_frames) > 3 else ''}"
                )
            else:
                error_msg = result['message']
            
            logger.warning(f"❌ Video rejected: {error_msg}")
            raise serializers.ValidationError(error_msg)
        
        logger.info(f"✅ Video passed moderation")
        return video
    
    def validate(self, data):
        """Validate post data"""
        post_type = data.get('post_type')
        images = data.get('images', [])
        video = data.get('video')
        caption = data.get('caption', '').strip()
        
        # Validate based on post type
        if post_type == 'image':
            if not images:
                raise serializers.ValidationError({
                    'images': 'At least one image is required for image posts'
                })
        elif post_type == 'video':
            if not video:
                raise serializers.ValidationError({
                    'video': 'Video file is required for video posts'
                })
        elif post_type == 'text':
            if not caption:
                raise serializers.ValidationError({
                    'caption': 'Caption is required for text posts'
                })
        
        return data
    
    def create(self, validated_data):
        """Create post with images - FIXED"""
        # Extract files from validated_data (they shouldn't go to Post model)
        images = validated_data.pop('images', [])
        video = validated_data.pop('video', None)
        
        # Extract user (passed from view)
        user = validated_data.pop('user', None)
        
        # Create post with only the fields that belong to Post model
        post = Post.objects.create(
            user=user,
            post_type=validated_data.get('post_type'),
            caption=validated_data.get('caption', ''),
            video=video  # This is handled by Post model's video field
        )
        
        # Create PostImage instances for each image
        for idx, image_file in enumerate(images):
            PostImage.objects.create(
                post=post,
                image=image_file,
                order=idx
            )
        
        logger.info(f"✅ Post created: ID={post.post_id}, Images={len(images)}")
        return post
    

class PostRatingSerializer(serializers.ModelSerializer):
    user_username = serializers.CharField(source='user.username', read_only=True)
    
    class Meta:
        model = PostRating
        fields = ['id', 'user', 'user_username', 'rating', 'created_at']
        read_only_fields = ['id', 'user', 'created_at']
