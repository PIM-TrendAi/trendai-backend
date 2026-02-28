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
