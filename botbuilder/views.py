from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from .models import Chatbot, KnowledgeBase, ChatSession
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse, HttpResponseForbidden, Http404
from django.shortcuts import get_object_or_404
from .models import *
import json
import os
from django.urls import reverse
from django.middleware.csrf import get_token
from bs4 import BeautifulSoup
import requests
from .utils import *
import zipfile
from io import BytesIO, StringIO
import shutil
import pandas as pd

@login_required(login_url='login')
def ai_tools_home(request):
    return render(request, 'ai_tools/ai_tools_home.html')
    
@login_required(login_url='login')
def chatbot_builder_home(request):
    # Filter chatbots by the logged-in user
    chatbots = Chatbot.objects.filter(creator=request.user if request.user.is_authenticated else None)
    return render(request, 'ai_tools/chatbot_builder_home.html', {'chatbots': chatbots})

def photo_generator_home(request):
    return render(request, 'ai_tools/photo_generator_home.html')


@login_required(login_url='login')
def create_chatbot(request):
    if request.method == 'POST':
        uploaded_at = timezone.now()
        uploaded_at_str = uploaded_at.isoformat()
        uploaded_files = []
        name = request.POST.get('name')
        description = request.POST.get('description')
        if Chatbot.objects.filter(name=name).exists():
            return JsonResponse({'status': 'error', 'message': "Chatbot's Name Already Taken"}, status=500)
        if not description:
            description = "A dummy description"
        chatbot_dir = os.path.join("media", "chatbot", name, "data")
        file_info = []
        if 'file[0]' in request.FILES and request.FILES['file[0]']:
            os.makedirs(chatbot_dir, exist_ok=True)
            if request.FILES.keys():
                for key in request.FILES.keys():
                    if key.startswith('file['):
                        uploaded_files.append(request.FILES[key])

                for uploaded_file in uploaded_files:
                    file_path = os.path.join(chatbot_dir, uploaded_file.name)
                    with open(file_path, 'wb') as f:
                        for chunk in uploaded_file.chunks():
                            f.write(chunk)
                    file_info.append({'filename': uploaded_file.name, 'file_path': file_path, 'uploaded_at': uploaded_at_str})
                    if uploaded_file.name.endswith('.xlsx'):
                        add_empty_row_to_excel(file_path)
                    elif uploaded_file.name.endswith('.csv'):
                        add_empty_row_to_csv(file_path)

        url_info = []
        url_input = request.POST.getlist('url_input[]', None)
        if url_input and any(url_input):
            os.makedirs(chatbot_dir, exist_ok=True)
            for url in url_input:
                if url:
                    file_paths = load_url(url, chatbot_dir)
                    for file_path in file_paths:
                        if is_google_drive_folder_url(url):
                            url_info.append({'url': file_path[0], 'file_path': file_path[1], 'uploaded_at': uploaded_at_str})
                        else:
                            url_info.append({'url': url, 'file_path': file_path, 'uploaded_at': uploaded_at_str})

        url_file = request.FILES.get('url_txt', None)
        if url_file is not None:
            os.makedirs(chatbot_dir, exist_ok=True)
            url_list = url_file.read().decode('utf-8').splitlines()
            for url in url_list:
                if url:
                    file_paths = load_url(url, chatbot_dir)
                    for file_path in file_paths:
                        if is_google_drive_folder_url(url):
                            url_info.append({'url': file_path[0], 'file_path': file_path[1], 'uploaded_at': uploaded_at_str})
                        else:
                            url_info.append({'url': url, 'file_path': file_path, 'uploaded_at': uploaded_at_str})

        if name and description:
            new_chatbot = Chatbot(
                name=name,
                description=description,
                creator=request.user
            )
            new_chatbot.save()
            if file_info == [] and url_info == []:
                return JsonResponse({'status': 'error', 'message': 'No Knowledge Files Detected.'}, status=400)
            
            knowledge_base = KnowledgeBase(
                chatbot=new_chatbot,
                folder_path=chatbot_dir,
                files=file_info,
                urls=url_info
            )
            knowledge_base.save()

            return JsonResponse({'status': 'success', 'chatbot_id': new_chatbot.id}, status=201)

        return JsonResponse({'status': 'error', 'message': 'Name is required.'}, status=400)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

def chatbot_form(request):
    return render(request, 'ai_tools/create_chatbot_form.html')

