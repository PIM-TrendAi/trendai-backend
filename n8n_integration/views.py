"""
Views for true N8N Integration.
Django acts as a Read/Proxy API over the PostgreSQL tables that N8N manages natively.
"""
import os
import requests
import uuid
from django.conf import settings
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from .models import TrendingVideo, CreatorSession, GeneratedScript, GeneratedVideo, PostedVideo, ConnectedPlatform
from .serializers import TrendingVideoSerializer, CombinedSessionStatusSerializer

def trigger_n8n_webhook(webhook_id: str, payload: dict):
    base_url = os.getenv("N8N_WEBHOOK_BASE_URL", "").rstrip("/")
    if not base_url:
        print("Missing N8N_WEBHOOK_BASE_URL")
        return False
    url = f"{base_url}/webhook/{webhook_id}"
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code in (200, 201)
    except Exception as e:
        print(f"Failed to call webhook {webhook_id}: {e}")
        return False

class TrendingVideoListView(generics.ListAPIView):
    """GET /api/n8n/trending_videos/ - Returns the most recently scraped trending videos"""
    serializer_class = TrendingVideoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Get base queryset ordered by rank
        queryset = TrendingVideo.objects.order_by('rank')
        
        # Apply niche filtering if provided
        niche = self.request.query_params.get('niche')
        if niche:
            # Clean up the niche string for search (e.g., 'Tech & Gadgets' -> ['tech', 'gadgets'])
            search_terms = [t.strip().lower() for t in niche.replace('&', ' ').split() if len(t.strip()) > 2]
            
            if search_terms:
                from django.db.models import Q
                query = Q()
                for term in search_terms:
                    # Search in both category field and hashtags field
                    query |= Q(category__icontains=term) | Q(hashtags__icontains=term)
                filtered = queryset.filter(query)
                # If niche filter finds nothing, fall back to all trending videos
                if filtered.exists():
                    queryset = filtered
                
        # Return top 10 matches
        return queryset[:10]

class SessionStatusView(APIView):
    """GET /api/n8n/sessions/{session_id}/ - Aggregates the session status across multiple tables"""
    permission_classes = [IsAuthenticated]

    def get(self, request, session_id):
        # 1. Fetch the base session
        try:
            session = CreatorSession.objects.get(session_id=session_id)
        except CreatorSession.DoesNotExist:
            return Response({"error": "Session not found"}, status=status.HTTP_404_NOT_FOUND)

        # Build aggregated payload
        payload = {
            "session_id": session.session_id,
            "creator_id": session.creator_id,
            "niche": session.niche,
            "status": session.status,
            "selected_video_id": session.selected_video_id,
            "script_id": None, "script_content": None, "script_status": None,
            "video_id": None, "video_url": None, "video_thumbnail": None, "video_status": None,
            "tiktok_post_url": None,
        }

        # 2. Check for Scripts
        script = GeneratedScript.objects.filter(session_id=session_id).order_by('-created_at').first()
        if script:
            payload["script_id"] = script.script_id
            payload["script_content"] = script.script_content
            payload["script_status"] = script.status
            # Bubble up script pending approval status to the top level
            if script.status == 'pending_approval':
                payload["status"] = "script_pending"
                
        # 3. Check for Videos
        video = GeneratedVideo.objects.filter(session_id=session_id).order_by('-created_at').first()
        if video:
            payload["video_id"] = video.video_id
            payload["video_url"] = video.video_url
            payload["video_status"] = video.status
            if video.status == 'pending_approval':
                payload["status"] = "video_pending"
                
        # 4. Check if Posted
        posted = PostedVideo.objects.filter(session_id=session_id).last()
        if posted:
            payload["tiktok_post_url"] = posted.video_url
            payload["status"] = "posted"

        serializer = CombinedSessionStatusSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data)


