from rest_framework import serializers
from .models import TrendingVideo, CreatorSession, GeneratedScript, GeneratedVideo

class TrendingVideoSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrendingVideo
        fields = '__all__'

class CreatorSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CreatorSession
        fields = '__all__'

class GeneratedScriptSerializer(serializers.ModelSerializer):
    class Meta:
        model = GeneratedScript
        fields = '__all__'

class GeneratedVideoSerializer(serializers.ModelSerializer):
    class Meta:
        model = GeneratedVideo
        fields = '__all__'

class CombinedSessionStatusSerializer(serializers.Serializer):
    # This serializer combines data from CreatorSession, GeneratedScript, and GeneratedVideo
    # to send a unified payload to the Flutter app.
    session_id = serializers.CharField()
    creator_id = serializers.CharField()
    niche = serializers.CharField()
    status = serializers.CharField()
    selected_video_id = serializers.CharField()
    
    script_id = serializers.CharField(allow_null=True, required=False)
    script_content = serializers.CharField(allow_null=True, required=False)
    script_status = serializers.CharField(allow_null=True, required=False)
    
    video_id = serializers.CharField(allow_null=True, required=False)
    video_url = serializers.CharField(allow_null=True, required=False)
    video_thumbnail = serializers.CharField(allow_null=True, required=False)
    video_status = serializers.CharField(allow_null=True, required=False)
    
    tiktok_post_url = serializers.CharField(allow_null=True, required=False)