def customize_chatbot(request):
    chatbot_uuid = request.GET.get('chatbot_uuid')
    chatbot = Chatbot.objects.filter(uuid=chatbot_uuid).first()
    if not chatbot.logo:
        chatbot.logo = "chatbot_logos/logo.jpg"
    if isinstance(chatbot.customization, str):
        customization = json.loads(chatbot.customization)
    else:
        customization = chatbot.customization
    formatted_prompts = "\n".join(chatbot.prompts)
    return render(request, 'ai_tools/customize_chatbot.html', {'current_chatbot':customization, 'chatbot':chatbot, 'prompts':formatted_prompts})

def chat_form(request):
    chat_uuid = request.GET.get('chat_uuid')
    chatbot_uuid = request.GET.get('chatbot_uuid')
    chat = ChatSession.objects.filter(uuid=chat_uuid).first()
    if chatbot_uuid:
        chatbot = Chatbot.objects.filter(uuid= chatbot_uuid).first()
        if chatbot is not None:
            welcome_message = chatbot.welcome_message
            if isinstance(chatbot.customization, str):
                customization = json.loads(chatbot.customization)
            else:
                customization = chatbot.customization
            prompts = json.dumps(chatbot.prompts)
        else:
            customization = dict
            prompts = dict

        return render(request, 'ai_tools/chat.html', {'current_chatbot':customization, 'prompts':prompts, 'chatbot':chatbot, 'welcome':welcome_message})
    else:
        if chat:
            chatbot = chat.chatbot
            if chatbot is not None:
                welcome_message = chatbot.welcome_message
                if isinstance(chatbot.customization, str):
                    customization = json.loads(chatbot.customization)
                else:
                    customization = chatbot.customization
                prompts = json.dumps(chatbot.prompts)
            else:
                customization = dict
                prompts = dict
                
            session_history_key = f'session_history_{chat.uuid}'
            request.session[f"{session_history_key}"] = chat.chat_history
            return render(request, 'ai_tools/chat.html', {'current_chatbot':customization, 'chat':chat, 'prompts':prompts, 'chatbot':chatbot, 'welcome':welcome_message})
        else:
            pass

def customize_bot(request):
    if request.method == 'POST':
        chatbot_uuid = request.POST.get('chatbot')
        prompts = request.POST.get('prompts')
        show_prompts = request.POST.get('show_prompts')
        welcome_message = request.POST.get('welcome_message')
        # Get the uploaded image file
        chatbot_logo = request.FILES.get('chatbot-logo')
        creativity = request.POST.get('creativity')
        # Construct customization data
        customization_data = {
            'font': request.POST.get('font'),
            'background_color': request.POST.get('background-color'),
            'font_color': request.POST.get('font-color'),
            'input_background': request.POST.get('input-background'),
            'chatbot_background_color': request.POST.get('chatbot-background-color'),
            'input_font_color': request.POST.get('input-font-color'),
            'user_background_color': request.POST.get('user-background-color'),
            'user_font_color': request.POST.get('user-font-color'),
            'prompts_font_color': request.POST.get('prompts-font-color'),
            'ai_tools_font_color': request.POST.get('ai-tools-font-color'),
            'ai_tools_border_color': request.POST.get('ai-tools-border-color'),
        }
        # Convert customization data to JSON
        chatbot_url = request.POST.get('chatbot-url')
        customization_json = json.dumps(customization_data)
        # Assuming 'customization_json' is your JSON string
        customization_data = json.loads(customization_json)

        # Now you can access the 'font' property


        # Update or create Chatbot instance with customization data
        chatbot = Chatbot.objects.filter(uuid=chatbot_uuid).first()
        if chatbot:
            # Handle image upload
            if chatbot_logo:
                # Save the uploaded image to your media directory
                chatbot.logo = chatbot_logo
                
            if chatbot_url:
                chatbot.custom_url = chatbot_url
            if prompts:
                lines = [line.strip() for line in prompts.splitlines() if line.strip()]
                chatbot.prompts = lines
            if show_prompts:
                if show_prompts == '0':
                    val = True
                else:
                    val = False
                chatbot.allow_prompts = val
            chatbot.creativity = creativity
            chatbot.welcome_message = welcome_message

            chatbot.customization = customization_json
            chatbot.save()
            return JsonResponse({'success': 'Chatbot customization updated successfully.'})
        else:
            return JsonResponse({'error': 'Chatbot not found.'}, status=404)
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=400)

