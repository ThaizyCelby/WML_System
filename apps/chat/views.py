"""Chat API: create conversations, ask questions, list history."""
import logging

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import ChatConversation
from .serializers import (
    AskRequestSerializer, ChatConversationSerializer, ChatMessageSerializer,
)
from .services import ChatService

try:
    from .throttling import ChatbotThrottle
except ImportError:
    from rest_framework.throttling import UserRateThrottle as ChatbotThrottle

logger = logging.getLogger('apps.chat')


class ChatConversationViewSet(viewsets.ModelViewSet):
    serializer_class = ChatConversationSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'delete', 'head', 'options']

    def get_queryset(self):
        return ChatConversation.objects.filter(
            user=self.request.user, is_active=True,
        )

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        conversation = self.get_object()
        qs = conversation.messages.order_by('created_at')
        return Response(ChatMessageSerializer(qs, many=True).data)

    @action(detail=True, methods=['post'], throttle_classes=[ChatbotThrottle])
    def ask(self, request, pk=None):
        serializer = AskRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        conversation = self.get_object()
        try:
            reply = ChatService.ask(
                user=request.user,
                message=serializer.validated_data['message'],
                conversation=conversation,
                provider_name=serializer.validated_data.get('provider'),
            )
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception("Chat ask failed: %s", e)
            return Response(
                {'detail': 'Chat service is temporarily unavailable.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            ChatMessageSerializer(reply).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=['post'], throttle_classes=[ChatbotThrottle])
    def new(self, request):
        serializer = AskRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        channel = 'staff' if (
            request.user.is_superuser
            or request.user.has_role('Administrator')
            or request.user.has_role('Credit Officer')
        ) else 'client'

        conversation = ChatService.get_or_create_conversation(
            user=request.user, channel=channel,
        )
        try:
            reply = ChatService.ask(
                user=request.user,
                message=serializer.validated_data['message'],
                conversation=conversation,
                provider_name=serializer.validated_data.get('provider'),
            )
        except ValueError as e:
            return Response({'detail': str(e)}, status=400)

        return Response({
            'conversation': ChatConversationSerializer(conversation).data,
            'reply': ChatMessageSerializer(reply).data,
        }, status=status.HTTP_201_CREATED)