class StartWorkflowView(APIView):
    """POST /api/n8n/start/ - Proxies the user's start choice to n8n"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        niche = request.data.get("niche")
        selected_video_id = request.data.get("selected_video_id")
        
        if not niche or not selected_video_id:
            return Response({"error": "niche and selected_video_id are required"}, status=status.HTTP_400_BAD_REQUEST)

        # Trigger n8n start Node "Webhook: Creator Chooses Video + Niche"
        # N8N handles creating the CreatorSession immediately
        payload = {
            "niche": niche,
            "selectedVideoId": selected_video_id,
            "creatorId": str(request.user.id)
        }
        
        # 205b7271-5246-4e81-80b4-7b93579ab006 = "🎯 Webhook: Creator Chooses Video + Niche"
        success = trigger_n8n_webhook("205b7271-5246-4e81-80b4-7b93579ab006", payload)
        
        if not success:
            return Response({"error": "Failed to trigger n8n workflow"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # To give flutter something to poll immediately, we can predict the session_id format N8N uses,
        # or we just let Flutter poll the API until N8N registers it. In N8N the session_id is built via:
        # '{{ $json.creatorId }}_{{ $now.toMillis() }}'. Since we don't know the millis exactly, 
        # N8N should probably return it or we fetch the latest session for the user.
        return Response({"success": True, "message": "Workflow started. Session is initializing in n8n."})

class TriggerScrapingView(APIView):
    """POST /api/n8n/trigger-scrape/ - Trigger the scraper workflow (TikTok or Instagram)"""
    permission_classes = [IsAuthenticated]

    # Webhook IDs by platform
    SCRAPE_WEBHOOK_IDS = {
        "tiktok": "8a4b64f3-ac29-4591-a1b7-4c2089f92bb4",
        "instagram": "f1e2d3c4-b5a6-7890-1234-567890abcdef",  # Instagram scrape webhook
    }

    def post(self, request):
        niche = request.data.get("niche", "")
        platform = request.data.get("platform", "tiktok").lower()
        payload = {"niche": niche, "platform": platform} if niche else {"platform": platform}

        webhook_id = self.SCRAPE_WEBHOOK_IDS.get(platform, self.SCRAPE_WEBHOOK_IDS["tiktok"])
        success = trigger_n8n_webhook(webhook_id, payload)

        if not success:
            return Response({"error": "Failed to trigger n8n scraping workflow"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"success": True, "message": f"{platform.title()} scraping workflow triggered successfully."})

class GetLatestSessionView(APIView):
    """GET /api/n8n/sessions/latest/ - Get the user's latest session"""
    permission_classes = [IsAuthenticated]
    def get(self, request):
        session = CreatorSession.objects.filter(creator_id=str(request.user.id)).order_by('-created_at').first()
        if not session:
            return Response({"session_id": None})
        return Response({"session_id": session.session_id})


class ApproveScriptView(APIView):
    """POST /api/n8n/approve/script/"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        session_id = request.data.get("session_id")
        script_id = request.data.get("script_id")
        approved = request.data.get("approved", False)
        
        # Trigger n8n "🎯 Webhook: Script Approve/Decline"
        # Node path: 0ec65146-238d-4c79-a441-25721e9373e7
        success = trigger_n8n_webhook("0ec65146-238d-4c79-a441-25721e9373e7", {
            "sessionId": session_id,
            "scriptId": script_id,
            "decision": "approve" if approved else "decline",
            "feedback": request.data.get("feedback", "")
        })
        
        if not success:
            return Response({"error": "Failed proxying to n8n"}, status=400)
            
        return Response({"success": True})

class ApproveVideoView(APIView):
    """POST /api/n8n/approve/video/"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        session_id = request.data.get("session_id")
        video_id = request.data.get("video_id")
        approved = request.data.get("approved", False)
        
        # Get the user's TikTok access token
        token = ""
        platform = ConnectedPlatform.objects.filter(creator_id=str(request.user.id), platform_name="tiktok").first()
        if platform:
            token = platform.access_token
        
        # Trigger n8n "🎯 Webhook: Video Approve/Decline"
        # Node path: 35bda5a4-5875-4ce6-b33f-3bea2ca0cc8a
        success = trigger_n8n_webhook("35bda5a4-5875-4ce6-b33f-3bea2ca0cc8a", {
            "sessionId": session_id,
            "videoId": video_id,
            "decision": "approve" if approved else "decline",
            "feedback": request.data.get("feedback", ""),
            "tiktok_access_token": token
        })
        
        if not success:
            return Response({"error": "Failed proxying to n8n"}, status=400)

        return Response({"success": True})