def chatbot_settings(request, chatbot_id):
    chatbot = Chatbot.objects.filter(uuid=chatbot_id).first()
    return render(request, 'ai_tools/chatbot_settings.html', {'chatbot': chatbot})

def chatbot_train(request):
    if request.method == 'POST':
        trained = train_chatbot(request.POST.get('chatbot_name'))
        if trained:
            if trained['status'] and trained['status'] is False:
                return JsonResponse({'error': trained['error']}, status=500)
            else:
                return JsonResponse({'success': 'Chatbot trained successfully.'})
        else:
            return JsonResponse({'error': 'Some Error Occured.'}, status=500)

    return JsonResponse({'error': 'Method Not Allowed.'}, status=500)

@csrf_exempt
def get_chatbot_response(request, chatbot_uuid):
    if request.method == 'POST':
        chat_id = request.POST.get('chat_id')
        query = request.POST.get('user_input')
        if chat_id == 'None' or chat_id == '' or chat_id == 'undefined':
            chat_id = None
        chatbot = Chatbot.objects.filter(uuid=chatbot_uuid).first()
        
        if not chatbot:
            return JsonResponse({'error': 'Invalid chatbot ID'}, status=400)
        
        chatbot_dir = os.path.join("media", 'chatbot', chatbot.name)
        chat = get_or_create_chat_session(request, chat_id, chatbot)
        # return JsonResponse({'response': 'response', 'chat':chat.uuid})
        # -----
        session_history_key = f'session_history_{chat.uuid}'
        session_history = request.session.get(session_history_key, [])
        if session_history is None:
            session_history = chat.chat_history
        # Process the user query and get the bot response
        response = handle_query(query, chatbot_dir, session_history, chatbot)
        print(response)
        
        # Store chat history
        store_chat_history(request, chat, query, response)
        
        # Return the bot response as JSON
        return JsonResponse({'response': response, 'chat':chat.uuid})
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

