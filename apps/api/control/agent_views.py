from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from control.agent_serializers import EnrollRequestSerializer, HeartbeatRequestSerializer
from control.authentication import AgentTokenAuthentication
from control.services.enrollment import EnrollmentError, enroll_agent
from control.services.heartbeat import apply_heartbeat


def _bearer(request) -> str:
    raw = request.headers.get("Authorization", "")
    if not raw.startswith("Bearer "):
        return ""
    return raw[7:].strip()


class EnrollView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = EnrollRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = enroll_agent(
                enrollment_secret=_bearer(request),
                **serializer.validated_data,
            )
        except EnrollmentError:
            return Response(
                {"detail": "Invalid enrollment credential"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return Response(
            {
                "server_id": str(result.server.public_id),
                "agent_token": result.agent_token,
            },
            status=status.HTTP_201_CREATED,
        )


class HeartbeatView(APIView):
    authentication_classes = [AgentTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = HeartbeatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        apply_heartbeat(request.user.server, serializer.validated_data)
        return Response(status=status.HTTP_204_NO_CONTENT)
