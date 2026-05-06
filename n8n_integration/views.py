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
from .models import TrendingVideo, CreatorSession, GeneratedScript, GeneratedVideo, PostedVideo, ConnectedPlatform, WorkflowRun, InstagramReel
from .serializers import TrendingVideoSerializer, CombinedSessionStatusSerializer, InstagramReelSerializer

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

    NICHE_KEYWORDS = {
        'entertainment': ['entertainment', 'funny', 'comedy', 'viral', 'fun', 'meme', 'prank', 'challenge', 'skit'],
        'education': ['education', 'learn', 'tutorial', 'howto', 'tips', 'facts', 'science', 'history', 'study'],
        'business': ['business', 'entrepreneur', 'startup', 'marketing', 'sales', 'ceo', 'hustle', 'success'],
        'finance': ['finance', 'money', 'investing', 'stocks', 'crypto', 'budget', 'wealth', 'financial', 'income'],
        'fitness': ['fitness', 'workout', 'gym', 'health', 'exercise', 'diet', 'nutrition', 'training', 'muscle'],
        'motivation': ['motivation', 'mindset', 'inspire', 'success', 'goals', 'growth', 'positivity', 'mindfulness'],
        'gaming': ['gaming', 'gamer', 'game', 'gameplay', 'esports', 'twitch', 'ps5', 'xbox', 'minecraft', 'fortnite'],
        'art': ['art', 'design', 'drawing', 'painting', 'creative', 'artist', 'illustration', 'sketch', 'digital'],
        'fashion': ['fashion', 'style', 'outfit', 'ootd', 'clothing', 'beauty', 'makeup', 'skincare', 'aesthetic'],
        'cooking': ['cooking', 'food', 'recipe', 'chef', 'baking', 'meal', 'kitchen', 'eat', 'delicious'],
        'travel': ['travel', 'adventure', 'explore', 'trip', 'vacation', 'wanderlust', 'destination', 'vlog'],
        'tech': ['tech', 'technology', 'coding', 'programming', 'ai', 'software', 'developer', 'gadget', 'review'],
        'podcast': ['podcast', 'interview', 'talk', 'discussion', 'story', 'storytelling', 'narration'],
        'news': ['news', 'politics', 'world', 'breaking', 'update', 'current', 'economy', 'report'],
        'storytelling': ['story', 'storytime', 'narrative', 'tale', 'vlog', 'experience', 'life', 'pov'],
    }

    def get_queryset(self):
        # Get base queryset ordered by rank
        queryset = TrendingVideo.objects.order_by('rank')
        
        # Apply niche filtering if provided
        niche = self.request.query_params.get('niche')
        if niche:
            search_key = niche.lower().strip()
            # If the specific niche is in our dictionary, use all its related keywords
            search_terms = self.NICHE_KEYWORDS.get(search_key, [search_key])
            
            if search_terms:
                from django.db.models import Q
                query = Q()
                for term in search_terms:
                    # Search in both category field and hashtags field
                    query |= Q(category__icontains=term) | Q(hashtags__icontains=term)
                
                # Check if we have any results using these rich keywords
                filtered = queryset.filter(query)
                if filtered.exists():
                    queryset = filtered
                
        # Return top 10 matches
        return queryset[:10]


