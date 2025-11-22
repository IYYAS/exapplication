# your_app/notifications.py
import firebase_admin
from firebase_admin import credentials, messaging
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

# Initialize Firebase Admin SDK (only once)
if not firebase_admin._apps:
    cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
    firebase_admin.initialize_app(cred)

def send_push_notification(fcm_token, title, body, data=None):
    """
    Send push notification to a single device
    
    Args:
        fcm_token (str): User's FCM device token
        title (str): Notification title
        body (str): Notification message
        data (dict): Additional data payload
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=data or {},
            token=fcm_token,
        )
        
        response = messaging.send(message)
        logger.info(f"✅ Push notification sent successfully: {response}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to send push notification: {str(e)}")
        return False

def send_bulk_notifications(tokens, title, body, data=None):
    """Send notification to multiple devices"""
    try:
        message = messaging.MulticastMessage(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=data or {},
            tokens=tokens,
        )
        
        response = messaging.send_multicast(message)
        logger.info(f"✅ Sent {response.success_count} notifications successfully")
        return response
        
    except Exception as e:
        logger.error(f"❌ Failed to send bulk notifications: {str(e)}")
        return None