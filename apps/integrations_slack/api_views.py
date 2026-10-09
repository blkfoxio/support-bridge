"""Customer API (called by Cyflare ONE) for connecting Slack workspaces to an org."""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.customer_api.org_access import authorize_org
from common.auth.backends import CognitoJWTAuthentication, FirebaseJWTAuthentication

from . import oauth
from .models import SlackInstallation
from .services import InvalidClaimError, claim_installation


class OrgRequestSerializer(serializers.Serializer):
    org_id = serializers.CharField(required=False)


class ClaimRequestSerializer(OrgRequestSerializer):
    code = serializers.CharField()


class InstallationSerializer(serializers.ModelSerializer):
    class Meta:
        model = SlackInstallation
        fields = ["team_id", "team_name", "status", "installed_at", "activated_at"]


class SlackInstallUrlView(APIView):
    authentication_classes = [CognitoJWTAuthentication, FirebaseJWTAuthentication]

    @extend_schema(
        tags=["Customer - Slack"], request=OrgRequestSerializer, summary="Get an 'Add to Slack' URL for an org"
    )
    def post(self, request):
        data = OrgRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        org_id, error = authorize_org(request, data.validated_data.get("org_id"))
        if error:
            return error
        return Response({"url": oauth.build_authorize_url(org_id=org_id, user_id=request.user.uid)})


class SlackClaimView(APIView):
    authentication_classes = [CognitoJWTAuthentication, FirebaseJWTAuthentication]

    @extend_schema(
        tags=["Customer - Slack"],
        request=ClaimRequestSerializer,
        responses={200: InstallationSerializer},
        summary="Link a Slack workspace installed from Slack to an org",
    )
    def post(self, request):
        data = ClaimRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        org_id, error = authorize_org(request, data.validated_data.get("org_id"))
        if error:
            return error
        try:
            install = claim_installation(data.validated_data["code"], org_id=org_id, user_id=request.user.uid)
        except InvalidClaimError:
            return Response(
                {"error": {"code": "invalid_claim_code", "message": "Invalid or expired code", "status": 400}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(InstallationSerializer(install).data)


class SlackInstallationListView(APIView):
    authentication_classes = [CognitoJWTAuthentication, FirebaseJWTAuthentication]

    @extend_schema(
        tags=["Customer - Slack"],
        responses={200: InstallationSerializer(many=True)},
        summary="List Slack workspaces connected to an org",
    )
    def get(self, request):
        org_id, error = authorize_org(request, request.query_params.get("org_id"))
        if error:
            return error
        installs = SlackInstallation.objects.filter(org_id=org_id)
        return Response(InstallationSerializer(installs, many=True).data)