class InstagramReelListView(generics.ListAPIView):
    """GET /api/n8n/instagram-reels/ — optional ?niche=fitness or ?niche=fitness,tech"""
    serializer_class = InstagramReelSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        from django.db import connection
        try:
            qs = InstagramReel.objects.all()
            niche_param = self.request.query_params.get('niche', '').strip()
            if niche_param:
                from django.db.models import Q
                niches = [n.strip().lower() for n in niche_param.split(',') if n.strip()]
                query = Q()
                for n in niches:
                    query |= Q(niche__icontains=n)
                qs = qs.filter(query)
            return qs.order_by('-scraped_at', '-views')[:50]
        except Exception as e:
            print(f"InstagramReelListView error: {e}")
            return InstagramReel.objects.order_by('-scraped_at')[:30]


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

        # For YouTube/Facebook/Threads: check their dedicated generated tables
        if session.platform in ("youtube", "facebook", "threads"):
            from django.db import connection
            try:
                if session.platform == "threads":
                    row = None
                    with connection.cursor() as cursor:
                        # Priority query: rows WITH video_url come first.
                        # Matches by session_id OR user_id to handle the n8n
                        # credential user_id vs Django creator_id mismatch.
                        cursor.execute(
                            "SELECT id, script_text as script, NULL as title, "
                            "NULL as description, NULL as tags, video_url, status "
                            "FROM threads_generated_videos "
                            "WHERE session_id = %s OR user_id = %s "
                            "ORDER BY "
                            "  CASE WHEN video_url IS NOT NULL THEN 0 ELSE 1 END, "
                            "  id DESC "
                            "LIMIT 1",
                            [session_id, str(session.creator_id)]
                        )
                        row = cursor.fetchone()

                        # Fallback 1: try matching the session_id prefix
                        if not row:
                            cursor.execute(
                                "SELECT id, script_text as script, NULL as title, "
                                "NULL as description, NULL as tags, video_url, status "
                                "FROM threads_generated_videos "
                                "WHERE session_id LIKE %s "
                                "ORDER BY "
                                "  CASE WHEN video_url IS NOT NULL THEN 0 ELSE 1 END, "
                                "  id DESC "
                                "LIMIT 1",
                                [f"%{session_id}%"]
                            )
                            row = cursor.fetchone()

                        # Fallback 2: get ANY row with a video_url
                        if not row:
                            cursor.execute(
                                "SELECT id, script_text as script, NULL as title, "
                                "NULL as description, NULL as tags, video_url, status "
                                "FROM threads_generated_videos "
                                "WHERE video_url IS NOT NULL "
                                "ORDER BY id DESC "
                                "LIMIT 1"
                            )
                            row = cursor.fetchone()
                            print(f"[Threads fallback2] found row with video_url: {row is not None}")

                        # Fallback 3: get ANY most-recent row (even without video)
                        if not row:
                            cursor.execute(
                                "SELECT id, script_text as script, NULL as title, "
                                "NULL as description, NULL as tags, video_url, status "
                                "FROM threads_generated_videos "
                                "ORDER BY id DESC "
                                "LIMIT 1"
                            )
                            row = cursor.fetchone()
                            print(f"[Threads fallback3] found any row: {row is not None}")

                    # Fallback: GeneratedVideo ORM model (written by MixVideoView)
                    if not row:
                        gen_video = (
                            GeneratedVideo.objects
                            .filter(session_id=session_id)
                            .order_by('-created_at')
                            .first()
                        ) or (
                            GeneratedVideo.objects
                            .filter(creator_id=str(session.creator_id))
                            .order_by('-created_at')
                            .first()
                        )
                        if gen_video and gen_video.video_url:
                            payload["video_id"] = gen_video.video_id
                            payload["video_url"] = gen_video.video_url
                            payload["video_status"] = gen_video.status
                            payload["status"] = "video_pending"

                    if row:
                        gen_id, script, title, description, tags, video_url, gen_status = row
                        payload["script_id"] = str(gen_id)
                        payload["script_content"] = script
                        payload["script_status"] = gen_status
                        if video_url:
                            payload["video_id"] = str(gen_id)
                            payload["video_url"] = video_url
                            payload["video_status"] = gen_status

                        # "done" maps to "video_pending" so Publish button appears
                        if gen_status == "done" or video_url:
                            payload["status"] = "video_pending"
                        elif gen_status == "processing":
                            if script:
                                payload["status"] = "script_pending"
                                payload["script_status"] = "pending_approval"
                            else:
                                payload["status"] = "script_generation"
                        elif gen_status == "pending_review":
                            payload["status"] = "script_pending"
                            payload["script_status"] = "pending_approval"
                        elif gen_status == "approved":
                            payload["status"] = "processing"
                        elif gen_status in ("published", "posted"):
                            payload["status"] = "posted"
                        elif gen_status == "rejected":
                            payload["status"] = "declined"
                        else:
                            payload["status"] = "script_generation"
                else:
                    with connection.cursor() as cursor:
                        if session.platform == "facebook":
                            cursor.execute(
                                "SELECT id, script_content, script_text, hook, body, cta, "
                                "hook_text, video_prompt, caption, hashtags, music_vibe, "
                                "reel_id, video_url, status "
                                "FROM facebook_generated_videos "
                                "WHERE user_id = %s ORDER BY id DESC LIMIT 1",
                                [int(session.creator_id)]
                            )
                            row = cursor.fetchone()
                            if row:
                                (gen_id, script_content, script_text, hook, body, cta,
                                 hook_text, video_prompt, caption, hashtags, music_vibe,
                                 reel_id, video_url, gen_status) = row
                                full_script = script_content or script_text or ""
                                payload["script_id"] = str(gen_id)
                                payload["script_content"] = full_script
                                payload["script_status"] = gen_status
                                payload["hook"] = hook or ""
                                payload["body"] = body or ""
                                payload["cta"] = cta or ""
                                payload["hook_text"] = hook_text or ""
                                payload["video_prompt"] = video_prompt or ""
                                payload["caption"] = caption or ""
                                payload["hashtags"] = hashtags or ""
                                payload["music_vibe"] = music_vibe or ""
                                if video_url:
                                    payload["video_id"] = str(gen_id)
                                    payload["video_url"] = video_url
                                    payload["video_status"] = gen_status
                                if gen_status == "done":
                                    payload["status"] = "ready"
                                elif gen_status == "processing":
                                    # If we have a script already, let the user review it while video generates
                                    if full_script:
                                        payload["status"] = "script_pending"
                                    else:
                                        payload["status"] = "processing"
                                elif gen_status == "approved":
                                    payload["status"] = "processing"
                                elif gen_status in ("published", "posted"):
                                    payload["status"] = "posted"
                                elif gen_status == "rejected":
                                    payload["status"] = "declined"
                                else:
                                    payload["status"] = "script_generation"

                                # Critical: Ensure script review screen sees it as ready if script content exists
                                if full_script and gen_status in ("processing", "done", "approved"):
                                    payload["script_status"] = "pending_approval"
                        else:  # youtube
                            cursor.execute(
                                "SELECT id, script, title, description, tags, video_url, status "
                                "FROM youtube_generated WHERE user_id = %s AND LOWER(niche) = LOWER(%s) ORDER BY id DESC LIMIT 1",
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
                                    payload["script_status"] = "pending_approval"
                                elif gen_status == "approved":
                                    payload["status"] = "ready"
                                elif gen_status == "posted":
                                    payload["status"] = "posted"
                                elif gen_status == "rejected":
                                    payload["status"] = "declined"
                                elif gen_status == "draft":
                                    payload["status"] = "draft"
                                else:
                                    payload["status"] = "script_generation"
            except Exception as e:
                print(f"Error checking {session.platform} generated table: {e}")

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
    FACEBOOK_START_WEBHOOK_PATH = os.getenv("N8N_FACEBOOK_START_WEBHOOK_PATH", "facebook-start")
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
                "post_id": selected_video_id,
                "reel_id": selected_video_id,
            }

            if platform == "instagram":
                session_id = f"{request.user.id}_{int(time.time() * 1000)}"
                CreatorSession.objects.create(
                    session_id=session_id,
                    creator_id=str(request.user.id),
                    selected_video_id=selected_video_id,
                    niche=niche,
                    platform="instagram",
                    status="script_generation",
                )
                payload["session_id"] = session_id
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
            elif platform == "threads":
                session_id = f"threads_{request.user.id}_{int(time.time() * 1000)}"
                # We don't necessarily need a CreatorSession if threads_generated_videos tracks it,
                # but the app expects a session_id to poll.
                CreatorSession.objects.create(
                    session_id=session_id,
                    creator_id=str(request.user.id),
                    selected_video_id=selected_video_id,
                    niche=niche,
                    platform="threads",
                    status="script_generation",
                )
                payload["session_id"] = session_id
                success = trigger_n8n_webhook(
                    "threads-generate",
                    payload,
                )
            else:  # TikTok
                session_id = f"{request.user.id}_{int(time.time() * 1000)}"
                CreatorSession.objects.create(
                    session_id=session_id,
                    creator_id=str(request.user.id),
                    selected_video_id=selected_video_id,
                    niche=niche,
                    platform="tiktok",
                    status="script_generation",
                )
                payload["session_id"] = session_id
                success = trigger_n8n_webhook(
                    self.TIKTOK_START_WEBHOOK_ID,
                    payload,
                    fallback_ids=[self.TIKTOK_START_WEBHOOK_PATH],
                )

            if not success:
                return Response({"error": "Failed to trigger n8n workflow. Please ensure it is active or listening in n8n."}, status=status.HTTP_502_BAD_GATEWAY)

            return Response({"success": True, "session_id": session_id, "message": f"{platform.title()} workflow started. Session is initializing in n8n."})
        except Exception as exc:
            print(f"StartWorkflowView failed unexpectedly: {exc}")
            return Response({"error": "Failed to start video generation workflow."}, status=status.HTTP_502_BAD_GATEWAY)

