from rest_framework.routers import DefaultRouter

from qa.views import QuestionAnswerViewSet


router = DefaultRouter()
router.register(
    "questions",
    QuestionAnswerViewSet,
    basename="question",
)

urlpatterns = router.urls