def embed_js(request, chatbot_uuid):
    current_domain = request.scheme + '://' + request.get_host()

    # Construct the URL for get_chatbot_response view
    url = reverse('ai_tools:get_chatbot_response', kwargs={'chatbot_uuid': chatbot_uuid})
    url = current_domain + url

    chatbot = Chatbot.objects.filter(uuid=chatbot_uuid).first()
    
    if chatbot is not None:
        prompts = json.dumps(chatbot.prompts)
        welcome_message = chatbot.welcome_message
        customization = json.loads(chatbot.customization)
        if not chatbot.logo:
            chatbot.logo = "/chatbot_logos/logo.jpg"
        logo_url = request.build_absolute_uri(chatbot.logo.url)
        logo_url = logo_url + '/'
        if not chatbot.custom_url:
            chatbot.custom_url = '#'
    else:
        prompts = '[]'  # Provide a default value if chatbot is not found
        customization = {}
        logo_url = ''
    csrf_token = get_token(request)
    data = """
    (function() {
  // Create the bubble icon
  var bubble = document.createElement('div');
  bubble.id = 'chatbot-bubble';
  bubble.classList.add('border','shadow');
  document.body.appendChild(bubble);

  // Add Google Fonts to the document
  var googleFontsLink = document.createElement('link');
  googleFontsLink.href = "https://fonts.googleapis.com/css2?family=Montserrat:wght@400;700&display=swap";
  googleFontsLink.rel = "stylesheet";
  document.head.appendChild(googleFontsLink);

  // Create the modal
  var modal = document.createElement('div');
  modal.id = 'chatbot-modal';
  modal.classList.add('rounded-lg');
  modal.style.display = 'none';
  modal.innerHTML = `
  <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;700&display=swap" rel="stylesheet">
    <header>
    <div class="title flex items-center justify-between">
        <a href=" """ + chatbot.custom_url + """ "><img src=" """ + logo_url + """ " style="width: 50px; height: 50px;" class="object-cover rounded-full shadow-lg" alt="Chatbot Logo"></a>
        <p class="mx-auto my-auto">Powered by AI Chatrooms</p>
    </div>
    </header>
    <div class="chat-container-h">
    <div class="chat-history flex-grow" id="chat_chat_history">
        <div class="chat-message no-wrap"><p> """ + welcome_message + """</p></div>
    </div>
      <div class="input_container p-2 bg-gray-200">
        <div class="flex" style="align-items:flex-start;">
           <textarea class="flex-1 rounded-md border-gray-300 chat-input p-2" id="chat_user_input" name="user_input" rows="1" placeholder="Type your question here..."></textarea>
           <button class="ml-2 bg-gray-700 text-white p-2 rounded-md submit_btn">
                <svg class="MuiSvgIcon-root MuiSvgIcon-fontSizeMedium css-z20xrw" focusable="false" aria-hidden="true" viewBox="0 0 20 20" width="20" height="20" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M4.05648 16.3129C3.21648 16.3129 2.68398 16.0279 2.34648 15.6904C1.68648 15.0304 1.22148 13.6279 2.70648 10.6504L3.35898 9.35285C3.44148 9.18035 3.44148 8.82035 3.35898 8.64785L2.70648 7.35035C1.21398 4.37285 1.68648 2.96285 2.34648 2.31035C2.99898 1.65035 4.40898 1.17785 7.37898 2.67035L13.799 5.88035C15.3965 6.67535 16.274 7.78535 16.274 9.00035C16.274 10.2154 15.3965 11.3254 13.8065 12.1204L7.38649 15.3304C5.93149 16.0579 4.85148 16.3129 4.05648 16.3129ZM4.05648 2.81285C3.65148 2.81285 3.33648 2.91035 3.14148 3.10535C2.59398 3.64535 2.81148 5.04785 3.71148 6.84035L4.36399 8.14535C4.60398 8.63285 4.60398 9.36785 4.36399 9.85535L3.71148 11.1529C2.81148 12.9529 2.59398 14.3479 3.14148 14.8879C3.68148 15.4354 5.08398 15.2179 6.88399 14.3179L13.304 11.1079C14.4815 10.5229 15.149 9.75035 15.149 8.99285C15.149 8.23535 14.474 7.46285 13.2965 6.87785L6.87648 3.67535C5.73649 3.10535 4.75398 2.81285 4.05648 2.81285Z" fill="white"></path><path d="M8.12813 9.5625H4.07812C3.77062 9.5625 3.51562 9.3075 3.51562 9C3.51562 8.6925 3.77062 8.4375 4.07812 8.4375H8.12813C8.43563 8.4375 8.69063 8.6925 8.69063 9C8.69063 9.3075 8.43563 9.5625 8.12813 9.5625Z" fill="white"></path></svg>
            </button>
   </div>
</div>
</div>
  `;
  document.body.appendChild(modal);

  // Add styles
  var style = document.createElement('style');
  style.innerHTML = `
      *, ::after, ::before {
        box-sizing: border-box;
        border-width: 0;
        border-style: solid;
        border-color: #e5e7eb;
      }
      #chatbot-modal .hidden {
      display: none;
    }
      #chatbot-modal .shadow {
      --tw-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px -1px rgba(0, 0, 0, 0.1);
      box-shadow: var(--tw-shadow);
    }

    #chatbot-modal .border {
        border-width: 1px;
        border-style: solid;
    }

    #chatbot-modal .border-md {
        border-width: 2px;
        border-style: solid;
    }
    /* Tailwind's bg-gray-200 */
    #chatbot-modal .bg-gray-200 {
      background-color: #e5e7eb;
    }

    /* Tailwind's bg-gray-300 */
    #chatbot-modal .bg-gray-300 {
      background-color: #d1d5db;
    }

    /* Tailwind's bg-gray-700 */
    #chatbot-modal .bg-gray-700 {
      background-color: #374151;
    }
    #chatbot-modal .rounded-md {
      border-radius: 0.375rem; /* 6px */
    }
    .rounded-lg {
      border-radius: 0.5rem; /* 8px */
    }
    #chatbot-modal .flex {
      display: flex;
    }
    #chatbot-modal .flex-1 {
      flex: 1 1 0%;
    }
    #chatbot-modal .p-2 {
      padding: 0.5rem; /* 8px */
    }

    #chatbot-modal .text-white {
      color: #ffffff;
    }

    #chatbot-modal .items-center {
      align-items: center;
    }

    #chatbot-modal .justify-between {
      justify-content: space-between;
    }
    /* object-cover */
    #chatbot-modal .object-cover {
        object-fit: cover;
    }

    /* rounded-full */
    #chatbot-modal .rounded-full {
        border-radius: 100%;
    }

    /* shadow-lg */
    #chatbot-modal .shadow-lg {
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 
                    0 4px 6px -2px rgba(0, 0, 0, 0.05);
    }
    #chatbot-modal .mx-auto {
        margin-left: auto;
        margin-right: auto;
    }
    #chatbot-modal .my-auto{
      margin-top: auto;
      margin-bottom: auto;
    }
    #chatbot-modal .font-bold-sm {
        font-weight: bold;
        font-size: 0.875rem; /* equivalent to Tailwind's text-sm */
    }
    #chatbot-modal h2 {
        font-weight: bold;
        font-size: 1.2em;
        color
    }
    #chatbot-modal .flex-grow {
        flex-grow: 1;
    }
    #chatbot-modal .ml-2 {
        margin-left: 0.5rem; /* 8px */
    }
    #chatbot-modal 
    input,
    button,
    select,
    optgroup,
    textarea {
      margin: 0; // 1
      font-family: inherit;
      @include font-size(inherit);
      line-height: inherit;
    }
  .chat-container-h {
        flex: 1;
        display: flex;
        flex-direction: column;
        margin: auto;
        # border: 1px solid #ccc;
        # border-radius: 5px;
        overflow: hidden;
        height: 60vh;
        background-color: """+ customization.get('background_color', '') +""";
    }
    .chat-history {
        flex: 1;
        padding: 15px;
        overflow-y: auto;

    }
    .chat-message {
        display: flex;
        margin-bottom: 10px;
        border-radius: 10px;
    }
    .chat-message p {
        padding: 10px;
        border-radius: 10px;
        word-wrap: break-word;
        font-size:14px;
        font-family: """+ customization.get('font', '') +""";
    }
    .chat-message.user {
        justify-content: flex-end;
    }
    .chat-message.user p {
        padding: 10px;
        max-width: 75%;
        background-color: """+ customization.get('user_background_color', '') +""";
        color: """+ customization.get('user_font_color', '') +""";
        align-self: flex-end;
        border-top-right-radius: 0;
    }
    .chat-res{
        max-width: 75%;
        background-color: """+ customization.get('chatbot_background_color', '') +""";
        color: """+ customization.get('font_color', '') +""";
        padding: 0px 10px;
        border-radius: 10px;
        border-top-left-radius: 0;

    }
    .chat-message.chatbot p {
        white-space: pre-wrap;
        white-space: -moz-pre-wrap;
        white-space: -pre-wrap;
        white-space: -o-pre-wrap;
        word-wrap: break-word;
        color: """+ customization.get('font_color', '') +"""!important;
    }
    .chat-message ul {
        list-style-type: disc;
        margin-left: 20px;
        padding-left: 0;
    }
    .chat-message li {
        margin: 5px 0;
    }
    .chat-message.no-wrap p {
        white-space:nowrap;
        background-color: """+ customization.get('chatbot_background_color', '') +""";
        color: """+ customization.get('font_color', '') +""";
        border-radius: 10px;
        border-top-left-radius: 0;
        padding: 10px 10px;
    }
  .chat-input {
    background-color: """+ customization.get('input_background', '') +""";
    color: """+ customization.get('input_font_color', '') +""";
    box-sizing: border-box;
    resize: none;
}
    .prompts-container {
    display: flex;
    overflow-x: auto; /* Enable horizontal scrolling */
    max-width: 100%; /* Adjust as needed */
    white-space: nowrap; /* Prevent prompts from wrapping */
}

    .prompt {
        padding: 5px;
        margin-right: 7px;
        border: 1px solid #ccc;
        border-radius: 8px;
        background-color: """+ customization.get('prompts_font_color', '') +""";
        color:black;
        cursor: pointer;
    }
    #chatbot-bubble {
      position: fixed;
      bottom: 20px;
      right: 20px;
      width: 50px;
      height: 50px;
      background-image: url('""" + logo_url + """');
      background-size: cover;
      border-radius: 50%;
      cursor: pointer;
      z-index: 1000;
    }
    .loader {
    display: flex;
    justify-content: center;
    align-items: center;
}
    .loader span {
        display: inline-block;
        width: 8px;
        height: 8px;
        margin: 0 4px;
        background-color: #ccc;
        border-radius: 50%;
        animation: loader 0.6s infinite alternate;
    }
    .loader span:nth-child(2) {
        animation-delay: 0.2s;
    }
    .loader span:nth-child(3) {
        animation-delay: 0.4s;
    }
    @keyframes loader {
        from {
            opacity: 0.3;
        }
        to {
            opacity: 1;
        }
    }

    #chatbot-modal {
      display: none;
      position: fixed;
      bottom: 100px;
      right: 20px;
      width: 90%; /* Adjust width percentage for responsiveness */
      max-width: 450px; /* Limit maximum width for larger screens */
      max-height: 80%; /* Limit maximum height for smaller screens */
      background-color: white;
      border: 1px solid #ccc;
      box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
      z-index: 1000;
    }

    #chatbot-modal header {
      padding: 5px;
    }
  `;
  document.head.appendChild(style);

  // Add event listeners
  bubble.onclick = function() {
    modal.style.display = modal.style.display === 'none' ? 'block' : 'none';
  };
  

})();

var jQueryScript = document.createElement('script');
jQueryScript.src = "https://code.jquery.com/jquery-3.6.1.min.js";
jQueryScript.onload = function() {
    console.log("jQuery loaded successfully!");
    // Your jQuery dependent code goes here
};
jQueryScript.onerror = function() {
    console.error("Failed to load jQuery from CDN.");
};
document.body.appendChild(jQueryScript);

//-------------------
$(document).ready(function() {

        localStorage.setItem('chat_uuid', 'None');
        const $textarea = $('#chat_user_input');
            const lineHeight = 20; // Assuming each line height is approximately 20px

            $textarea.on('input', function() {
                // Reset the rows to 1 to correctly calculate scrollHeight
                $textarea.attr('rows', 1);

                const padding = parseInt($textarea.css('padding-top')) + parseInt($textarea.css('padding-bottom'));
                const border = parseInt($textarea.css('border-top-width')) + parseInt($textarea.css('border-bottom-width'));
                const scrollHeight = this.scrollHeight - padding - border;
                const rows = Math.min(Math.floor(scrollHeight / lineHeight), 10);

                $textarea.attr('rows', rows > 1 ? rows : 1);
            });
        });
        $(document).ready(function() {

        var prompts = """ + prompts + """;
        console.log("prompts", prompts);
        var promptsContainer = $('<div class="prompts-container flex"></div>');

            for (var i = 0; i < prompts.length; i++) {
        promptsContainer.append('<div class="prompt border rounded-lg">' + prompts[i] + '</div>');
    }
"""
    if chatbot.allow_prompts:
        data += """
        promptsContainer.insertBefore('.input_container');
        """
        # Ending the script tag
    data += r"""
        $('.prompt').on('click', function() {
            var promptText = $(this).text();
            $('#chat_user_input').val(promptText)
            sendMessage();  // Pass the prompt text to sendMessage function
        });

            $('.submit_btn').click(function(event) {
        event.preventDefault();  // Prevent form submission
        sendMessage();  // Function to handle sending message
    });

            $('#chat_user_input').keydown(function(event) {
                if (event.keyCode === 13 && !event.shiftKey) {
                    event.preventDefault();
                    sendMessage();
                }
            });

            function formatText(text) {
                // Convert headings
                text = text.replace(/\*\*(.*?)\*\*/g, '<span style="font-weight:bold;font-size: 1.2em;">$1</span>'); // Level 1 headings
                text = text.replace(/### (.*?)/g, '<span style="font-weight:bold;font-size: 1em;">$1</span>');

                // Convert unordered list items

                text = text.replace(/(\\n\* .+?)(?=\\n[^*]|\\n*$)/gs, '\\n<ul>$1</ul>');
                text = text.replace(/\\n\* (.+?)(?=\\n|$)/g, '<li>$1</li>');

                // Handle special cases where lists are continuous
                text = text.replace(/<\/ul>\\n<ul>/g, ''); // Merge adjacent lists

                // Convert line breaks to paragraph breaks for simple text
                text = text.replace(/\\n\\n/g, '</p><p>'); // Double line break to paragraph

                // Wrap entire text in a container
                text = '<div class="chat-res"><p>' + text.trim() + '</p></div>';

                return text;
            }
            function sendMessage() {
                var user_input = $('#chat_user_input').val().trim();
        if (user_input === '') return; // prevent sending empty messages
        $('#chat_chat_history').append('<div class="chat-message user"><p>' + user_input + '</p></div>');
        $('#chat_user_input').val('');  // Clear input field
        $('#chat_chat_history').scrollTop($('#chat_chat_history')[0].scrollHeight);  // Scroll to the bottom

        var loaderHtml = '<div class="chat-message chatbot"><div class="loader"><span></span><span></span><span></span><span></span><span></span></div></div>';
        $('#chat_chat_history').append(loaderHtml);
        $('#chat_chat_history').scrollTop($('#chat_chat_history')[0].scrollHeight);  // Scroll to the bottom

        $.ajax({
            type: 'POST',
            url: '"""+ url +"""',
            data: {
                csrfmiddlewaretoken: '""" + csrf_token + """',
                user_input: user_input,
                chat_id: localStorage.getItem('chat_uuid')
                
            },
            success: function(response) {
                console.log(response);
                $('.loader').parent().remove();
                $('#chat_chat_history').append('<div class="chat-message chatbot"><p>' + formatText(response.response) + '</p></div>');
                $('#chat_chat_history').scrollTop($('#chat_chat_history')[0].scrollHeight);  // Scroll to the bottom
                localStorage.setItem('chat_uuid', response.chat);
                $('.prompt').addClass('hidden')
            },
            error: function(xhr, status, error) {
                console.log(xhr);
                var errorMessage = "An Error Occurred";
                if (xhr.responseJSON && xhr.responseJSON.error) {
                    errorMessage = xhr.responseJSON.error;
                }
                $('.loader').parent().remove();
                $('#chat_chat_history').append('<div class="chat-message chatbot"><p style="background-color: darkred;color:white;">' + errorMessage + '</p></div>');
                $('#chat_chat_history').scrollTop($('#chat_chat_history')[0].scrollHeight);
            }
        });
    }


});
    """
    return HttpResponse(data, content_type='text/javascript')

