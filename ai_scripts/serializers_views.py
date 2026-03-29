"""
AI Scripts serializers and views.
"""
from rest_framework import serializers, generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from .models import AIScript


class AIScriptSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIScript
        fields = ["id", "prompt", "style", "duration", "platform", "hook", "script", "cta", "hashtags", "created_at"]
        read_only_fields = ["id", "hook", "script", "cta", "hashtags", "created_at"]


def generate_script_content(prompt: str, style: str, duration: str, platform: str) -> dict:
    """
    Mock AI script generator.
    Replace this function with OpenAI / Gemini API call in production.
    Returns structured content: hook, script body, CTA, and hashtags.
    """
    style_hooks = {
        "Funny": f"You won't believe what just happened with {prompt.lower()[:40]}... 😂",
        "Informative": f"Here's the truth nobody's talking about: {prompt[:50]}",
        "Dramatic": f"Everything is about to change. {prompt[:40]}... this is why.",
        "Casual": f"Okay so I was just thinking about {prompt.lower()[:40]} and...",
    }
    platform_cta = {
        "TikTok": "Follow for daily insights that actually make sense!",
        "Instagram": "Save this post and share it with someone who needs it!",
        "YouTube": "Subscribe and hit the bell — new video every week!",
        "Facebook": "Share this with your friends and drop a comment below!",
    }
    words = {"30s": 80, "60s": 150, "90s": 220}
    script_body = (
        f"Here's what most people get wrong about {prompt[:30].lower()}. "
        f"While everyone is focused on the surface-level approach, smart creators are going deeper. "
        f"The key insight is that consistency and authenticity drive real engagement. "
        f"Think about it — your audience follows you for your unique perspective, not because you copy trends. "
        f"That's the power of understanding your niche. Apply this today and watch your numbers change."
    )[:words.get(duration, 150)]

    return {
        "hook": style_hooks.get(style, style_hooks["Informative"]),
        "script": script_body,
        "cta": platform_cta.get(platform, "Follow for more!"),
        "hashtags": ["#Trending", "#ContentCreator", "#Viral", f"#{platform}Tips"],
    }


class GenerateScriptView(APIView):
    """POST /api/scripts/generate/ — Generate an AI script (not saved)."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AIScriptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        generated = generate_script_content(
            data["prompt"], data.get("style", "Informative"),
            data.get("duration", "60s"), data.get("platform", "TikTok"),
        )
        # Persist to DB
        script = AIScript.objects.create(
            user=request.user,
            prompt=data["prompt"],
            style=data.get("style", "Informative"),
            duration=data.get("duration", "60s"),
            platform=data.get("platform", "TikTok"),
            **generated,
        )
        return Response(AIScriptSerializer(script).data, status=status.HTTP_201_CREATED)


class SavedScriptListView(generics.ListAPIView):
    """GET /api/scripts/ — List all of the user's saved scripts."""
    serializer_class = AIScriptSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return AIScript.objects.filter(user=self.request.user)


from .models import GeneratedVideo
from django.shortcuts import get_object_or_404
import requests

class GeneratedVideoSerializer(serializers.ModelSerializer):
    """Serializer for the unmanaged GeneratedVideo model from n8n."""
    thumbnail_url = serializers.CharField(source='reel.thumbnail_url', read_only=True)

    class Meta:
        model = GeneratedVideo
        fields = ["id", "reel_id", "user_id_str", "niche", "user_prompt", "script", "script_text", "fal_request_id", "video_url", "status", "created_at", "updated_at", "thumbnail_url"]

class GeneratedVideoListView(generics.ListAPIView):
    """GET /api/videos/ — List all of the user's generated AI videos from n8n."""
    serializer_class = GeneratedVideoSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Show all generated videos (sorted by most recent)
        # In a multi-user production setup, filter by user_id_str=str(self.request.user.id)
        return GeneratedVideo.objects.all().order_by("-created_at")

