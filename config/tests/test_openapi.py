from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase


class OpenAPITests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="openapi-user",
            password="test-password",
        )
        self.client.force_authenticate(user=self.user)

    def test_schema_contains_all_api_operations(self):
        response = self.client.get(
            reverse("api-schema"),
            HTTP_ACCEPT="application/vnd.oai.openapi+json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        schema = response.data

        self.assertEqual(
            schema["info"]["title"],
            "RoshanAI API",
        )
        self.assertEqual(
            schema["info"]["version"],
            "1.0.0",
        )

        expected_operations = {
            "/health/": {
                "get",
            },
            "/api/v1/documents/": {
                "get",
                "post",
            },
            "/api/v1/documents/{id}/": {
                "get",
                "patch",
                "delete",
            },
            "/api/v1/questions/": {
                "get",
                "post",
            },
            "/api/v1/questions/{id}/": {
                "get",
            },
        }

        for path, methods in expected_operations.items():
            with self.subTest(path=path):
                self.assertIn(path, schema["paths"])

                documented_methods = (
                    set(schema["paths"][path])
                    & {
                        "get",
                        "post",
                        "put",
                        "patch",
                        "delete",
                    }
                )

                self.assertEqual(
                    documented_methods,
                    methods,
                )

        self.assertFalse(
            schema["paths"]["/health/"]["get"].get(
                "security"
            )
        )

    def test_schema_and_docs_require_authentication(
        self,
    ):
        self.client.force_authenticate(user=None)

        for url_name in ("api-schema", "api-docs"):
            with self.subTest(url_name=url_name):
                response = self.client.get(
                    reverse(url_name)
                )

                self.assertIn(
                    response.status_code,
                    (
                        status.HTTP_401_UNAUTHORIZED,
                        status.HTTP_403_FORBIDDEN,
                    ),
                )

    def test_health_check_is_public(self):
        self.client.force_authenticate(user=None)

        response = self.client.get(
            reverse("health-check")
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            response.data,
            {
                "status": "healthy",
                "checks": {
                    "database": "available",
                },
            },
        )
