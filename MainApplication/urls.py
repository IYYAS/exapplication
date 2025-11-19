from django.urls import path,include

urlpatterns = [
    
    path('auth/web/', include('MainApplication.Authentication.Web.urls')),
    path('auth/app/', include('MainApplication.Authentication.App.urls')),
    
    path('user/', include('MainApplication.User.urls')),
    path('posts/', include('MainApplication.Post.post_urls')),

]