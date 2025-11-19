# posts/post_urls.py
from django.urls import path
from . import post_views

app_name = 'posts'

urlpatterns = [
    # Post CRUD

    path('create/image/', post_views.PostImageCreateView.as_view(), name='post-create-image'),
    path('create/video/', post_views.PostVideoCreateView.as_view(), name='post-create-video'),
    path('<int:pk>/like/', post_views.PostLikeView.as_view(), name='post-like'),
    path('<int:pk>/save/', post_views.PostSaveView.as_view(), name='post-save'),
    path('<int:pk>/share/', post_views.PostShareView.as_view(), name='post-share'),
    path('<int:pk>/rate/', post_views.PostRatingView.as_view(), name='post-rate'),


    path('', post_views.PostListCreateView.as_view(), name='post-list-create'),
    path('<int:pk>/', post_views.PostDetailView.as_view(), name='post-detail'),
    
   
    
    
    path('<int:pk>/comments/', post_views.PostCommentListCreateView.as_view(), name='post-comments'),
    path('<int:pk>/comments/<uuid:comment_id>/', post_views.PostCommentDetailView.as_view(), name='post-comment-detail'),
   
    path('saved/', post_views.saved_posts, name='saved-posts'),

    path('my-posts/', post_views.my_posts, name='my-posts'),
    path('feed/', post_views.feed, name='feed'),
    path('user/<int:user_id>/', post_views.user_posts, name='user-posts'),
]