@login_required
def get_chat_sessions(request):
    chatbot_uuid = request.GET.get('chatbot_uuid')
    chat_sessions = ChatSession.objects.filter(chatbot__uuid=chatbot_uuid, user=request.user).values('uuid', 'name').order_by('created_at')
    return JsonResponse(list(chat_sessions), safe=False)


def export_chatbot(request):
    return render(request, 'ai_tools/export_chatbot.html')

@csrf_exempt
def export_chats(request):
    if request.method == 'POST':
        chatbot_uuid = request.POST.get('chatbot_uuid')
        chat_sessions = ChatSession.objects.filter(chatbot__uuid=chatbot_uuid)
        
        # Create a temporary directory to store text files
        tmp_dir = 'tmp_chats'
        os.makedirs(tmp_dir, exist_ok=True)

        try:
            # Generate text files for each chat session
            for session in chat_sessions:
                file_path = os.path.join(tmp_dir, f"{session.name}.txt")
                with open(file_path, 'w') as file:
                    for entry in session.chat_history:
                        for sender, message in entry.items():
                            file.write(f"{sender}: {message}\n")

            # Create a ZIP file
            zip_filename = 'chat_sessions.zip'
            zip_filepath = os.path.join(tmp_dir, zip_filename)
            with zipfile.ZipFile(zip_filepath, 'w') as zip_file:
                for session in chat_sessions:
                    file_path = os.path.join(tmp_dir, f"{session.name}.txt")
                    zip_file.write(file_path, os.path.basename(file_path))

            # Prepare the response to return the ZIP file for download
            with open(zip_filepath, 'rb') as zip_file:
                response = HttpResponse(zip_file.read(), content_type='application/zip')
                response['Content-Disposition'] = f'attachment; filename={zip_filename}'

        finally:
            # Clean up the temporary directory and files
            shutil.rmtree(tmp_dir)

        return response

    return render(request, 'ai_tools/export_chat.html')

