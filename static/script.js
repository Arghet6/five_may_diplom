document.addEventListener("DOMContentLoaded", () => {
    let mediaRecorder, audioChunks = [], audioStream, currentChatId = null;
    const recordBtn = document.getElementById("record-btn");
    const stopBtn = document.getElementById("stop-btn");
    const sendBtn = document.getElementById("send-btn");
    const uploadBtn = document.getElementById("upload-btn");
    const userInput = document.getElementById("user-input");
    const chatBox = document.getElementById("chat-box");
    const audioFileInput = document.getElementById("audio-file");
    const newChatBtn = document.getElementById("new-chat-btn");
    const chatList = document.getElementById("chat-list");
    const currentChatTitle = document.getElementById("current-chat-title");

    // Инициализация при загрузке
    initializeChats();

    function initializeChats() {
        const savedChatId = localStorage.getItem('currentChatId');

        fetch("/get_chats")
            .then(response => response.json())
            .then(chats => {
                renderChatList(chats);

                if (savedChatId && chats.some(c => c.chat_id === savedChatId)) {
                    loadChat(savedChatId);
                } else if (chats.length > 0) {
                    loadChat(chats[0].chat_id);
                } else {
                    startNewChat();
                }
            })
            .catch(error => {
                console.error("Ошибка загрузки чатов:", error);
                startNewChat();
            });
    }

    function renderChatList(chats) {
        chatList.innerHTML = '';
        chats.forEach(chat => {
            const chatItem = document.createElement("div");
            chatItem.className = "chat-item";
            chatItem.dataset.chatId = chat.chat_id;
            chatItem.innerHTML = `
                <i class="fas fa-comment"></i>
                <span class="chat-title">${chat.title}</span>
            `;
            chatItem.addEventListener("click", () => {
                loadChat(chat.chat_id);
                localStorage.setItem('currentChatId', chat.chat_id);
            });
            chatList.appendChild(chatItem);
        });
    }

    newChatBtn.addEventListener("click", startNewChat);

    function startNewChat() {
        fetch("/start_chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
        })
        .then(response => response.json())
        .then(data => {
            currentChatId = data.chat_id;
            currentChatTitle.textContent = data.title;
            chatBox.innerHTML = '<div class="message bot-message">Привет! Отправьте текст или голосовое сообщение для анализа эмоций.</div>';
            initializeChats(); // Обновляем список чатов
            localStorage.setItem('currentChatId', data.chat_id);
        })
        .catch(console.error);
    }

    function loadChat(chatId) {
        fetch(`/load_chat/${chatId}`)
        .then(response => response.json())
        .then(data => {
            if (data.error) throw new Error(data.error);

            currentChatId = chatId;
            currentChatTitle.textContent = data.title;
            updateActiveChat(chatId);

            chatBox.innerHTML = "";
            data.messages.forEach(msg => {
                appendMessage(msg.sender, msg.content);
            });

            localStorage.setItem('currentChatId', chatId);
        })
        .catch(error => {
            console.error("Ошибка загрузки чата:", error);
            appendMessage("bot", `❌ Ошибка: ${error.message}`);
        });
    }

    function updateActiveChat(chatId) {
        document.querySelectorAll(".chat-item").forEach(item => {
            item.classList.toggle("active", item.dataset.chatId === chatId);
        });
    }

    sendBtn.addEventListener("click", sendMessage);

    async function sendMessage() {
        const text = userInput.value.trim();
        if (!text || !currentChatId) return;

        appendAndSaveMessage("user", text);
        userInput.value = "";

        try {
            const response = await fetch("/analyze", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ text })
            });
            const data = await response.json();
            appendAndSaveMessage("bot", `Эмоция: ${data.emotion} (${(data.confidence * 100).toFixed(1)}%)`);
        } catch (error) {
            console.error("Ошибка:", error);
            appendAndSaveMessage("bot", `❌ Ошибка: ${error.message}`);
        }
    }

    uploadBtn.addEventListener("click", async () => {
        const file = audioFileInput.files[0];
        if (!file || !currentChatId) return;

        appendAndSaveMessage("user", "Загружен аудиофайл...");

        try {
            const formData = new FormData();
            formData.append("audio", file);

            const response = await fetch("/analyze_audio", {
                method: "POST",
                body: formData
            });
            const data = await response.json();

            // Добавляем распознанный текст в чат
            if (data.transcribed_text) {
                appendAndSaveMessage("user", `Распознанный текст: ${data.transcribed_text}`);
            }

            appendAndSaveMessage("bot", `Эмоция: ${data.emotion} (${(data.confidence * 100).toFixed(1)}%)`);
        } catch (error) {
            console.error("Ошибка:", error);
            appendAndSaveMessage("bot", `❌ Ошибка: ${error.message}`);
        }
    });

    recordBtn.addEventListener("click", startRecording);
    stopBtn.addEventListener("click", stopRecording);

    async function startRecording() {
        try {
            audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(audioStream);
            audioChunks = [];

            mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
            mediaRecorder.onstop = async () => {
                try {
                    const audioBlob = new Blob(audioChunks, { type: "audio/wav" });
                    appendAndSaveMessage("user", "Отправлено голосовое сообщение...");

                    const formData = new FormData();
                    formData.append("audio", audioBlob, "recording.wav");

                    const response = await fetch("/analyze_audio", {
                        method: "POST",
                        body: formData
                    });
                    const data = await response.json();

                    // Добавляем распознанный текст в чат
                    if (data.transcribed_text) {
                        appendAndSaveMessage("user", `Распознанный текст: ${data.transcribed_text}`);
                    }

                    appendAndSaveMessage("bot", `Эмоция: ${data.emotion} (${(data.confidence * 100).toFixed(1)}%)`);
                } catch (error) {
                    console.error("Ошибка:", error);
                    appendAndSaveMessage("bot", `❌ Ошибка: ${error.message}`);
                } finally {
                    audioStream.getTracks().forEach(track => track.stop());
                }
            };

            mediaRecorder.start();
            recordBtn.disabled = true;
            stopBtn.disabled = false;
        } catch (error) {
            console.error("Ошибка записи:", error);
            appendMessage("bot", "❌ Не удалось получить доступ к микрофону");
        }
    }

    function stopRecording() {
        if (mediaRecorder?.state === "recording") {
            mediaRecorder.stop();
            recordBtn.disabled = false;
            stopBtn.disabled = true;
        }
    }

    function appendMessage(sender, text) {
        const message = document.createElement("div");
        message.className = `message ${sender}-message`;
        message.innerHTML = text;
        chatBox.appendChild(message);
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    function appendAndSaveMessage(sender, text) {
        appendMessage(sender, text);

        if (currentChatId) {
            fetch("/save_message", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    chat_id: currentChatId,
                    sender: sender,
                    content: text
                })
            }).catch(console.error);
        }
    }
});