class TriggerScrapingView(APIView):
    """POST /api/n8n/trigger-scrape/ - Trigger the scraper workflow (TikTok or Instagram)"""
    permission_classes = [IsAuthenticated]

    # Webhook IDs by platform
    SCRAPE_WEBHOOK_IDS = {
        "tiktok": "8a4b64f3-ac29-4591-a1b7-4c2089f92bb4",
        "instagram": "instagram-scrape-v2",
        # Must match the n8n Webhook Trigger node path exactly (path: "scrape")
        "facebook": os.getenv("N8N_FACEBOOK_SCRAPE_WEBHOOK_PATH", "scrape"),
        "youtube": os.getenv("N8N_YOUTUBE_SCRAPE_WEBHOOK_PATH", "youtube-scrape"),
        "threads": os.getenv("N8N_THREADS_SCRAPE_WEBHOOK_PATH", "threads-scrape"),
    }

    def post(self, request):
        niche_param = request.data.get("niche", "")
        platform = request.data.get("platform", "tiktok").lower()
        niches = [n.strip() for n in niche_param.split(',') if n.strip()]
        if not niches:
            niches = ["trending"]
        webhook_id = self.SCRAPE_WEBHOOK_IDS.get(platform, self.SCRAPE_WEBHOOK_IDS["tiktok"])
        overall_success = True
        for niche in niches:
            run = WorkflowRun.objects.create(platform=platform, niche=niche, status='running')
            payload = {"niche": niche, "platform": platform, "run_id": run.id}
            success = trigger_n8n_webhook(webhook_id, payload, timeout=120)
            if not success:
                overall_success = False
        if overall_success:
            return Response({"success": True, "message": f"Scraping triggered for {len(niches)} niches."}, status=status.HTTP_200_OK)
        return Response({"success": False, "message": "Could not reach N8N workflow. Make sure N8N is running and the workflow is active."}, status=status.HTTP_200_OK)

class GetLatestSessionView(APIView):
    """GET /api/n8n/sessions/latest/ - Get the user's latest session"""
    permission_classes = [IsAuthenticated]
    def get(self, request):
        qs = CreatorSession.objects.filter(creator_id=str(request.user.id))
        platform = request.query_params.get('platform')
        niche = request.query_params.get('niche')
        if platform:
            qs = qs.filter(platform=platform.lower())
        if niche:
            qs = qs.filter(niche=niche)
        session = qs.order_by('-created_at').first()
        if not session:
            # For threads: if no creator_session exists yet, synthesize one from
            # threads_generated_videos so the poller can still get a session_id.
            if platform and platform.lower() == 'threads':
                try:
                    from django.db import connection as _conn
                    with _conn.cursor() as cur:
                        cur.execute(
                            "SELECT id, session_id FROM threads_generated_videos "
                            "WHERE video_url IS NOT NULL "
                            "ORDER BY id DESC LIMIT 1"
                        )
                        tgv_row = cur.fetchone()
                    if tgv_row:
                        tgv_id, tgv_session_id = tgv_row
                        synthetic_session_id = tgv_session_id or f"threads_synth_{tgv_id}"
                        obj, _ = CreatorSession.objects.get_or_create(
                            session_id=synthetic_session_id,
                            defaults={
                                'creator_id': str(request.user.id),
                                'selected_video_id': '',
                                'niche': '',
                                'platform': 'threads',
                                'status': 'script_generation',
                            }
                        )
                        return Response({"session_id": obj.session_id})
                except Exception as e:
                    print(f"GetLatestSessionView threads fallback error: {e}")
            return Response({"session_id": None})
        return Response({"session_id": session.session_id})


