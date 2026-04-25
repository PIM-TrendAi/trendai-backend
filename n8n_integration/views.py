"""
Views for true N8N Integration.
Django acts as a Read/Proxy API over the PostgreSQL tables that N8N manages natively.
"""
import os
import requests
import uuid
import time
from django.conf import settings
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from .models import TrendingVideo, CreatorSession, GeneratedScript, GeneratedVideo, PostedVideo, ConnectedPlatform
from .serializers import TrendingVideoSerializer, CombinedSessionStatusSerializer

def trigger_n8n_webhook(webhook_id: str, payload: dict, fallback_ids=None, timeout=30):
    base_url = os.getenv("N8N_WEBHOOK_BASE_URL", "").rstrip("/")
    if not base_url:
        print("Missing N8N_WEBHOOK_BASE_URL")
        return False

    fallback_ids = fallback_ids or []
    webhook_ids = [webhook_id, *fallback_ids]
    attempted = set()

    # Try both production and test webhooks.
    # Use (connect_timeout, read_timeout) — ngrok can be slow.
    connect_timeout = 5
    read_timeout = min(timeout, 30)

    for hook_id in webhook_ids:
        clean_hook_id = str(hook_id or "").strip().strip("/")
        if not clean_hook_id or clean_hook_id in attempted:
            continue
        attempted.add(clean_hook_id)

        # Try both production and test endpoints
        endpoints_to_try = [
            f"{base_url}/webhook/{clean_hook_id}",
            f"{base_url}/webhook-test/{clean_hook_id}",
        ]

        for url in endpoints_to_try:
            try:
                response = requests.post(url, json=payload, timeout=(connect_timeout, read_timeout))
                if response.status_code in (200, 201):
                    return True
                # 404 means wrong mode — try next quickly
                if response.status_code == 404:
                    print(f"Webhook {url} returned 404, trying next...")
                    continue
                print(f"Webhook {url} returned {response.status_code}: {response.text[:200]}")
            except requests.exceptions.ReadTimeout:
                # Server received request but response is slow (ngrok + n8n processing)
                # n8n IS working — treat as success since callback handles the result
                print(f"Webhook {url} read timeout — n8n is likely processing. Treating as success.")
                return True
            except requests.exceptions.ConnectTimeout:
                print(f"Webhook {url} connect timeout, trying next...")
            except requests.exceptions.ConnectionError:
                print(f"Webhook {url} connection error, trying next...")
            except Exception as e:
                print(f"Failed to call webhook {url}: {e}")
            
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

        # For YouTube/Facebook: check their dedicated generated tables
        if session.platform in ("youtube", "facebook"):
            from django.db import connection
            table = "youtube_generated" if session.platform == "youtube" else "facebook_generated"
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"SELECT id, script, title, description, tags, video_url, status "
                        f"FROM {table} WHERE user_id = %s AND LOWER(niche) = LOWER(%s) ORDER BY id DESC LIMIT 1",
                        [int(session.creator_id), session.niche]
                    )
                    row = cursor.fetchone()
                    if row:
                        gen_id, script, title, description, tags, video_url, gen_status = row
                        payload["script_id"] = str(gen_id)
                        payload["script_content"] = script
                        payload["script_status"] = gen_status
                        if video_url:
                            payload["video_id"] = str(gen_id)
                            payload["video_url"] = video_url
                            payload["video_status"] = gen_status
                        if gen_status == "pending_review":
                            payload["status"] = "script_pending"
                        elif gen_status == "approved":
                            payload["status"] = "processing"
                        elif gen_status == "posted":
                            payload["status"] = "posted"
                        elif gen_status == "rejected":
                            payload["status"] = "declined"
                        else:
                            payload["status"] = "script_generation"
            except Exception as e:
                print(f"Error checking {table}: {e}")

            serializer = CombinedSessionStatusSerializer(data=payload)
            serializer.is_valid(raise_exception=True)
            return Response(serializer.validated_data)

        # 2. Check for Scripts (TikTok/Instagram)
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
    """POST /api/n8n/start/ - Proxies the user's start choice to n8n (TikTok or Instagram)"""
    permission_classes = [IsAuthenticated]

    TIKTOK_START_WEBHOOK_ID = os.getenv("N8N_START_WEBHOOK_ID", "205b7271-5246-4e81-80b4-7b93579ab006")
    TIKTOK_START_WEBHOOK_PATH = os.getenv("N8N_START_WEBHOOK_PATH", "tiktok-creator-select")
    INSTAGRAM_START_WEBHOOK_PATH = "instagram-start"
    FACEBOOK_START_WEBHOOK_PATH = os.getenv("N8N_FACEBOOK_START_WEBHOOK_PATH", "generate")  # Facebook workflow path
    YOUTUBE_START_WEBHOOK_PATH = os.getenv("N8N_YOUTUBE_START_WEBHOOK_PATH", "generate-video-v2")

    def post(self, request):
        try:
            niche = request.data.get("niche")
            selected_video_id = request.data.get("selected_video_id") or request.data.get("selectedVideoId")
            platform = request.data.get("platform", "tiktok").lower()

            if not niche or not selected_video_id:
                return Response({"error": "niche and selected_video_id are required"}, status=status.HTTP_400_BAD_REQUEST)

            payload = {
                "niche": niche,
                "selectedVideoId": selected_video_id,
                "creatorId": str(request.user.id),
                "userPrompt": request.data.get("custom_prompt", ""),
                "style": request.data.get("style", "Informative"),
                "duration": request.data.get("duration", "60s"),
                "video_id": selected_video_id,
                "reel_id": selected_video_id,
                "creator_id": str(request.user.id),
                "user_id": str(request.user.id),
                "user_email": request.user.email,
                "title": request.data.get("title", ""),
                "custom_prompt": request.data.get("custom_prompt", ""),
                "prompt": request.data.get("custom_prompt", ""),
            }

            if platform == "instagram":
                success = trigger_n8n_webhook(
                    self.INSTAGRAM_START_WEBHOOK_PATH,
                    payload,
                )
            elif platform == "facebook":
                session_id = f"{request.user.id}_{int(time.time() * 1000)}"
                CreatorSession.objects.create(
                    session_id=session_id,
                    creator_id=str(request.user.id),
                    selected_video_id=selected_video_id,
                    niche=niche,
                    platform="facebook",
                    status="script_generation",
                )
                payload["session_id"] = session_id
                success = trigger_n8n_webhook(
                    self.FACEBOOK_START_WEBHOOK_PATH,
                    payload,
                )
            elif platform == "youtube":
                # Create a session so the app can poll for status
                session_id = f"{request.user.id}_{int(time.time() * 1000)}"
                CreatorSession.objects.create(
                    session_id=session_id,
                    creator_id=str(request.user.id),
                    selected_video_id=selected_video_id,
                    niche=niche,
                    platform="youtube",
                    status="script_generation",
                )
                payload["session_id"] = session_id
                success = trigger_n8n_webhook(
                    self.YOUTUBE_START_WEBHOOK_PATH,
                    payload,
                )
            else:
                success = trigger_n8n_webhook(
                    self.TIKTOK_START_WEBHOOK_ID,
                    payload,
                    fallback_ids=[self.TIKTOK_START_WEBHOOK_PATH],
                )

            if not success:
                return Response({"error": "Failed to trigger n8n workflow. Please ensure it is active or listening in n8n."}, status=status.HTTP_502_BAD_GATEWAY)

            return Response({"success": True, "message": f"{platform.title()} workflow started. Session is initializing in n8n."})
        except Exception as exc:
            print(f"StartWorkflowView failed unexpectedly: {exc}")
            return Response({"error": "Failed to start video generation workflow."}, status=status.HTTP_502_BAD_GATEWAY)