class GeneratedVideosListView(APIView):
    """GET /api/n8n/my-videos/ - Returns all generated videos for the logged-in user"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        videos = GeneratedVideo.objects.filter(
            creator_id=str(request.user.id)
        ).order_by('-created_at')

        data = []
        for v in videos:
            script = GeneratedScript.objects.filter(
                session_id=v.session_id, status='approved'
            ).order_by('-created_at').first()

            session = CreatorSession.objects.filter(session_id=v.session_id).first()

            data.append({
                'video_id': v.video_id,
                'session_id': v.session_id,
                'video_url': v.video_url,
                'status': v.status,
                'niche': session.niche if session else '',
                'script_preview': (script.script_content[:120] + '...') if script else '',
                'created_at': v.created_at.isoformat() if v.created_at else None,
            })

        return Response(data)

from django.http import HttpResponse

TIKTOK_CLIENT_KEY = "sbaw1tz2r0ocin57kl"
TIKTOK_CLIENT_SECRET = "j0YE0fR0hOEWVqtt0FmrpsMVQb6r7Ua4"
TIKTOK_REDIRECT_URI = "https://noncartelized-delightsomely-donetta.ngrok-free.dev/api/n8n/platforms/tiktok/callback/"

class ConnectedPlatformsView(APIView):
    """GET /api/n8n/platforms/ - Returns a list of the user's connected platforms"""
    permission_classes = [IsAuthenticated]
    def get(self, request):
        tiktok = ConnectedPlatform.objects.filter(creator_id=str(request.user.id), platform_name="tiktok").exists()
        return Response([
            {"name": "TikTok", "connected": tiktok},
            {"name": "Instagram", "connected": False},
            {"name": "YouTube", "connected": False},
            {"name": "Facebook", "connected": False},
        ])

import urllib.parse

class PlatformAuthURLView(APIView):
    """GET /api/n8n/platforms/tiktok/url/ - Generates the TikTok OAuth URL"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, platform):
        if platform == "tiktok":
            # State is the user id so we know who they are when they come back
            state = str(request.user.id)
            encoded_redirect = urllib.parse.quote(TIKTOK_REDIRECT_URI, safe='')
            url = f"https://www.tiktok.com/v2/auth/authorize/?client_key={TIKTOK_CLIENT_KEY}&response_type=code&scope=user.info.basic,video.publish,video.upload&redirect_uri={encoded_redirect}&state={state}"
            return Response({"url": url})
        return Response({"error": "Platform not supported"}, status=400)


class PlatformCallbackView(APIView):
    """GET /api/n8n/platforms/tiktok/callback/ - Handles the redirect from TikTok"""
    # No auth class, because this is hit by the browser redirect from TikTok
    permission_classes = []
    
    def get(self, request, platform):
        if platform == "tiktok":
            code = request.GET.get("code")
            state = request.GET.get("state")  # This is the user_id
            error = request.GET.get("errCode")
            error_desc = request.GET.get("error")
            
            if error or not code:
                return HttpResponse(f"Error connecting TikTok: {error_desc or 'No code returned'}")
                
            # Exchange code for token
            token_url = "https://open.tiktokapis.com/v2/oauth/token/"
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            data = {
                "client_key": TIKTOK_CLIENT_KEY,
                "client_secret": TIKTOK_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": TIKTOK_REDIRECT_URI,
            }
            
            resp = requests.post(token_url, headers=headers, data=data)
            if resp.status_code == 200:
                resp_json = resp.json()
                access_token = resp_json.get("access_token")
                refresh_token = resp_json.get("refresh_token")
                open_id = resp_json.get("open_id")
                expires_in = resp_json.get("expires_in", 0)
                
                ConnectedPlatform.objects.update_or_create(
                    creator_id=state,
                    platform_name="tiktok",
                    defaults={
                        "access_token": access_token,
                        "refresh_token": refresh_token,
                        "open_id": open_id,
                        "expires_in": expires_in
                    }
                )
                
                # Successful response that auto-closes the window
                return HttpResponse("<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head><body style='font-family:sans-serif; text-align:center; padding-top: 50px;'><h1>TikTok Connected Successfully! 🚀</h1><p>You can close this window now and return to the app.</p><script>setTimeout(function(){window.close();}, 1500);</script></body></html>")
            else:
                return HttpResponse(f"Error exchanging token: {resp.text}")
                
        return HttpResponse("Platform not supported")
