from rest_framework import serializers


class ApiErrorDetailSerializer(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()
    details = serializers.JSONField(
        allow_null=True,
    )


class ApiErrorResponseSerializer(serializers.Serializer):
    error = ApiErrorDetailSerializer()


class HealthChecksSerializer(serializers.Serializer):
    database = serializers.CharField()


class HealthResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    checks = HealthChecksSerializer()