class TriggerScrapingView(APIView):
    """POST /api/n8n/trigger-scrape/ - Trigger the scraper workflow (TikTok or Instagram)"""
    permission_classes = [IsAuthenticated]

    # Webhook IDs by platform
    SCRAPE_WEBHOOK_IDS = {
        "tiktok": "8a4b64f3-ac29-4591-a1b7-4c2089f92bb4",
        "instagram": "instagram-scrape",
        "facebook": os.getenv("N8N_FACEBOOK_SCRAPE_WEBHOOK_PATH", "scrape"),  # Facebook workflow scrape path
        "youtube": os.getenv("N8N_YOUTUBE_SCRAPE_WEBHOOK_PATH", "youtube-scrape"),
    }

    def post(self, request):
        niche = request.data.get("niche", "")
        platform = request.data.get("platform", "tiktok").lower()
        payload = {"niche": niche, "platform": platform} if niche else {"platform": platform}

        webhook_id = self.SCRAPE_WEBHOOK_IDS.get(platform, self.SCRAPE_WEBHOOK_IDS["tiktok"])
        success = trigger_n8n_webhook(webhook_id, payload, timeout=180)

        if not success:
            return Response({"error": "Failed to trigger n8n scraping workflow"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"success": True, "message": f"{platform.title()} scraping workflow triggered successfully."})