class ApproveScriptView(APIView):
    """POST /api/n8n/approve/script/"""
    permission_classes = [IsAuthenticated]

    SCRIPT_APPROVE_WEBHOOK_ID = os.getenv("N8N_SCRIPT_APPROVE_WEBHOOK_ID", "0ec65146-238d-4c79-a441-25721e9373e7")
    SCRIPT_APPROVE_WEBHOOK_PATH = os.getenv("N8N_SCRIPT_APPROVE_WEBHOOK_PATH", "tiktok-script-approve")
    INSTAGRAM_SCRIPT_APPROVE_PATH = os.getenv("N8N_INSTAGRAM_SCRIPT_APPROVE_PATH", "instagram-script-approve")

    YOUTUBE_SCRIPT_APPROVE_PATH = os.getenv("N8N_YOUTUBE_SCRIPT_APPROVE_PATH", "youtube-approve-script")

    def post(self, request):
        session_id = request.data.get("session_id")
        script_id = request.data.get("script_id")
        approved = request.data.get("approved", False)
        decision = "approve" if approved else "decline"
        platform = request.data.get("platform", "tiktok").lower()

        session = CreatorSession.objects.filter(session_id=session_id).first()

        if platform == "youtube":
            return self._handle_youtube(request, session, approved)

        payload = {
            "sessionId": session_id,
            "scriptId": script_id,
            "decision": decision,
            "action": decision,
            "feedback": request.data.get("feedback", ""),
            "creatorId": str(request.user.id),
            "niche": session.niche if session else request.data.get("niche", ""),
            "selectedVideoId": session.selected_video_id if session else request.data.get("selected_video_id", ""),
        }

        if platform == "instagram":
            success = trigger_n8n_webhook(self.INSTAGRAM_SCRIPT_APPROVE_PATH, payload)
        else:
            success = trigger_n8n_webhook(self.SCRIPT_APPROVE_WEBHOOK_ID, payload,
                                          fallback_ids=[self.SCRIPT_APPROVE_WEBHOOK_PATH])

        if not success:
            return Response({"error": "Failed proxying to n8n"}, status=400)

        return Response({"success": True})

    def _handle_youtube(self, request, session, approved):
        from django.db import connection as db_conn
        if not session:
            return Response({"error": "Session not found"}, status=status.HTTP_404_NOT_FOUND)

        user_id = int(session.creator_id)
        niche = session.niche

        with db_conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM youtube_generated WHERE user_id = %s AND LOWER(niche) = LOWER(%s) "
                "AND status = 'pending_review' ORDER BY id DESC LIMIT 1",
                [user_id, niche]
            )
            row = cursor.fetchone()

        if not row:
            return Response({"error": "No pending script found"}, status=status.HTTP_404_NOT_FOUND)

        generated_id = row[0]

        if approved:
            with db_conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE youtube_generated SET status = 'approved' WHERE id = %s",
                    [generated_id]
                )
        else:
            # Mark rejected and trigger a new generation so polling finds a fresh pending_review
            with db_conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE youtube_generated SET status = 'rejected' WHERE id = %s",
                    [generated_id]
                )
            regen_payload = {
                "user_id": user_id,
                "niche": niche,
                "email": request.user.email,
                "prompt": "",
            }
            trigger_n8n_webhook("generate-video-v2", regen_payload)

        return Response({"success": True})

