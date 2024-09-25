from django.urls import path

from . import views

app_name = 'ai_tools'

urlpatterns = [
     path('', views.chatbot_builder_home, name='home'),
     path('ajax/chatbot-form/', views.chatbot_form, name='chatbot_form'),
     path('ajax/chat/', views.chat_form, name='chat_form'),
     path('create-chatbot/', views.create_chatbot, name='create_chatbot'),
     path('ajax/customize-chatbot/', views.customize_chatbot, name='chatbot_customizations'),
     path('chatbot/response/<str:chatbot_uuid>/', views.get_chatbot_response, name='get_chatbot_response'),
     path('customize-bot/', views.customize_bot, name='customize_bot'),
     path('chatbot-settings/<str:chatbot_id>/', views.chatbot_settings, name='chatbot_settings'),
     path('train_bot', views.chatbot_train, name='train_bot'),
     path('embed.js/<str:chatbot_uuid>/', views.embed_js, name='embed_js'),
     path('get_chat_sessions/', views.get_chat_sessions, name='get_chat_sessions'),
     path('get-knowledge-base', views.get_knowledge_base, name='get_knowledge_base'),
     path('export-chatbot', views.export_chatbot, name='export_chatbot'),
     path('export-chats', views.export_chats, name='export_chats'),
     path('add-files', views.add_files, name='add_files'),
     path('delete-knowledge-base-item/', views.delete_knowledge_base_item, name='delete_knowledge_base_item'),
     path('delete_chat_session/', views.delete_chat_session, name='delete_chat_session'),
     path('delete_chatbot/', views.delete_chatbot, name='delete_chatbot'),
]