class GetLatestSessionView(APIView):
    """GET /api/n8n/sessions/latest/ - Get the user's latest session"""
    permission_classes = [IsAuthenticated]
    def get(self, request):
        qs = CreatorSession.objects.filter(creator_id=str(request.user.id))
        platform = request.query_params.get('platform')
        if platform:
            qs = qs.filter(platform=platform.lower())
        session = qs.order_by('-created_at').first()
        if not session:
            return Response({"session_id": None})
        return Response({"session_id": session.session_id})


class ApproveScriptView(APIView):
    """POST /api/n8n/approve/script/"""
    permission_classes = [IsAuthenticated]

    SCRIPT_APPROVE_WEBHOOK_ID = os.getenv("N8N_SCRIPT_APPROVE_WEBHOOK_ID", "0ec65146-238d-4c79-a441-25721e9373e7")
    SCRIPT_APPROVE_WEBHOOK_PATH = os.getenv("N8N_SCRIPT_APPROVE_WEBHOOK_PATH", "tiktok-script-approve")

    def post(self, request):
        session_id = request.data.get("session_id")
        script_id = request.data.get("script_id")
        approved = request.data.get("approved", False)
        decision = "approve" if approved else "decline"

        session = CreatorSession.objects.filter(session_id=session_id).first()
        
        # Trigger n8n "🎯 Webhook: Script Approve/Decline"
        # Node path: 0ec65146-238d-4c79-a441-25721e9373e7
        success = trigger_n8n_webhook(self.SCRIPT_APPROVE_WEBHOOK_ID, {
            "sessionId": session_id,
            "scriptId": script_id,
            # Send both keys to support old/new n8n IF conditions.
            "decision": decision,
            "action": decision,
            "feedback": request.data.get("feedback", ""),
            "creatorId": str(request.user.id),
            "niche": session.niche if session else request.data.get("niche", ""),
            "selectedVideoId": session.selected_video_id if session else request.data.get("selected_video_id", ""),
        }, fallback_ids=[self.SCRIPT_APPROVE_WEBHOOK_PATH])
        
        if not success:
            return Response({"error": "Failed proxying to n8n"}, status=400)
            
        return Response({"success": True})

