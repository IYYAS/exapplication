from  django.urls import path, include
from .views import *
from rest_framework.routers import DefaultRouter

router = DefaultRouter()



urlpatterns = [
    path('edit/username/', EditUsernameView.as_view(), name="edit-username"),
    path('profile/', UserProfileAPIView.as_view(), name="user-profile"),
    path('follow/', UserFollowingAPIView.as_view(), name="user-follow-unfollow"),
    path('helloworld/', HelloworldView.as_view(), name="hello-world"),
    path('test-redis/', test_redis_view, name='test_redis'),

    path('', include(router.urls)),
]