def add_files(request):
    if request.method == 'POST':
        uploaded_at = timezone.now()
        uploaded_at_str = uploaded_at.isoformat()
        uploaded_files = []
        name = request.POST.get('name')
        chatbot_dir = os.path.join("media", "chatbot", name, "data")

        if not name:
            return JsonResponse({'status': 'error', 'message': 'No Chatbot Found.'}, status=400)

        new_chatbot = Chatbot.objects.filter(name=name, creator=request.user).first()

        if not new_chatbot:
            return JsonResponse({'status': 'error', 'message': 'No Chatbot Found.'}, status=400)

        knowledge_base, created = KnowledgeBase.objects.get_or_create(chatbot=new_chatbot)

        file_info = knowledge_base.files or []
        url_info = knowledge_base.urls or []

        if 'file[0]' in request.FILES and request.FILES['file[0]']:
            os.makedirs(chatbot_dir, exist_ok=True)
            for key in request.FILES.keys():
                if key.startswith('file['):
                    uploaded_files.append(request.FILES[key])

            for uploaded_file in uploaded_files:
                file_path = os.path.join(chatbot_dir, uploaded_file.name)
                with open(file_path, 'wb') as f:
                    for chunk in uploaded_file.chunks():
                        f.write(chunk)
                file_info.append({'filename': uploaded_file.name, 'file_path': file_path, 'uploaded_at': uploaded_at_str})
                print('file_uploaded')
                if uploaded_file.name.endswith('.xlsx'):
                    add_empty_row_to_excel(file_path)
                elif uploaded_file.name.endswith('.csv'):
                    add_empty_row_to_csv(file_path)

        url_input = request.POST.getlist('url_input[]', None)
        if url_input and any(url_input):
            for url in url_input:
                if url:
                    file_paths = load_url(url, chatbot_dir)
                    for file_path in file_paths:
                        if is_google_drive_folder_url(url):
                            url_info.append({'url': file_path[0], 'file_path': file_path[1], 'uploaded_at': uploaded_at_str})
                        else:
                            url_info.append({'url': url, 'file_path': file_path, 'uploaded_at': uploaded_at_str})

        url_file = request.FILES.get('url_txt', None)
        if url_file is not None:
            url_list = url_file.read().decode('utf-8').splitlines()
            for url in url_list:
                if url:
                    file_paths = load_url(url, chatbot_dir)
                    for file_path in file_paths:
                        if is_google_drive_folder_url(url):
                            url_info.append({'url': file_path[0], 'file_path': file_path[1], 'uploaded_at': uploaded_at_str})
                        else:
                            url_info.append({'url': url, 'file_path': file_path, 'uploaded_at': uploaded_at_str})

        knowledge_base.files = file_info
        knowledge_base.urls = url_info
        knowledge_base.save()

        return JsonResponse({'status': 'success', 'message': 'Chatbot updated successfully.', 'chatbot_id': new_chatbot.id}, status=201)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)