class ApproveVideoView(APIView):
    """POST /api/n8n/approve/video/ - Supports both TikTok and Instagram"""
    permission_classes = [IsAuthenticated]

    VIDEO_APPROVE_WEBHOOK_ID = os.getenv("N8N_VIDEO_APPROVE_WEBHOOK_ID", "35bda5a4-5875-4ce6-b33f-3bea2ca0cc8a")
    VIDEO_APPROVE_WEBHOOK_PATH = os.getenv("N8N_VIDEO_APPROVE_WEBHOOK_PATH", "tiktok-video-approve")
    INSTAGRAM_VIDEO_APPROVE_PATH = "instagram-video-approve"

    def post(self, request):
        session_id = request.data.get("session_id")
        video_id = request.data.get("video_id")
        approved = request.data.get("approved", False)
        decision = "approve" if approved else "decline"
        platform = request.data.get("platform", "tiktok").lower()
        
        payload = {
            "sessionId": session_id,
            "videoId": video_id,
            "decision": decision,
            "action": decision,
            "feedback": request.data.get("feedback", ""),
        }

        if platform == "instagram":
            success = trigger_n8n_webhook(self.INSTAGRAM_VIDEO_APPROVE_PATH, payload)
        elif platform == "facebook":
            # Facebook workflow: trigger dedicated approve webhook
            fb_approve_path = os.getenv("N8N_FACEBOOK_VIDEO_APPROVE_PATH", "facebook-video-approve")
            success = trigger_n8n_webhook(fb_approve_path, payload)
        elif platform == "youtube":
            # YouTube workflow: trigger dedicated approve webhook
            yt_approve_path = os.getenv("N8N_YOUTUBE_VIDEO_APPROVE_PATH", "youtube-video-approve")
            success = trigger_n8n_webhook(yt_approve_path, payload)
        else:
            # TikTok path: include access token
            token = ""
            cp = ConnectedPlatform.objects.filter(creator_id=str(request.user.id), platform_name="tiktok").first()
            if cp:
                token = cp.access_token
            payload["tiktok_access_token"] = token
            success = trigger_n8n_webhook(
                self.VIDEO_APPROVE_WEBHOOK_ID,
                payload,
                fallback_ids=[self.VIDEO_APPROVE_WEBHOOK_PATH],
            )

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
from django.db import connection
from django.utils import timezone

TIKTOK_CLIENT_KEY = "sbaw1tz2r0ocin57kl"
TIKTOK_CLIENT_SECRET = "j0YE0fR0hOEWVqtt0FmrpsMVQb6r7Ua4"
TIKTOK_REDIRECT_URI = os.getenv(
    "TIKTOK_REDIRECT_URI",
    "https://noncartelized-delightsomely-donetta.ngrok-free.dev/webhook/c0a80001-0000-0000-0000-000000000002",
)

class ConnectedPlatformsView(APIView):
    """GET /api/n8n/platforms/ - Returns a list of the user's connected platforms"""
    permission_classes = [IsAuthenticated]
    def get(self, request):
        from platforms.models import UserPlatform
        tiktok_connected_platform = ConnectedPlatform.objects.filter(
            creator_id=str(request.user.id),
            platform_name="tiktok",
        ).exists()
        tiktok_user_platform = UserPlatform.objects.filter(
            user=request.user,
            platform_name="TikTok",
            connected=True,
        ).exists()
        tiktok = tiktok_connected_platform or tiktok_user_platform
        facebook = UserPlatform.objects.filter(user=request.user, platform_name="Facebook", connected=True).exists()
        instagram = UserPlatform.objects.filter(user=request.user, platform_name="Instagram", connected=True).exists()
        return Response([
            {"name": "TikTok", "connected": tiktok},
            {"name": "Instagram", "connected": instagram},
            {"name": "YouTube", "connected": False},
            {"name": "Facebook", "connected": facebook},
        ])