class ApproveVideoView(APIView):
    """POST /api/n8n/approve/video/ - Supports TikTok, Instagram, and Facebook"""
    permission_classes = [IsAuthenticated]

    VIDEO_APPROVE_WEBHOOK_ID = os.getenv("N8N_VIDEO_APPROVE_WEBHOOK_ID", "35bda5a4-5875-4ce6-b33f-3bea2ca0cc8a")
    VIDEO_APPROVE_WEBHOOK_PATH = os.getenv("N8N_VIDEO_APPROVE_WEBHOOK_PATH", "tiktok-video-approve")
    INSTAGRAM_VIDEO_APPROVE_PATH = "instagram-video-approve"
    FACEBOOK_VIDEO_APPROVE_PATH = os.getenv("N8N_FACEBOOK_VIDEO_APPROVE_PATH", "facebook-video-approve")
    THREADS_VIDEO_APPROVE_PATH = "threads-video-approve"
    YOUTUBE_VIDEO_APPROVE_PATH = "youtube-video-approve"

    def post(self, request):
        session_id = request.data.get("session_id")
        video_id = request.data.get("video_id")
        approved = request.data.get("approved", False)
        decision = "approve" if approved else "decline"
        platform = request.data.get("platform", "tiktok").lower()
        is_draft = request.data.get("is_draft", False)

        if is_draft:
            try:
                from django.db import connection
                if platform == "threads":
                    with connection.cursor() as cursor:
                        cursor.execute("UPDATE threads_generated_videos SET status = 'draft' WHERE id = %s", [video_id])
                elif platform == "youtube":
                    with connection.cursor() as cursor:
                        cursor.execute("UPDATE youtube_generated SET status = 'draft' WHERE id = %s", [video_id])
                elif platform == "facebook":
                    with connection.cursor() as cursor:
                        cursor.execute("UPDATE facebook_generated_videos SET status = 'draft' WHERE id = %s", [video_id])
                else:
                    GeneratedVideo.objects.filter(video_id=video_id).update(status='draft')
                return Response({"success": True})
            except Exception as e:
                return Response({"error": f"Failed to save draft locally: {e}"}, status=400)

        payload = {
            "sessionId": session_id,
            "videoId": video_id,
            "decision": decision,
            "action": decision,
            "feedback": request.data.get("feedback", ""),
        }

        if platform == "facebook":
            from .models import FacebookGeneratedVideo
            fb_video = FacebookGeneratedVideo.objects.filter(id=video_id).first()
            payload["videoUrl"] = fb_video.video_url if fb_video else ""
            success = trigger_n8n_webhook(self.FACEBOOK_VIDEO_APPROVE_PATH, payload)
        elif platform == "instagram":
            success = trigger_n8n_webhook(self.INSTAGRAM_VIDEO_APPROVE_PATH, payload)
        elif platform == "threads":
            success = trigger_n8n_webhook(self.THREADS_VIDEO_APPROVE_PATH, payload)
        elif platform == "youtube":
            payload["approved"] = approved
            payload["generated_id"] = video_id
            success = trigger_n8n_webhook(self.YOUTUBE_VIDEO_APPROVE_PATH, payload)
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
            
            # Fallback to chosen trending video thumbnail if generated one is missing
            thumb = v.thumbnail_url
            if not thumb and session:
                trending = TrendingVideo.objects.filter(video_id=session.selected_video_id).first()
                if trending:
                    thumb = trending.thumbnail_url

            data.append({
                'video_id': v.video_id,
                'session_id': v.session_id,
                'video_url': v.video_url,
                'thumbnail_url': thumb or '',
                'status': v.status,
                'niche': session.niche if session else '',
                'script_preview': (script.script_content[:120] + '...') if script else '',
                'created_at': v.created_at.isoformat() if v.created_at else None,
            })

        # 2. Fetch from n8n-managed tables (YouTube, Facebook, Threads)
        user_id_str = str(request.user.id)
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                # Threads
                cursor.execute(
                    "SELECT id, script_text, video_url, status FROM threads_generated_videos WHERE user_id = %s",
                    [user_id_str]
                )
                for row in cursor.fetchall():
                    gen_id, script_text, video_url, gen_status = row
                    data.append({
                        'video_id': str(gen_id),
                        'session_id': f'threads_{gen_id}',
                        'video_url': video_url or '',
                        'status': gen_status,
                        'niche': 'Threads',
                        'script_preview': ((script_text or '')[:120] + '...') if script_text else '',
                        'created_at': None,
                    })

                # Facebook
                cursor.execute(
                    "SELECT id, script_content as script, video_url, thumbnail_url, status FROM facebook_generated_videos WHERE user_id = %s",
                    [int(user_id_str)]
                )
                for row in cursor.fetchall():
                    gen_id, script, video_url, thumbnail_url, gen_status = row
                    data.append({
                        'video_id': str(gen_id),
                        'session_id': f'facebook_{gen_id}',
                        'video_url': video_url or '',
                        'thumbnail_url': thumbnail_url or '',
                        'status': gen_status,
                        'niche': 'Facebook',
                        'script_preview': ((script or '')[:120] + '...') if script else '',
                        'created_at': None,
                    })

                # YouTube
                cursor.execute(
                    "SELECT id, script, video_url, thumbnail_url, status FROM youtube_generated WHERE user_id = %s",
                    [int(user_id_str)]
                )
                for row in cursor.fetchall():
                    gen_id, script, video_url, thumbnail_url, gen_status = row
                    data.append({
                        'video_id': str(gen_id),
                        'session_id': f'youtube_{gen_id}',
                        'video_url': video_url or '',
                        'thumbnail_url': thumbnail_url or '',
                        'status': gen_status,
                        'niche': 'YouTube',
                        'script_preview': ((script or '')[:120] + '...') if script else '',
                        'created_at': None,
                    })
        except Exception as e:
            print(f"Error fetching from n8n tables: {e}")

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

        if action == "script_ready":
            # YouTube sends platform + user_id (no session_id / script_id)
            if request.data.get("platform") == "youtube":
                user_id = str(request.data.get("user_id", ""))
                if user_id:
                    CreatorSession.objects.filter(
                        creator_id=user_id,
                        platform="youtube",
                    ).order_by("-created_at").update(status="script_pending")
                return Response({"status": "ok", "action": action})

            script_content = request.data.get("script_content", "")
            script_id = request.data.get("script_id", "")
            creator_id = str(request.data.get("creator_id", ""))

            # Update the script row to pending_approval with content
            if session_id:
                update_fields = {"status": "pending_approval"}
                if script_content:
                    update_fields["script_content"] = script_content
                if script_id:
                    GeneratedScript.objects.filter(script_id=script_id).update(**update_fields)
                else:
                    GeneratedScript.objects.filter(session_id=session_id).update(**update_fields)

            # For Threads: update the dedicated table
            if session_id and session_id.startswith("threads_"):
                from django.db import connection
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE threads_generated_videos SET script_text = %s, status = 'pending_review' WHERE session_id = %s",
                        [script_content, session_id]
                    )

            # Update the N8N-created session
            CreatorSession.objects.filter(session_id=session_id).update(status="script_pending")

            # N8N creates its own session_id — bridge to the Django-created session
            # so Flutter's polling (which uses the Django session_id) works.
            if creator_id:
                django_session = (
                    CreatorSession.objects
                    .filter(creator_id=creator_id)
                    .exclude(session_id=session_id)
                    .order_by('-created_at')
                    .first()
                )
                if django_session:
                    django_session.status = "script_pending"
                    django_session.save(update_fields=["status"])
                    # Re-link the script to the Django session_id
                    if script_id:
                        GeneratedScript.objects.filter(script_id=script_id).update(
                            session_id=django_session.session_id
                        )
                    elif session_id:
                        GeneratedScript.objects.filter(
                            session_id=session_id, status="pending_approval"
                        ).update(session_id=django_session.session_id)

            return Response({"status": "ok", "action": action})

        if action == "video_ready":
            video_id = request.data.get("video_id")
            video_url = request.data.get("video_url")
            creator_id = str(request.data.get("creator_id", ""))

            # For Threads: update the dedicated table and persist to GeneratedVideo
            if session_id and session_id.startswith("threads_"):
                from django.db import connection
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE threads_generated_videos SET video_url = %s, status = 'done', session_id = %s WHERE user_id = %s AND session_id IS NULL",
                        [video_url, session_id, str(creator_id)]
                    )
                    cursor.execute(
                        "UPDATE threads_generated_videos SET video_url = %s, status = 'done' WHERE session_id = %s",
                        [video_url, session_id]
                    )
                new_video_id = f"threads_vid_{session_id}_{video_id or ''}"
                GeneratedVideo.objects.update_or_create(
                    session_id=session_id,
                    defaults={
                        "video_id": new_video_id,
                        "video_url": video_url,
                        "status": "pending_approval",
                        "creator_id": str(creator_id),
                    }
                )

            # Update the session that N8N reported
            CreatorSession.objects.filter(session_id=session_id).update(status="video_pending")

            # Check if the video is already linked to this session (Instagram flow:
            # N8N reuses the Django session_id, so no bridging is needed).
            video_already_here = (
                video_id and GeneratedVideo.objects.filter(
                    video_id=video_id, session_id=session_id
                ).exists()
            ) or (
                not video_id and GeneratedVideo.objects.filter(session_id=session_id).exists()
            )

            if not video_already_here and creator_id:
                # TikTok flow: N8N uses a different session_id, bridge to Django session.
                django_session = (
                    CreatorSession.objects
                    .filter(creator_id=creator_id)
                    .exclude(session_id=session_id)
                    .order_by('-created_at')
                    .first()
                )
                if django_session:
                    django_session.status = "video_pending"
                    django_session.save(update_fields=["status"])
                    if video_id:
                        GeneratedVideo.objects.filter(video_id=video_id).update(
                            session_id=django_session.session_id
                        )
                    elif session_id:
                        GeneratedVideo.objects.filter(session_id=session_id).update(
                            session_id=django_session.session_id
                        )

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

            # Save to generated_videos so Flutter polling finds it.
            # Use the public URL (catbox) if upload succeeded; fall back to local_url.
            new_video_id = f"ig_vid_{session_id}_{uuid.uuid4().hex[:8]}"
            GeneratedVideo.objects.update_or_create(
                session_id=session_id,
                defaults={
                    "video_id": new_video_id,
                    "video_url": video_url,
                    "status": "pending_approval",
                    "creator_id": creator_id,
                }
            )
            CreatorSession.objects.filter(session_id=session_id).update(status="video_pending")

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