class VideoGenerateTriggerView(APIView):
    """POST /api/videos/generate/ — Trigger the n8n AI video generation webhook."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        reel_id = request.data.get("reel_id")
        niche = request.data.get("niche")
        prompt = request.data.get("prompt", "Create a viral video")
        
        if not reel_id:
            return Response({"error": "reel_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        webhook_url = "http://localhost:5678/webhook/generate"
        payload = {
            "reel_id": reel_id,
            "niche": niche or (request.user.categories[0] if request.user.categories else "general"),
            "user_id": str(request.user.id),
            "user_email": request.user.email,
            "prompt": prompt
        }
        
        try:
            errors = []
            # Try production webhook first, fallback to webhook-test
            for webhook_url in ["http://localhost:5678/webhook/generate", "http://localhost:5678/webhook-test/generate"]:
                try:
                    resp = requests.post(webhook_url, json=payload, timeout=15)
                    if resp.status_code in (200, 201):
                        return Response({
                            "message": "Video generation job triggered successfully.",
                            "reel_id": reel_id
                        }, status=status.HTTP_200_OK)
                    else:
                        errors.append(f"{webhook_url} returned {resp.status_code}: {resp.text}")
                except requests.ConnectionError:
                    errors.append(f"{webhook_url} is unreachable.")
                    continue
            
            # If we get here, both URLs failed. Print and return the errors.
            error_message = " | ".join(errors)
            print("n8n Webhook Trigger Failed:", error_message)
            return Response({
                "error": "Failed to trigger n8n workflow.",
                "details": error_message
            }, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        except requests.RequestException as e:
            return Response({"error": f"Failed to reach n8n video workflow: {str(e)}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class VideoApproveView(APIView):
    """POST /api/scripts/videos/<id>/approve/ — Mark a generated video as approved and trigger Facebook post via n8n."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        video = get_object_or_404(GeneratedVideo, pk=pk)
        video.status = 'approved'
        video.save(update_fields=['status'])

        # Optionally notify n8n that approval happened so it can post to Facebook.
        # The n8n workflow handles the actual FB posting via its email‑approval node,
        # but we expose this endpoint so the app can also directly signal approval.
        try:
            requests.post(
                'http://localhost:5678/webhook/approve',
                json={'video_id': video.id, 'action': 'approve', 'video_url': video.video_url or ''},
                timeout=5,
            )
        except Exception:
            pass  # n8n notification is best‑effort; DB is already updated.

        return Response({'status': 'approved', 'id': video.id}, status=status.HTTP_200_OK)


class VideoRejectView(APIView):
    """POST /api/scripts/videos/<id>/reject/ — Mark a generated video as rejected."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        video = get_object_or_404(GeneratedVideo, pk=pk)
        video.status = 'rejected'
        video.save(update_fields=['status'])
        return Response({'status': 'rejected', 'id': video.id}, status=status.HTTP_200_OK)


class VideoPublishView(APIView):
    """POST /api/scripts/videos/<id>/publish/ — Post video to Facebook page and mark as published."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        import os
        video = get_object_or_404(GeneratedVideo, pk=pk)
        fb_token = os.environ.get('FB_ACCESS_TOKEN', '').strip()
        fb_page_id = os.environ.get('FB_PAGE_ID', '979625138576176').strip()

        if not video.video_url:
            return Response({'error': 'No video URL to publish.'}, status=status.HTTP_400_BAD_REQUEST)

        if not fb_token:
            return Response({'error': 'FB_ACCESS_TOKEN not configured in .env'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        description = (video.script_text or video.user_prompt or 'AI Generated Video') + ' #TrendAI'

        try:
            fb_resp = requests.post(
                f'https://graph.facebook.com/v24.0/{fb_page_id}/videos',
                data={
                    'file_url': video.video_url,
                    'access_token': fb_token,
                    'description': description,
                    'published': 'true',
                },
                timeout=60,
            )
            fb_data = {}
            try:
                fb_data = fb_resp.json()
            except Exception:
                pass

            if fb_resp.status_code in (200, 201) and 'id' in fb_data:
                video.status = 'published'
                video.save(update_fields=['status'])
                return Response({
                    'status': 'published',
                    'id': video.id,
                    'fb_video_id': fb_data.get('id', ''),
                }, status=status.HTTP_200_OK)
            else:
                # Facebook rejected the request — return the error details
                error_msg = fb_data.get('error', {}).get('message', fb_resp.text[:300])
                return Response({
                    'error': f'Facebook API error: {error_msg}',
                    'fb_status': fb_resp.status_code,
                    'fb_response': fb_data,
                }, status=status.HTTP_502_BAD_GATEWAY)

        except requests.Timeout:
            return Response({'error': 'Facebook API timeout (>60s).'}, status=status.HTTP_504_GATEWAY_TIMEOUT)
        except requests.RequestException as e:
            return Response({'error': f'Network error reaching Facebook: {str(e)}'}, status=status.HTTP_502_BAD_GATEWAY)