class PlatformStatusView(APIView):
    """GET /api/n8n/platforms/<platform>/status/ - Returns whether a platform is connected"""
    permission_classes = [IsAuthenticated]

    def get(self, request, platform):
        platform = (platform or "").lower()
        from platforms.models import UserPlatform

        if platform == "tiktok":
            connected_platform = ConnectedPlatform.objects.filter(
                creator_id=str(request.user.id),
                platform_name="tiktok",
            ).exists()
            connected_user_platform = UserPlatform.objects.filter(
                user=request.user,
                platform_name="TikTok",
                connected=True,
            ).exists()
            token_row_exists = False
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT 1 FROM tiktok_tokens WHERE creator_id = %s LIMIT 1",
                        [str(request.user.id)],
                    )
                    token_row_exists = cursor.fetchone() is not None
            except Exception:
                token_row_exists = False

            return Response({
                "connected": connected_platform or connected_user_platform or token_row_exists
            })

        if platform == "instagram":
            connected = UserPlatform.objects.filter(
                user=request.user,
                platform_name="Instagram",
                connected=True,
            ).exists()
            return Response({"connected": connected})

        if platform == "facebook":
            connected = UserPlatform.objects.filter(
                user=request.user,
                platform_name="Facebook",
                connected=True,
            ).exists()
            return Response({"connected": connected})

        return Response({"error": "Platform not supported"}, status=status.HTTP_400_BAD_REQUEST)


class PlatformConnectView(APIView):
    """POST /api/n8n/platforms/<platform>/connect/ - Marks a platform as connected"""
    permission_classes = [IsAuthenticated]

    def post(self, request, platform):
        platform = (platform or "").lower()
        from platforms.models import UserPlatform

        if platform == "instagram":
            UserPlatform.objects.update_or_create(
                user=request.user,
                platform_name="Instagram",
                defaults={
                    "connected": True,
                    "connected_at": timezone.now(),
                },
            )
            return Response({"success": True, "connected": True})

        if platform == "facebook":
            UserPlatform.objects.update_or_create(
                user=request.user,
                platform_name="Facebook",
                defaults={
                    "connected": True,
                    "connected_at": timezone.now(),
                },
            )
            return Response({"success": True, "connected": True})

        if platform == "tiktok":
            return Response(
                {
                    "error": "TikTok requires OAuth. Use /api/n8n/platforms/tiktok/url/ first."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"error": "Platform not supported"}, status=status.HTTP_400_BAD_REQUEST)


class PlatformDisconnectView(APIView):
    """POST /api/n8n/platforms/<platform>/disconnect/ - Disconnects a platform"""
    permission_classes = [IsAuthenticated]

    def post(self, request, platform):
        platform = (platform or "").lower()
        from platforms.models import UserPlatform

        if platform == "tiktok":
            ConnectedPlatform.objects.filter(
                creator_id=str(request.user.id),
                platform_name="tiktok",
            ).delete()
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "DELETE FROM tiktok_tokens WHERE creator_id = %s",
                        [str(request.user.id)],
                    )
            except Exception:
                # Table may not exist in some environments; do not block disconnect.
                pass
            UserPlatform.objects.update_or_create(
                user=request.user,
                platform_name="TikTok",
                defaults={
                    "connected": False,
                    "connected_at": None,
                    "access_token": None,
                },
            )
            return Response({"success": True, "connected": False})

        if platform == "instagram":
            UserPlatform.objects.update_or_create(
                user=request.user,
                platform_name="Instagram",
                defaults={
                    "connected": False,
                    "connected_at": None,
                    "access_token": None,
                },
            )
            return Response({"success": True, "connected": False})

        if platform == "facebook":
            UserPlatform.objects.update_or_create(
                user=request.user,
                platform_name="Facebook",
                defaults={
                    "connected": False,
                    "connected_at": None,
                    "access_token": None,
                },
            )
            return Response({"success": True, "connected": False})

        return Response({"error": "Platform not supported"}, status=status.HTTP_400_BAD_REQUEST)

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

                try:
                    from accounts.models import User
                    from platforms.models import UserPlatform
                    user = User.objects.filter(id=state).first()
                    if user:
                        UserPlatform.objects.update_or_create(
                            user=user,
                            platform_name="TikTok",
                            defaults={
                                "connected": True,
                                "connected_at": timezone.now(),
                                "access_token": access_token,
                            },
                        )
                except Exception:
                    pass
                
                # Successful response that auto-closes the window
                return HttpResponse("<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head><body style='font-family:sans-serif; text-align:center; padding-top: 50px;'><h1>TikTok Connected Successfully! 🚀</h1><p>You can close this window now and return to the app.</p><script>setTimeout(function(){window.close();}, 1500);</script></body></html>")
            else:
                return HttpResponse(f"Error exchanging token: {resp.text}")
                
        return HttpResponse("Platform not supported")


