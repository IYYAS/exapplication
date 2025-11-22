# posts/post_views.py
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.utils import timezone
from MainApplication.notifications import send_push_notification

import logging
from .post_models import Post, PostLike, PostComment, PostImage, PostSave, PostShare, PostRating
from .post_serializers import (
    PostSerializer, 
    PostCreateSerializer, 
    PostCommentSerializer,
    PostImageSerializer
)
from .post_content_moderator import ImageModerationService
from django.db import transaction
from django.db import models
from ..Credit.credit_models import CreditTransactionLog, UserCreditVault, CreditModel, CreditCostsModel
# Setup logging
logger = logging.getLogger(__name__)


class PostListCreateView(APIView):
    """
    GET: List all posts
    POST: Create a new post (image/video/text)
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
    def get(self, request):
        """Get all posts or filter by user_id"""
        user_id = request.query_params.get('user_id', None)
        
        queryset = Post.objects.filter(
            is_deleted=False, 
            is_active=True,
            content_status='approved'  # Only show approved content
        )
        
        if user_id:
            queryset = queryset.filter(user__id=user_id)
        
        queryset = queryset.select_related('user').prefetch_related(
            'images', 'comments', 'likes'
        ).order_by('-created_at')
        
        serializer = PostSerializer(queryset, many=True, context={'request': request})
        return Response({
            'success': True,
            'count': queryset.count(),
            'posts': serializer.data
        }, status=status.HTTP_200_OK)
    
    def post(self, request):
        """
        Create a new post
        Supports: image (up to 5), video, or text posts
        """
        serializer = PostCreateSerializer(data=request.data)
        
        if serializer.is_valid():
            # Save post with current user
            post = serializer.save(user=request.user)
            
            # Return full post details
            output_serializer = PostSerializer(post, context={'request': request})
            return Response({
                'success': True,
                'message': 'Post created successfully',
                'post': output_serializer.data
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class PostDetailView(APIView):
    """
    GET: Retrieve a single post
    PUT/PATCH: Update a post (only owner)
    DELETE: Delete a post (only owner)
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
    def get_object(self, pk):
        """Get post by ID"""
        return get_object_or_404(Post, pk=pk, is_deleted=False, is_active=True)
    
    def get(self, request, pk):
        """Get single post details"""
        post = self.get_object(pk)
        serializer = PostSerializer(post, context={'request': request})
        return Response({
            'success': True,
            'post': serializer.data
        }, status=status.HTTP_200_OK)
    
    def patch(self, request, pk):
        """Partial update of post"""
        post = self.get_object(pk)
        
        # Check ownership
        if post.user != request.user:
            return Response({
                'success': False,
                'error': 'You do not have permission to edit this post'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Only allow caption updates for now
        caption = request.data.get('caption')
        if caption is not None:
            post.caption = caption
            post.save()
        
        output_serializer = PostSerializer(post, context={'request': request})
        return Response({
            'success': True,
            'message': 'Post updated successfully',
            'post': output_serializer.data
        }, status=status.HTTP_200_OK)
    
    def delete(self, request, pk):
        """Soft delete a post"""
        post = self.get_object(pk)
        
        # Check ownership
        if post.user != request.user:
            return Response({
                'success': False,
                'error': 'You do not have permission to delete this post'
            }, status=status.HTTP_403_FORBIDDEN)
        
        post.is_deleted = True
        post.deleted_at = timezone.now()
        post.save()
        
        return Response({
            'success': True,
            'message': 'Post deleted successfully'
        }, status=status.HTTP_200_OK)


class PostImageCreateView(APIView):
    """
    POST: Create an image post with up to 5 images
    Moderation now happens in serializer validation
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    
    def post(self, request):
        """Create image post with multiple images"""
        
        logger.info(f"📸 NEW IMAGE POST REQUEST from {request.user.email}")
        
        # Extract images
        images = []
        for i in range(1, 6):
            image_key = f'image{i}' if i > 1 else 'image'
            if image_key in request.FILES:
                images.append(request.FILES[image_key])
        
        if 'images' in request.FILES:
            images.extend(request.FILES.getlist('images'))
        
        images = list(dict.fromkeys(images))[:5]
        
        if not images:
            return Response({
                'success': False,
                'error': 'At least one image is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Prepare data
        data = {
            'caption': request.data.get('caption', ''),
            'post_type': 'image',
            'images': images
        }
        
        # Validate (moderation happens here automatically)
        serializer = PostCreateSerializer(data=data)
        
        if serializer.is_valid():
            # All images passed moderation, create post
            post = serializer.save(user=request.user)
            logger.info(f"✅ Post created: ID={post.post_id}")
            
            output_serializer = PostSerializer(post, context={'request': request})
            return Response({
                'success': True,
                'message': f'Image post created successfully with {len(images)} image(s)',
                'post': output_serializer.data
            }, status=status.HTTP_201_CREATED)
        
        # Validation failed (including moderation)
        logger.warning(f"❌ Post creation failed: {serializer.errors}")
        return Response({
            'success': False,
            'error': 'Failed to create post',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
class PostVideoCreateView(APIView):
    """
    POST: Create a video post
    Max size: 20MB
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    
    def post(self, request):
        """Create video post"""
        if 'video' not in request.FILES:
            return Response({
                'success': False,
                'error': 'Video file is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        data = {
            'caption': request.data.get('caption', ''),
            'post_type': 'video',
            'video': request.FILES['video']
        }
        
        serializer = PostCreateSerializer(data=data)
        
        if serializer.is_valid():
            post = serializer.save(user=request.user)
            output_serializer = PostSerializer(post, context={'request': request})
            return Response({
                'success': True,
                'message': 'Video post created successfully',
                'post': output_serializer.data
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)




class PostCommentListCreateView(APIView):
    """
    GET: Get all comments for a post
    POST: Add a comment to a post
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, pk):
        """Get all comments for a post"""
        post = get_object_or_404(Post, pk=pk, is_deleted=False, is_active=True)
        comments = post.comments.all().order_by('-created_at')
        serializer = PostCommentSerializer(comments, many=True)
        return Response({
            'success': True,
            'count': comments.count(),
            'comments': serializer.data
        }, status=status.HTTP_200_OK)
    
    def post(self, request, pk):
        """Add a comment to a post"""
        post = get_object_or_404(Post, pk=pk, is_deleted=False, is_active=True)
        
        serializer = PostCommentSerializer(data=request.data)
        
        if serializer.is_valid():
            comment = serializer.save(user=request.user, post=post)
            
            # Increment comment count
            post.comments_count += 1
            post.save()
            
            return Response({
                'success': True,
                'message': 'Comment added successfully',
                'comment': PostCommentSerializer(comment).data
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class PostCommentDetailView(APIView):
    """
    DELETE: Delete a comment (only owner)
    PATCH: Update a comment (only owner)
    """
    permission_classes = [IsAuthenticated]
    
    def get_object(self, pk, comment_id):
        """Get comment by ID"""
        post = get_object_or_404(Post, pk=pk, is_deleted=False, is_active=True)
        return get_object_or_404(PostComment, comment_id=comment_id, post=post)
    
    def patch(self, request, pk, comment_id):
        """Update a comment"""
        comment = self.get_object(pk, comment_id)
        
        # Check ownership
        if comment.user != request.user:
            return Response({
                'success': False,
                'error': 'You do not have permission to edit this comment'
            }, status=status.HTTP_403_FORBIDDEN)
        
        serializer = PostCommentSerializer(comment, data=request.data, partial=True)
        
        if serializer.is_valid():
            serializer.save()
            return Response({
                'success': True,
                'message': 'Comment updated successfully',
                'comment': serializer.data
            }, status=status.HTTP_200_OK)
        
        return Response({
            'success': False,
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, pk, comment_id):
        """Delete a comment"""
        comment = self.get_object(pk, comment_id)
        
        # Check ownership
        if comment.user != request.user:
            return Response({
                'success': False,
                'error': 'You do not have permission to delete this comment'
            }, status=status.HTTP_403_FORBIDDEN)
        
        post = comment.post
        comment.delete()
        
        # Decrement comment count
        post.comments_count = max(0, post.comments_count - 1)
        post.save()
        
        return Response({
            'success': True,
            'message': 'Comment deleted successfully'
        }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_posts(request):
    """Get all posts by the current user"""
    posts = Post.objects.filter(
        user=request.user,
        is_deleted=False,
        is_active=True
    ).select_related('user').prefetch_related(
        'images', 'comments', 'likes'
    ).order_by('-created_at')
    
    serializer = PostSerializer(posts, many=True, context={'request': request})
    return Response({
        'success': True,
        'count': posts.count(),
        'posts': serializer.data
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def feed(request):
    """Get feed of posts (all posts or following users)"""
    posts = Post.objects.filter(
        is_deleted=False,
        is_active=True,
        content_status='approved'
    ).select_related('user').prefetch_related(
        'images', 'comments', 'likes'
    ).order_by('-created_at')[:50]
    
    serializer = PostSerializer(posts, many=True, context={'request': request})
    return Response({
        'success': True,
        'count': posts.count(),
        'posts': serializer.data
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_posts(request, user_id):
    """Get all posts by a specific user"""
    posts = Post.objects.filter(
        user__id=user_id,
        is_deleted=False,
        is_active=True,
        content_status='approved'
    ).select_related('user').prefetch_related(
        'images', 'comments', 'likes'
    ).order_by('-created_at')
    
    serializer = PostSerializer(posts, many=True, context={'request': request})
    return Response({
        'success': True,
        'count': posts.count(),
        'posts': serializer.data
    }, status=status.HTTP_200_OK)


class PostSaveView(APIView):
    """POST: Save or unsave a post (bookmark) - FREE"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, pk):
        post = get_object_or_404(Post, pk=pk, is_deleted=False, is_active=True)
        
        save, created = PostSave.objects.get_or_create(post=post, user=request.user)
        
        if not created:
            # Unsave
            save.delete()
            post.saves_count = max(0, post.saves_count - 1)
            post.save()
            return Response({
                'success': True,
                'message': 'Post unsaved',
                'saved': False,
                'saves_count': post.saves_count
            }, status=status.HTTP_200_OK)
        else:
            # Save
            post.saves_count += 1
            post.save()
            return Response({
                'success': True,
                'message': 'Post saved',
                'saved': True,
                'saves_count': post.saves_count
            }, status=status.HTTP_201_CREATED)


class PostShareView(APIView):
    """POST: Share a post - FREE (just tracks sharing)"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, pk):
        post = get_object_or_404(Post, pk=pk, is_deleted=False, is_active=True)
        
        # Create share record
        PostShare.objects.create(post=post, user=request.user)
        
        # Increment share count
        post.shares_count += 1
        post.save()
        
        return Response({
            'success': True,
            'message': 'Post shared successfully',
            'shares_count': post.shares_count
        }, status=status.HTTP_201_CREATED)


class PostRatingView(APIView):
    """POST: Rate a post (1-5 stars) - COSTS CREDITS"""
    permission_classes = [IsAuthenticated]
    
    @transaction.atomic
    def post(self, request, pk):
        post = get_object_or_404(Post, pk=pk, is_deleted=False, is_active=True)
        rating_value = request.data.get('rating')
        
        # Validate rating
        if not rating_value or not (1 <= int(rating_value) <= 5):
            return Response({
                'success': False,
                'error': 'Rating must be between 1 and 5'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get credit costs
        credit_costs = CreditCostsModel.objects.first()
        if not credit_costs or not credit_costs.star_rating_cost:
            return Response({
                'success': False,
                'error': 'Rating cost not configured'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Get user's credit vault
        vault, _ = UserCreditVault.objects.get_or_create(user=request.user)
        
        # Check if user already rated this post
        existing_rating = PostRating.objects.filter(post=post, user=request.user).first()
        
        if existing_rating:
            # Update existing rating (FREE update)
            old_rating = existing_rating.rating
            existing_rating.rating = rating_value
            existing_rating.save()
            
            # Recalculate average
            post.average_rating = PostRating.objects.filter(post=post).aggregate(
                avg=models.Avg('rating')
            )['avg'] or 0
            post.save()
            
            # 🔔 SEND NOTIFICATION FOR UPDATED RATING
            if post.user.fcm_token and post.user.notifications_enabled:
                if post.user != request.user:  # Don't notify if rating own post
                    send_push_notification(
                        fcm_token=post.user.fcm_token,
                        title=f"Rating Updated to {rating_value}⭐",
                        body=f"{request.user.username} changed their rating from {old_rating}⭐ to {rating_value}⭐",
                        data={
                            'type': 'rating_update',
                            'post_id': str(post.post_id),
                            'old_rating': str(old_rating),
                            'new_rating': str(rating_value),
                            'user_id': str(request.user.id),
                            'username': request.user.username or 'A user'
                        }
                    )
            
            return Response({
                'success': True,
                'message': f'Rating updated from {old_rating}⭐ to {rating_value}⭐',
                'rating': rating_value,
                'average_rating': float(post.average_rating),
                'credits_used': 0
            }, status=status.HTTP_200_OK)
        
        # Check if user has enough credits for NEW rating
        required_credits = int(credit_costs.star_rating_cost)
        if vault.total_credits < required_credits:
            return Response({
                'success': False,
                'error': f'Insufficient credits. Need {required_credits}, have {vault.total_credits}',
                'required_credits': required_credits,
                'available_credits': vault.total_credits
            }, status=status.HTTP_402_PAYMENT_REQUIRED)
        
        # Deduct credits
        vault.total_credits -= required_credits
        vault.spent_credits += required_credits
        vault.save()
        
        # Create transaction log
        CreditTransactionLog.objects.create(
            user=request.user,
            transaction_type='Rating',
            credits_changed=-required_credits,
            value_changed=-credit_costs.star_rating_cost,
            description=f'Rated post {post.post_id} with {rating_value} stars'
        )
        
        # Create rating
        PostRating.objects.create(post=post, user=request.user, rating=rating_value)
        
        # Update post stats
        post.rating_count += 1
        post.average_rating = PostRating.objects.filter(post=post).aggregate(
            avg=models.Avg('rating')
        )['avg'] or 0
        post.save()
        
        # 🔔 SEND NOTIFICATION FOR NEW RATING
        if post.user.fcm_token and post.user.notifications_enabled:
            if post.user != request.user:  # Don't notify if rating own post
                send_push_notification(
                    fcm_token=post.user.fcm_token,
                    title=f"New {rating_value}⭐ Rating!",
                    body=f"{request.user.username} rated your post {rating_value} stars",
                    data={
                        'type': 'rating',
                        'post_id': str(post.post_id),
                        'rating': str(rating_value),
                        'user_id': str(request.user.id),
                        'username': request.user.username or 'A user'
                    }
                )
        
        return Response({
            'success': True,
            'message': f'Post rated {rating_value}⭐ successfully',
            'rating': rating_value,
            'average_rating': float(post.average_rating),
            'credits_used': required_credits,
            'remaining_credits': vault.total_credits
        }, status=status.HTTP_201_CREATED)

# Update PostLikeView to use credits
class PostLikeView(APIView):
    """POST: Like or unlike a post - COSTS CREDITS"""
    permission_classes = [IsAuthenticated]
    
    @transaction.atomic
    def post(self, request, pk):
        post = get_object_or_404(Post, pk=pk, is_deleted=False, is_active=True)
        
        # Check if already liked
        existing_like = PostLike.objects.filter(post=post, user=request.user).first()
        
        if existing_like:
            # Unlike (FREE - no credit refund)
            existing_like.delete()
            post.likes_count = max(0, post.likes_count - 1)
            post.save()
            return Response({
                'success': True,
                'message': 'Post unliked',
                'liked': False,
                'likes_count': post.likes_count
            }, status=status.HTTP_200_OK)
        
        # Get credit costs
        credit_costs = CreditCostsModel.objects.first()
        if not credit_costs or not credit_costs.post_liking_cost:
            return Response({
                'success': False,
                'error': 'Like cost not configured'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # Get user's credit vault
        vault, _ = UserCreditVault.objects.get_or_create(user=request.user)
        
        # Check credits
        required_credits = int(credit_costs.post_liking_cost)
        if vault.total_credits < required_credits:
            return Response({
                'success': False,
                'error': f'Insufficient credits. Need {required_credits}, have {vault.total_credits}',
                'required_credits': required_credits,
                'available_credits': vault.total_credits
            }, status=status.HTTP_402_PAYMENT_REQUIRED)
        
        # Deduct credits
        vault.total_credits -= required_credits
        vault.spent_credits += required_credits
        vault.save()
        
        # Log transaction
        CreditTransactionLog.objects.create(
            user=request.user,
            transaction_type='Like',
            credits_changed=-required_credits,
            value_changed=-credit_costs.post_liking_cost,
            description=f'Liked post {post.post_id}'
        )
        
        # Create like
        PostLike.objects.create(post=post, user=request.user)
        post.likes_count += 1
        post.save()
        
        return Response({
            'success': True,
            'message': 'Post liked',
            'liked': True,
            'likes_count': post.likes_count,
            'credits_used': required_credits,
            'remaining_credits': vault.total_credits
        }, status=status.HTTP_201_CREATED)
    

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def saved_posts(request):
    """Get all saved posts by the current user"""
    saved = PostSave.objects.filter(user=request.user).select_related('post')
    posts = [s.post for s in saved if not s.post.is_deleted and s.post.is_active]
    
    serializer = PostSerializer(posts, many=True, context={'request': request})
    return Response({
        'success': True,
        'count': len(posts),
        'posts': serializer.data
    }, status=status.HTTP_200_OK)


# your_app/views.py


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_device_token(request):
    """
    Save user's FCM token and device info
    Flutter app calls this after login
    
    Expected data:
    {
        "fcm_token": "long-token-string",
        "device_type": "android" or "ios",
        "enable_notifications": true
    }
    """
    fcm_token = request.data.get('fcm_token')
    device_type = request.data.get('device_type')
    enable_notifications = request.data.get('enable_notifications', True)
    
    if not fcm_token:
        return Response({
            'success': False,
            'error': 'fcm_token is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Save to user model
    user = request.user
    user.fcm_token = fcm_token
    user.device_type = device_type
    user.notifications_enabled = enable_notifications
    user.save()
    
    return Response({
        'success': True,
        'message': 'Device token saved successfully'
    }, status=status.HTTP_200_OK)