class MergeVoiceoverView(APIView):
    """
    POST /api/n8n/merge-voiceover/
    Called by n8n TikTok workflow to overlay a pre-generated TTS audio file onto
    a generated/stock video. Both inputs are public URLs.
    Body: { video_url, audio_url, session_id }
    Header: X-N8N-Secret
    Returns: { video_url }  — public URL of the merged MP4
    """
    permission_classes = []

    def post(self, request):
        import subprocess
        import tempfile
        import shutil
        from pathlib import Path

        expected_secret = os.getenv("N8N_CALLBACK_SECRET", "trendai-internal-n8n-secret-2026")
        if request.headers.get("X-N8N-Secret", "") != expected_secret:
            return Response({"error": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)

        video_url = request.data.get("video_url", "")
        audio_url = request.data.get("audio_url", "")
        session_id = request.data.get("session_id", "unknown")

        if not video_url:
            return Response({"error": "video_url is required"}, status=400)

        if not audio_url:
            return Response({"video_url": video_url})

        tmpdir = tempfile.mkdtemp(prefix="trendai_vo_")
        try:
            video_path = os.path.join(tmpdir, "video.mp4")
            audio_path = os.path.join(tmpdir, "audio.mp3")
            output_path = os.path.join(tmpdir, "merged.mp4")

            resp_v = requests.get(video_url, timeout=120, stream=True)
            resp_v.raise_for_status()
            with open(video_path, "wb") as f:
                for chunk in resp_v.iter_content(chunk_size=8192):
                    f.write(chunk)

            resp_a = requests.get(audio_url, timeout=30, stream=True)
            resp_a.raise_for_status()
            with open(audio_path, "wb") as f:
                for chunk in resp_a.iter_content(chunk_size=8192):
                    f.write(chunk)

            result = subprocess.run([
                "ffmpeg", "-y",
                "-i", video_path,
                "-i", audio_path,
                "-c:v", "copy",
                "-c:a", "aac",
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-shortest",
                output_path
            ], capture_output=True, text=True, timeout=300)

            if result.returncode != 0:
                return Response({"video_url": video_url})

            output_filename = f"tiktok_vo_{session_id}_{uuid.uuid4().hex[:8]}.mp4"

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

            merged_url = video_url
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
                            merged_url = up.text.strip()
                            break
                except Exception:
                    continue

            return Response({"video_url": merged_url})

        except Exception as e:
            return Response({"video_url": video_url})
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


class FacebookReelsListView(APIView):
    """
    GET /api/n8n/facebook_reels/
    Returns niche-filtered Facebook reels scraped by n8n for the
    "Pick a Trend" screen. Mirrors TrendingVideoListView for TikTok.

    Query params:
      ?niche=cuisine   — filter by niche (required for best results)
      ?limit=20        — max results (default 20)
    """
    permission_classes = [IsAuthenticated]

    NICHE_KEYWORDS = {
        'entertainment': ['entertainment', 'funny', 'comedy', 'viral', 'fun', 'meme', 'prank', 'challenge', 'skit'],
        'education': ['education', 'learn', 'tutorial', 'howto', 'tips', 'facts', 'science', 'history', 'study'],
        'business': ['business', 'entrepreneur', 'startup', 'marketing', 'sales', 'ceo', 'hustle', 'success'],
        'finance': ['finance', 'money', 'investing', 'stocks', 'crypto', 'budget', 'wealth', 'financial', 'income'],
        'fitness': ['fitness', 'workout', 'gym', 'health', 'exercise', 'diet', 'nutrition', 'training', 'muscle'],
        'motivation': ['motivation', 'mindset', 'inspire', 'success', 'goals', 'growth', 'positivity', 'mindfulness'],
        'gaming': ['gaming', 'gamer', 'game', 'gameplay', 'esports', 'twitch', 'ps5', 'xbox', 'minecraft', 'fortnite'],
        'art': ['art', 'design', 'drawing', 'painting', 'creative', 'artist', 'illustration', 'sketch', 'digital'],
        'fashion': ['fashion', 'style', 'outfit', 'ootd', 'clothing', 'beauty', 'makeup', 'skincare', 'aesthetic'],
        'cooking': ['cooking', 'food', 'recipe', 'chef', 'baking', 'meal', 'kitchen', 'eat', 'delicious'],
        'travel': ['travel', 'adventure', 'explore', 'trip', 'vacation', 'wanderlust', 'destination', 'vlog'],
        'tech': ['tech', 'technology', 'coding', 'programming', 'ai', 'software', 'developer', 'gadget', 'review'],
        'podcast': ['podcast', 'interview', 'talk', 'discussion', 'story', 'storytelling', 'narration'],
        'news': ['news', 'politics', 'world', 'breaking', 'update', 'current', 'economy', 'report'],
        'storytelling': ['story', 'storytime', 'narrative', 'tale', 'vlog', 'experience', 'life', 'pov'],
    }

    # Maps each niche to the Facebook page slugs configured in the N8N scraper.
    # Filtering by page_url is language-agnostic — works even for Arabic/French content.
    PAGE_NICHE_MAP = {
        'entertainment': ['9GAG', 'LADbible', 'unilad', 'ViralHog', 'CapitaleFM', 'ShemsFM'],
        'education':     ['TEDtalks', 'NatGeo', 'ScienceAlert', 'brainfoodofficial'],
        'business':      ['EntrepreneurMagazine', 'Inc', 'garyvee', 'Forbes'],
        'finance':       ['bloomberg', 'cnbc', 'TheMotleyFool', 'investopedia'],
        'fitness':       ['NikeTrainingClub', 'MensHealthMagazine', 'muscleandfitness', 'bodybuilding'],
        'motivation':    ['TonyRobbins', 'Goalcast', 'JayShettyPage', 'BeInspiredChannel'],
        'gaming':        ['IGN', 'GameSpot', 'PlayStation', 'Xbox'],
        'art':           ['Behance', 'adobe', 'BoredPanda'],
        'fashion':       ['vogue', 'HM', 'ZARA', 'NordstromRack'],
        'cooking':       ['buzzfeedtasty', 'FoodNetwork', 'Tastemade', 'bonappetitmag'],
        'travel':        ['lonelyplanet', 'NatGeoTravel', 'TravelChannel', 'beautifuldestinations'],
        'tech':          ['TechCrunch', 'TheVerge', 'wired', 'engadget'],
        'podcast':       ['TimFerriss', 'HubermanLab', 'lexfridman'],
        'news':          ['BBCNews', 'CNN', 'reuters', 'AlJazeera', 'TunisieNumerique', 'mosaiquefm', 'BusinessNewsTN'],
        'storytelling':  ['HumansOfNewYork', 'storycorps', 'AmazingStories'],
    }

    def get(self, request):
        niche = request.query_params.get("niche", "").strip().lower()
        limit = min(int(request.query_params.get("limit", 20)), 50)

        _SELECT = """
            SELECT id, reel_id, reel_url, page_url, text, play_count,
                   duration_ms, niche, thumbnail_url, created_at, status
            FROM facebook_reels
        """
        columns: list = []
        rows: list = []

        try:
            with connection.cursor() as cursor:
                if niche and niche != "general":
                    page_slugs = self.PAGE_NICHE_MAP.get(niche, [])
                    keywords   = self.NICHE_KEYWORDS.get(niche, [niche])

                    # Build page_url conditions (language-agnostic: filter by
                    # which Facebook page the reel came from).
                    page_conditions  = " OR ".join(["page_url ILIKE %s"] * len(page_slugs))
                    page_params      = [f"%/{slug}%" for slug in page_slugs]

                    # Secondary: text keyword matching for pages not in our map.
                    text_conditions  = " OR ".join(["text ILIKE %s"] * len(keywords))
                    text_params      = [f"%{k}%" for k in keywords]

                    if page_slugs:
                        where = f"({page_conditions}) OR ({text_conditions})"
                        params = page_params + text_params
                    else:
                        where = text_conditions
                        params = text_params

                    cursor.execute(
                        f"{_SELECT} WHERE {where} "
                        f"ORDER BY play_count DESC, created_at DESC LIMIT %s",
                        params + [limit],
                    )
                    columns = [c[0] for c in cursor.description]
                    rows = cursor.fetchall()

                    # Fallback: if nothing matched, return all reels so the
                    # screen is never empty while the DB is still being seeded.
                    if not rows:
                        cursor.execute(
                            f"{_SELECT} ORDER BY play_count DESC, created_at DESC LIMIT %s",
                            [limit],
                        )
                        columns = [c[0] for c in cursor.description]
                        rows = cursor.fetchall()
                else:
                    cursor.execute(
                        f"{_SELECT} ORDER BY play_count DESC, created_at DESC LIMIT %s",
                        [limit],
                    )
                    columns = [c[0] for c in cursor.description]
                    rows = cursor.fetchall()

        except Exception as e:
            return Response(
                {"error": f"Failed to fetch Facebook reels: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        reels = []
        for row in rows:
            r = dict(zip(columns, row))
            reels.append({
                "id":            r.get("id"),
                "reel_id":       r.get("reel_id", ""),
                "reel_url":      r.get("reel_url", ""),
                "page_url":      r.get("page_url", ""),
                "text":          r.get("text", ""),
                "play_count":    r.get("play_count", 0),
                "duration_ms":   r.get("duration_ms", 0),
                "niche":         r.get("niche", ""),
                "thumbnail_url": r.get("thumbnail_url", ""),
                "created_at":    r["created_at"].isoformat() if r.get("created_at") else None,
                "status":        r.get("status", "scraped"),
            })

        return Response(reels)


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
        import random
        user = request.user

        # Accept ?niche= param — supports multiple comma-separated niches
        niche_param = request.query_params.get('niche', None)
        if niche_param:
            niches = [n.strip() for n in niche_param.split(',') if n.strip()]
        else:
            niches = list(user.categories) if user.categories else ['tech']

        # ── 1. Fetch trending + shuffle so every call returns different results
        trending_all = list(TrendingVideo.objects.order_by('rank')[:20])
        random.shuffle(trending_all)
        trending = trending_all[:10]

        # ── 2. Try Groq (free, llama-3.3-70b) ────────────────────────────
        if trending:
            try:
                recs = self._groq_recommendations(niches, trending)
                if recs:
                    return Response(recs)
            except Exception as e:
                print(f"[recommendations] Groq failed: {e}")

        # ── 3. Rule-based fallback ───────────────────────────────────────
        return Response(self._rule_based(niches, trending))

    # ------------------------------------------------------------------ #
    def _groq_recommendations(self, niches, trending):
        import json
        import random
        from datetime import datetime

        groq_key = os.getenv('GROQ_API_KEY', '')
        if not groq_key:
            return None

        # Cycle niches across the 3 slots: [fitness, tech] → [fitness, tech, fitness]
        niche_cycle = (niches * 3)[:3]
        video_examples = [
            f'"{v.title}" by {v.author} — views: {v.views}, hashtags: {", ".join(v.hashtags[:3]) if v.hashtags else "none"}, video_id: {v.video_id}'
            for v in trending[:6]
        ]

        hook_styles = [
            'pattern interrupt ("Nobody tells you this but...")',
            'curiosity gap ("The real reason X happens will shock you")',
            'specific number ("I gained 10k followers doing this ONE thing")',
            'controversy ("Unpopular opinion about {niche}...")',
            'personal story ("I wasted 6 months before I learned this")',
            'direct challenge ("Stop doing X if you actually want Y")',
        ]
        chosen_style = random.choice(hook_styles).format(niche=niche_cycle[0])
        today = datetime.now().strftime('%A')

        system_prompt = 'You are a viral TikTok content strategist. Always respond with valid JSON only, no markdown.'
        user_prompt = (
            f'It is {today}. Give exactly 3 viral TikTok video ideas. Each idea targets a specific niche:\n'
            f'- Idea 1 niche: {niche_cycle[0]}\n'
            f'- Idea 2 niche: {niche_cycle[1]}\n'
            f'- Idea 3 niche: {niche_cycle[2]}\n\n'
            f'Trending videos to inspire you (assign one video_id per idea, all different):\n'
            + '\n'.join(video_examples) +
            f'\n\nHook style for this session: {chosen_style}\n\n'
            f'Return ONLY a JSON object with a "recommendations" array. Each item:\n'
            f'{{"title":"...","hook":"...","best_time":"7:00 PM","niche":"<the niche for that idea>","platform":"tiktok","video_id":"...","angle":"..."}}\n'
            f'Each hook must be scroll-stopping (first 3 seconds). All 3 ideas must feel completely different. JSON only.'
        )

        resp = requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {groq_key}',
                'Content-Type': 'application/json',
            },
            json={
                'model': 'llama-3.3-70b-versatile',
                'messages': [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt},
                ],
                'response_format': {'type': 'json_object'},
                'max_tokens': 700,
                'temperature': 0.9,
            },
            timeout=15,
        )
        resp.raise_for_status()
        content = resp.json()['choices'][0]['message']['content']
        data = json.loads(content)
        # Handle {"recommendations": [...]} or bare array
        if isinstance(data, list):
            return data
        for val in data.values():
            if isinstance(val, list):
                return val
        return None

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
