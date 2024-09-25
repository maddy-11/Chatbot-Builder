import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone

# Create your models here.
def get_default_prompts():
    return [
        "Explain the contents of this chatbot?",
        "Name the files in your Knowledge Base",
        "How can I customize the appearance of the chatbot?"
    ]

def get_default_customization():
    return "{\"font\": \"Montserrat\", \"background_color\": \"#ebeaea\", \"font_color\": \"#ffffff\", \"input_background\": \"#e6e6e6\", \"chatbot_background_color\": \"#000000\", \"input_font_color\": \"#000000\", \"user_background_color\": \"#6e6e6e\", \"user_font_color\": \"#ffffff\", \"prompts_font_color\": \"#ffffff\", \"ai_tools_font_color\": null, \"ai_tools_border_color\": null}"

class Chatbot(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.CharField(max_length=255, unique=True)
    customization = models.JSONField(
        null=True, 
        blank=True, 
        default=get_default_customization
    )
    description = models.TextField(null=True)
    logo = models.ImageField(upload_to='chatbot_logos/', null=True, blank=True)
    custom_url = models.CharField(max_length=255, unique=True, null=True, blank=True)
    allow_prompts = models.BooleanField(default=True)
    prompts = models.JSONField(null=True, blank=True, default=get_default_prompts)
    welcome_message = models.CharField(max_length=255, null=True, blank=True, default="👋 Hi, how can I help you?")
    creativity = models.CharField(max_length=255, null=True, blank=True, default="0")
    prompt_template = models.TextField(null=True, blank=True, 
        default="""
        Your main goal is to provide answers as accurately as possible, based on the instructions and Knowledge Base you have been given.
        If a question does not match the provided Knowledge Base or chat history, do not answer it and courteously ask the user to ask questions within the context.
        Use the following pieces of information to answer the user's question.
        If you don't know the answer, just say that you don't know, don't try to make up an answer.
        """)
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='created_chatbots', on_delete=models.CASCADE)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    def __str__(self):
        return f"{self.name} - {self.creator}"

class KnowledgeBase(models.Model):
    chatbot = models.ForeignKey(Chatbot, on_delete=models.CASCADE)
    folder_path = models.CharField(max_length=255, null=True, blank=True)
    files = models.JSONField(default=dict, null=True, blank=True)
    urls = models.JSONField(default=dict, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False, null=True, blank=True)

    def __str__(self):
        return f"{self.chatbot} - {self.folder_path or self.url}"

class ChatSession(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.CharField(max_length=255, null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='chat_sessions', on_delete=models.CASCADE, null=True, blank=True)
    chatbot = models.ForeignKey(Chatbot, on_delete=models.CASCADE)
    chat_history = models.JSONField(default=dict, null = True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    def __str__(self):
        return f"{self.user} - {self.chatbot}"