def get_knowledge_base(request):
    if request.method == "POST":
        uuid = request.POST.get('chatbot')
        chatbot = Chatbot.objects.filter(uuid=uuid).first()
        k_b = KnowledgeBase.objects.filter(chatbot=chatbot).first()
        files = k_b.files
        urls = k_b.urls
        data = {
            'urls': urls,
            'files': files
        }
        print(data)
        return JsonResponse(data)
    return JsonResponse({'error': 'Invalid request'}, status=400)

def delete_knowledge_base_item(request):
    if request.method == 'POST':
        file_path = request.POST.get('file_path')
        url = request.POST.get('url')
        chatbot_uuid = request.POST.get('chatbot_uuid')
        
        try:
            knowledge_base = KnowledgeBase.objects.filter(chatbot__uuid=chatbot_uuid).first()
            
            if file_path:
                knowledge_base.files = [file for file in knowledge_base.files if file['file_path'] != file_path]
                # Also delete the file from the directory
                if os.path.exists(file_path):
                    os.remove(file_path)
            if url:
                knowledge_base.urls = [u for u in knowledge_base.urls if u['url'] != url]
                url_file_path = next((u['file_path'] for u in knowledge_base.urls if u['url'] == url), None)
                # Also delete the scraped file
                if url_file_path and os.path.exists(url_file_path):
                    os.remove(url_file_path)

            knowledge_base.save()
            return JsonResponse({'success': True})
        
        except KnowledgeBase.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Knowledge base not found.'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method.'})


def delete_chat_session(request):
    if request.method == 'POST':
        uuid = request.POST.get('uuid')
        try:
            session = ChatSession.objects.filter(uuid=uuid).first()
            session.delete()
            return JsonResponse({'status': 'success'})
        except ChatSession.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Session not found'}, status=404)
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)

def delete_chatbot(request):
    if request.method == 'POST':
        uuid = request.POST.get('chatbot_uuid')
        chatbot = Chatbot.objects.filter(uuid=uuid).first()
        kb = KnowledgeBase.objects.filter(chatbot=chatbot).first()
        path = kb.folder_path
        parent_path = os.path.dirname(path)
        if os.path.exists(path):
            shutil.rmtree(path)
        chatbot.delete()
        return JsonResponse({'status': 'success'})
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)