class N8NCallbackView(APIView):
    """POST /api/n8n/callback/ - Receives callbacks from n8n workflow (e.g. video_ready)"""
    permission_classes = []

    def post(self, request):
        # Verify shared secret
        expected_secret = os.getenv("N8N_CALLBACK_SECRET", "trendai-internal-n8n-secret-2026")
        provided_secret = request.headers.get("X-N8N-Secret", "")
        if not provided_secret or provided_secret != expected_secret:
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)

        action = request.data.get("action")
        session_id = request.data.get("session_id")

        if action == "video_ready":
            video_id = request.data.get("video_id")
            video_url = request.data.get("video_url")
            creator_id = request.data.get("creator_id")

            # Update session status so Flutter polling picks it up
            CreatorSession.objects.filter(session_id=session_id).update(status="video_pending")

            return Response({"status": "ok", "action": action})

        return Response({"status": "ok", "action": action})


class MixVideoView(APIView):
    """
    POST /api/n8n/mix-video/
    Called by n8n to create a video from a Pexels stock clip + TTS of the AI script.
    Body: { pexels_video_url, script_text, session_id, creator_id }
    Header: X-N8N-Secret
    Returns: { video_url }
    """
    permission_classes = []

    def post(self, request):
        import subprocess
        import tempfile
        import shutil
        from pathlib import Path
        from gtts import gTTS

        # Auth
        expected_secret = os.getenv("N8N_CALLBACK_SECRET", "trendai-internal-n8n-secret-2026")
        if request.headers.get("X-N8N-Secret", "") != expected_secret:
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)

        pexels_url = request.data.get("pexels_video_url", "")
        script_text = request.data.get("script_text", "")
        session_id = request.data.get("session_id", "unknown")
        creator_id = request.data.get("creator_id", "")

        if not pexels_url or not script_text:
            return Response({"error": "pexels_video_url and script_text are required"}, status=400)

        media_root = Path(settings.MEDIA_ROOT)
        videos_dir = media_root / "generated_videos"
        videos_dir.mkdir(parents=True, exist_ok=True)

        tmpdir = tempfile.mkdtemp(prefix="trendai_mix_")
        try:
            # 1. Generate TTS audio from script
            tts_path = os.path.join(tmpdir, "tts.mp3")
            tts = gTTS(text=script_text, lang="en")
            tts.save(tts_path)

            # Get TTS audio duration
            probe = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "csv=p=0", tts_path],
                capture_output=True, text=True, timeout=10
            )
            audio_duration = float(probe.stdout.strip())

            # 2. Download Pexels video
            stock_path = os.path.join(tmpdir, "stock.mp4")
            resp = requests.get(pexels_url, timeout=60, stream=True)
            resp.raise_for_status()
            with open(stock_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            # Get stock video duration
            probe_v = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "csv=p=0", stock_path],
                capture_output=True, text=True, timeout=10
            )
            video_duration = float(probe_v.stdout.strip())

            # 3. Build ffmpeg command
            #    - If video shorter than audio: loop it
            #    - If video longer: cut it to audio length
            output_filename = f"ig_{session_id}_{uuid.uuid4().hex[:8]}.mp4"
            output_path = str(videos_dir / output_filename)

            if video_duration < audio_duration:
                # Loop video to match audio length
                loop_count = int(audio_duration / video_duration) + 1
                cmd = [
                    "ffmpeg", "-y",
                    "-stream_loop", str(loop_count),
                    "-i", stock_path,
                    "-i", tts_path,
                    "-t", str(audio_duration),
                    "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                    "-c:a", "aac", "-b:a", "128k",
                    "-map", "0:v:0", "-map", "1:a:0",
                    "-shortest",
                    "-movflags", "+faststart",
                    output_path
                ]
            else:
                # Cut video to audio length
                cmd = [
                    "ffmpeg", "-y",
                    "-i", stock_path,
                    "-i", tts_path,
                    "-t", str(audio_duration),
                    "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                    "-c:a", "aac", "-b:a", "128k",
                    "-map", "0:v:0", "-map", "1:a:0",
                    "-shortest",
                    "-movflags", "+faststart",
                    output_path
                ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                return Response({"error": f"ffmpeg failed: {result.stderr[-500:]}"}, status=500)

            # 4. Upload to public file host so Instagram Graph API can fetch it
            #    (host.docker.internal URLs are not accessible from Facebook servers)
            local_url = f"{request.scheme}://{request.get_host()}/media/generated_videos/{output_filename}"
            video_url = local_url  # fallback

            upload_services = [
                {
                    "name": "catbox.moe",
                    "url": "https://catbox.moe/user/api.php",
                    "data": {"reqtype": "fileupload"},
                    "file_field": "fileToUpload",
                },
                {
                    "name": "litterbox.catbox.moe",
                    "url": "https://litterbox.catbox.moe/resources/serverside/llupload.php",
                    "data": {"reqtype": "fileupload", "time": "72h"},
                    "file_field": "fileToUpload",
                },
            ]

            for svc in upload_services:
                try:
                    with open(output_path, "rb") as f:
                        up = requests.post(
                            svc["url"],
                            data=svc.get("data", {}),
                            files={svc["file_field"]: (output_filename, f, "video/mp4")},
                            timeout=180,
                        )
                        if up.status_code == 200 and up.text.strip().startswith("http"):
                            video_url = up.text.strip()
                            print(f"Video uploaded to {svc['name']}: {video_url}")
                            break
                        else:
                            print(f"{svc['name']} returned {up.status_code}: {up.text[:200]}")
                except Exception as ue:
                    print(f"Upload to {svc['name']} failed: {ue}")

            return Response({
                "video_url": video_url,
                "local_url": local_url,
                "duration": audio_duration,
                "session_id": session_id,
                "creator_id": creator_id,
            })

        except Exception as e:
            return Response({"error": f"Video mixing failed: {str(e)}"}, status=500)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ──────────────────────────────────────────────────────────────
# Niche-aware fallback recommendations (used when no API key)
# ──────────────────────────────────────────────────────────────
_NICHE_BEST_TIMES = {
    'fitness':       '7:00 AM',
    'food':          '12:00 PM',
    'finance':       '8:00 AM',
    'tech':          '9:00 AM',
    'gaming':        '8:00 PM',
    'beauty':        '6:00 PM',
    'fashion':       '5:00 PM',
    'comedy':        '7:00 PM',
    'education':     '10:00 AM',
    'motivation':    '6:00 AM',
    'travel':        '3:00 PM',
    'music':         '9:00 PM',
}

_NICHE_HOOKS = {
    'fitness':    "Most people quit in week 2. Here's how to make it stick...",
    'food':       "This recipe took me 10 minutes and everyone thinks I'm a chef...",
    'finance':    "I saved ${amount} in 30 days using this one rule...",
    'tech':       "This tool just saved me 3 hours of work. You need it.",
    'gaming':     "Nobody talks about this strategy. Until now.",
    'beauty':     "Dermatologists don't want you to know this $5 dupe...",
    'fashion':    "Dress for less — here's how I build outfits under $50.",
    'comedy':     "POV: you did this and immediately regretted it.",
    'education':  "They never taught us this in school. Surprisingly useful.",
    'motivation': "Stop waiting for motivation — here's what actually works.",
    'travel':     "I found this hidden spot so you don't have to.",
    'music':      "This song went from 0 to viral in 48 hours. Here's why.",
}


class RecommendationsView(APIView):
    """
    GET /api/n8n/recommendations/

    Returns 3 AI-personalised content recommendations based on the
    user's saved niches and the latest trending videos in those niches.

    Uses Claude Haiku when ANTHROPIC_API_KEY is set.
    Falls back to smart rule-based recommendations otherwise.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        niches = list(user.categories) if user.categories else ['tech']

        # ── 1. Fetch top trending videos (used as inspiration) ────────────
        trending = list(TrendingVideo.objects.order_by('rank')[:15])

        # ── 2. Try Ollama (local, free) ──────────────────────────────────
        if trending:
            try:
                recs = self._ollama_recommendations(niches, trending)
                if recs:
                    return Response(recs)
            except Exception as e:
                print(f"[recommendations] Ollama failed: {e}")

        # ── 3. Rule-based fallback ───────────────────────────────────────
        return Response(self._rule_based(niches, trending))

    # ------------------------------------------------------------------ #
    def _ollama_recommendations(self, niches, trending):
        import json

        model = os.getenv('OLLAMA_MODEL', 'llama3.2:1b')
        ollama_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')

        # Use top 5 videos as inspiration (keep prompt short for small model)
        video_ids = [v.video_id for v in trending[:5]]
        niche_str = ', '.join(niches)

        prompt = (
            f'Give 3 social media video ideas for a creator in: {niche_str}.\n'
            f'Use these video IDs as inspiration (pick one per idea): {", ".join(video_ids[:3])}.\n'
            f'Reply ONLY with a JSON array. Each item: {{"title":"...","hook":"...","best_time":"7:00 PM","niche":"{niches[0]}","platform":"tiktok","video_id":"...","angle":"..."}}\n'
            f'No explanation. No markdown. JSON only.'
        )

        resp = requests.post(
            f"{ollama_url}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=90,
        )
        resp.raise_for_status()
        text = resp.json().get("response", "").strip()
        # Strip markdown code fences if present
        if '```' in text:
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
        # Extract JSON array
        start = text.find('[')
        end = text.rfind(']') + 1
        if start == -1 or end == 0:
            return None
        return json.loads(text[start:end])

    # ------------------------------------------------------------------ #
    def _rule_based(self, niches, trending):
        """Build 3 varied niche-specific recommendations."""
        _TITLES = [
            ("Top {niche} Tips Nobody Talks About",   "Beginner-friendly {niche} advice that actually works."),
            ("My {niche} Take on This Viral Trend",   "Put a {niche} spin on what's already trending."),
            ("What I Wish I Knew About {niche} Earlier", "Personal story + {niche} lesson = high retention."),
        ]
        _PLATFORMS = ['tiktok', 'instagram', 'youtube']

        recs = []
        niche_cycle = (niches * 3)[:3]

        for i, niche in enumerate(niche_cycle):
            video = trending[i] if i < len(trending) else None
            best_time = _NICHE_BEST_TIMES.get(niche, '6:00 PM')
            hook = _NICHE_HOOKS.get(niche, f"Here's what no one tells you about {niche}...")
            title_tmpl, angle_tmpl = _TITLES[i]

            recs.append({
                'title': title_tmpl.format(niche=niche.title()),
                'hook': hook,
                'best_time': best_time,
                'niche': niche,
                'platform': _PLATFORMS[i],
                'video_id': video.video_id if video else '',
                'angle': angle_tmpl.format(niche=niche),
            })

        return recs
