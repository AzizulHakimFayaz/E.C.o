// State Management
let config = {};
let conversations = [];
let activeConversationId = null;
let graphNetwork = null;
let clientTtsEnabled = false;

// Audio System (STT)
let SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;
if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.lang = 'en-US';
    recognition.interimResults = false;
}

// Initialize Application
document.addEventListener("DOMContentLoaded", () => {
    initApp();
    setupEventListeners();
});

async function initApp() {
    await fetchConfig();
    await fetchConversations();
    
    // Default to first conversation if available
    if (conversations.length > 0) {
        selectConversation(conversations[0].id);
    } else {
        createNewConversation();
    }
}

// Fetch Configurations
async function fetchConfig() {
    try {
        const response = await fetch("/api/config");
        config = await response.json();
        populateSettingsForm();
        updateStatusBadges();
    } catch (error) {
        console.error("Error fetching config:", error);
    }
}

// Fetch Conversations
async function fetchConversations() {
    try {
        const response = await fetch("/api/conversations");
        conversations = await response.json();
        renderConversationsList();
    } catch (error) {
        console.error("Error fetching conversations:", error);
    }
}

// Populate settings form
function populateSettingsForm() {
    if (!config) return;
    
    // Active Provider
    const provider = config.active_provider || "ollama";
    if (provider === "ollama") {
        document.getElementById("provider-ollama").checked = true;
        toggleProviderPanels("ollama");
    } else {
        document.getElementById("provider-groq").checked = true;
        toggleProviderPanels("groq");
    }
    
    // Ollama Fields
    document.getElementById("ollama_url").value = config.ollama_url || "http://localhost:11434";
    document.getElementById("ollama_chat_model").value = config.ollama_chat_model || "qwen3:1.7b";
    document.getElementById("ollama_embedding_model").value = config.ollama_embedding_model || "nomic-embed-text";
    
    // Groq Fields
    document.getElementById("groq_api_key").value = config.groq_api_key || "";
    document.getElementById("groq_chat_model").value = config.groq_chat_model || "llama-3.3-70b-versatile";
    
    // Storage Paths & Options
    document.getElementById("sqlite_db_path").value = config.sqlite_db_path || "./eco_memory.db";
    document.getElementById("chroma_db_path").value = config.chroma_db_path || "./chroma_db";
    
    document.getElementById("use_chroma").checked = !!config.use_chroma;
    document.getElementById("use_neo4j").checked = !!config.use_neo4j;
    
    // Neo4j Subpanel
    document.getElementById("neo4j_uri").value = config.neo4j_uri || "bolt://localhost:7687";
    document.getElementById("neo4j_user").value = config.neo4j_user || "neo4j";
    document.getElementById("neo4j_password").value = config.neo4j_password || "password";
    
    toggleNeo4jSubpanel(!!config.use_neo4j);
    
    // Fast Mode
    document.getElementById("fast_mode").checked = !!config.fast_mode;
}

// Update sidebar status badges
function updateStatusBadges() {
    if (!config) return;
    
    // SQLite - always active since it's core
    document.querySelector("#status-sqlite .status-indicator").className = "status-indicator active";
    document.querySelector("#status-sqlite .status-label").textContent = "SQLite: Active";
    
    // Neo4j Status Badge
    const neo4jIndicator = document.querySelector("#status-neo4j .status-indicator");
    const neo4jLabel = document.querySelector("#status-neo4j .status-label");
    if (config.use_neo4j) {
        neo4jIndicator.className = "status-indicator active";
        neo4jLabel.textContent = "Neo4j: Enabled";
    } else {
        neo4jIndicator.className = "status-indicator";
        neo4jLabel.textContent = "Neo4j: Fallback Mode";
    }
    
    // LLM Provider Badge
    const providerBadge = document.getElementById("provider-badge");
    const activeProv = (config.active_provider || "ollama").toUpperCase();
    providerBadge.textContent = activeProv;
    providerBadge.className = "status-label " + (activeProv === "GROQ" ? "text-accent-pink" : "text-accent-cyan");
}

function toggleProviderPanels(provider) {
    const ollamaPanel = document.querySelector(".ollama-settings");
    const groqPanel = document.querySelector(".groq-settings");
    
    if (provider === "ollama") {
        ollamaPanel.classList.add("visible");
        groqPanel.classList.remove("visible");
    } else {
        ollamaPanel.classList.remove("visible");
        groqPanel.classList.add("visible");
    }
}

function toggleNeo4jSubpanel(show) {
    const subpanel = document.getElementById("neo4j-connection-subpanel");
    if (show) {
        subpanel.classList.add("visible");
    } else {
        subpanel.classList.remove("visible");
    }
}

// Render conversations on sidebar
function renderConversationsList() {
    const container = document.getElementById("conversations-list");
    container.innerHTML = "";
    
    if (conversations.length === 0) {
        container.innerHTML = `<div class="loading-placeholder">No conversations</div>`;
        return;
    }
    
    conversations.forEach(convo => {
        const item = document.createElement("div");
        item.className = `convo-item ${convo.id === activeConversationId ? 'active' : ''}`;
        item.setAttribute("data-id", convo.id);
        
        item.innerHTML = `
            <div class="convo-title-container">
                <i class="fa-regular fa-message"></i>
                <span class="convo-title">${escapeHTML(convo.title)}</span>
            </div>
            <button class="convo-delete-btn" title="Delete Conversation">
                <i class="fa-solid fa-trash-can"></i>
            </button>
        `;
        
        // Clicks
        item.querySelector(".convo-title-container").addEventListener("click", () => {
            selectConversation(convo.id);
        });
        
        item.querySelector(".convo-delete-btn").addEventListener("click", (e) => {
            e.stopPropagation();
            deleteConversation(convo.id);
        });
        
        container.appendChild(item);
    });
}

// Select conversation
async function selectConversation(id) {
    activeConversationId = id;
    
    // Highlight sidebar
    document.querySelectorAll(".convo-item").forEach(item => {
        if (parseInt(item.getAttribute("data-id")) === id) {
            item.classList.add("active");
        } else {
            item.classList.remove("active");
        }
    });
    
    // Fetch and render messages
    try {
        const response = await fetch(`/api/conversations/${id}/messages`);
        const messages = await response.json();
        renderMessages(messages);
    } catch (error) {
        console.error("Error loading messages:", error);
    }
}

// Create new conversation
async function createNewConversation() {
    try {
        const response = await fetch("/api/conversations", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title: `Chat Session #${new Date().toLocaleTimeString()}` })
        });
        const newConvo = await response.json();
        conversations.unshift(newConvo);
        renderConversationsList();
        selectConversation(newConvo.id);
    } catch (error) {
        console.error("Error creating conversation:", error);
    }
}

// Delete conversation
async function deleteConversation(id) {
    if (!confirm("Are you sure you want to delete this conversation? This cannot be undone.")) return;
    
    try {
        const response = await fetch(`/api/conversations/${id}`, {
            method: "DELETE"
        });
        
        if (response.ok) {
            conversations = conversations.filter(c => c.id !== id);
            renderConversationsList();
            
            if (activeConversationId === id) {
                if (conversations.length > 0) {
                    selectConversation(conversations[0].id);
                } else {
                    createNewConversation();
                }
            }
        }
    } catch (error) {
        console.error("Error deleting conversation:", error);
    }
}

// Setup Event Listeners
function setupEventListeners() {
    // Sidebar Tabs switching
    document.querySelectorAll(".tab-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const tabId = btn.getAttribute("data-tab");
            
            document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
            document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
            
            btn.classList.add("active");
            document.getElementById(tabId).classList.add("active");
            
            // Trigger load functions specific to each tab
            if (tabId === "graph-tab") {
                loadGraphMemory();
            } else if (tabId === "rag-tab") {
                loadRAGEntries();
            } else if (tabId === "manage-graph-tab") {
                loadGraphManager();
            }
        });
    });
    
    // New Chat Button
    document.getElementById("new-chat-btn").addEventListener("click", createNewConversation);
    
    // Send Message Button & Textarea
    const chatInput = document.getElementById("chat-input");
    document.getElementById("send-btn").addEventListener("click", sendMessage);
    
    chatInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    
    // Auto-grow input text area
    chatInput.addEventListener("input", function() {
        this.style.height = "auto";
        this.style.height = (this.scrollHeight) + "px";
    });
    
    // Voice Dictation (STT) Trigger
    const micBtn = document.getElementById("mic-btn");
    if (micBtn && recognition) {
        micBtn.addEventListener("click", () => {
            startSpeechRecognition();
        });
    } else if (micBtn) {
        micBtn.style.display = "none"; // Hide if not supported
    }
    
    // Cancel Dictation
    document.getElementById("cancel-dictation-btn").addEventListener("click", () => {
        if (recognition) recognition.stop();
        document.getElementById("dictation-overlay").classList.remove("visible");
    });
    
    // Voice Mode Output Toggle (TTS)
    const voiceModeToggle = document.getElementById("voice-mode-toggle");
    voiceModeToggle.addEventListener("click", () => {
        clientTtsEnabled = !clientTtsEnabled;
        const icon = voiceModeToggle.querySelector("i");
        if (clientTtsEnabled) {
            icon.className = "fa-solid fa-volume-high active-tts";
            voiceModeToggle.title = "Disable Client Voice Output (TTS)";
            speakText("Voice response enabled.");
        } else {
            icon.className = "fa-solid fa-volume-xmark text-muted";
            voiceModeToggle.title = "Enable Client Voice Output (TTS)";
            window.speechSynthesis.cancel();
        }
    });
    
    // Sync Button
    document.getElementById("system-reload-btn").addEventListener("click", async () => {
        const icon = document.querySelector("#system-reload-btn i");
        icon.className = "fa-solid fa-arrows-rotate fa-spin";
        await fetchConfig();
        await fetchConversations();
        if (activeConversationId) {
            await selectConversation(activeConversationId);
        }
        icon.className = "fa-solid fa-arrows-rotate";
    });
    
    // Settings Radio Switches
    document.querySelectorAll('[name="active_provider"]').forEach(el => {
        el.addEventListener("change", (e) => {
            toggleProviderPanels(e.target.value);
        });
    });
    
    // Listen for manual settings provider radios
    document.getElementById("provider-ollama").addEventListener("change", () => toggleProviderPanels("ollama"));
    document.getElementById("provider-groq").addEventListener("change", () => toggleProviderPanels("groq"));
    
    // Listen for manual database checkboxes
    document.getElementById("use_neo4j").addEventListener("change", (e) => {
        toggleNeo4jSubpanel(e.target.checked);
    });
    
    // Settings Form Submit
    document.getElementById("settings-form").addEventListener("submit", saveSettings);
    
    // Create Node Form Submit
    document.getElementById("create-node-form").addEventListener("submit", addGraphNode);
    
    // Create Edge Form Submit
    document.getElementById("create-edge-form").addEventListener("submit", addGraphEdge);
    
    // RAG Live Search filter
    document.getElementById("rag-search-input").addEventListener("input", (e) => {
        filterRagTable(e.target.value);
    });
}

// Set Prompt utility (used by quick start cards)
window.setPrompt = function(text) {
    const input = document.getElementById("chat-input");
    input.value = text;
    input.dispatchEvent(new Event('input')); // trigger auto grow resize
    input.focus();
};

// Send Chat Message
async function sendMessage() {
    const input = document.getElementById("chat-input");
    const text = input.value.trim();
    if (!text || !activeConversationId) return;
    
    // Reset input height & value
    input.value = "";
    input.style.height = "auto";
    
    // 1. Append User Message to UI
    appendMessage("user", text);
    hideEmptyState();
    
    // 2. Add loading bot bubble
    const loadingBubbleId = appendMessage("bot", `<div class="loading-placeholder"><i class="fa-solid fa-circle-notch fa-spin"></i> E.C.o is reasoning...</div>`, true);
    
    try {
        // Stop any running speech synthesis
        window.speechSynthesis.cancel();
        
        const response = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                message: text,
                conversation_id: activeConversationId,
                user_name: "Shahriar"
            })
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || "Error from server");
        }
        
        const data = await response.json();
        
        // Remove loading bubble
        document.getElementById(loadingBubbleId).remove();
        
        // 3. Render complete assistant response + thoughts trace
        appendBotResponse(data);
        
        // Speak response if enabled
        if (clientTtsEnabled && data.response) {
            speakText(cleanSpeechText(data.response));
        }
        
    } catch (error) {
        console.error("Chat error:", error);
        document.getElementById(loadingBubbleId).innerHTML = `<span style="color: var(--accent-pink);"><i class="fa-solid fa-circle-exclamation"></i> Error: ${escapeHTML(error.message)}</span>`;
    }
}

// Format bot messages with Markdown & collapsible thoughts
function appendBotResponse(agentResult) {
    const viewport = document.getElementById("chat-bubbles");
    
    // Create wrapper row
    const row = document.createElement("div");
    row.className = "message-row bot";
    
    const bubble = document.createElement("div");
    bubble.className = "message-bubble";
    
    // Extract intermediate thought loop details
    const messages = agentResult.messages || [];
    // Find index of the user's latest query message
    let lastUserIndex = -1;
    for (let i = messages.length - 1; i >= 0; i--) {
        if (messages[i].role === "user") {
            lastUserIndex = i;
            break;
        }
    }
    
    // Extract thoughts and tool calls in between user input and final answer
    let thoughtsHtml = "";
    if (lastUserIndex !== -1 && messages.length > lastUserIndex + 2) {
        let thoughtsText = "";
        for (let i = lastUserIndex + 1; i < messages.length - 1; i++) {
            const m = messages[i];
            if (m.role === "assistant" && m.content) {
                // Formatting thoughts
                thoughtsText += `[AGENT THOUGHTS]\n${m.content}\n\n`;
            } else if (m.role === "tool") {
                // Formatting tool outputs
                thoughtsText += `[TOOL CALL: ${m.name}]\nArguments/Output:\n${m.content}\n\n`;
            }
        }
        
        if (thoughtsText.trim()) {
            thoughtsHtml = `
                <div class="thoughts-container">
                    <div class="thoughts-header" onclick="toggleThoughts(this)">
                        <span><i class="fa-solid fa-microchip"></i> Agent Reasoning Chain</span>
                        <i class="fa-solid fa-chevron-down thoughts-icon"></i>
                    </div>
                    <div class="thoughts-content">${escapeHTML(thoughtsText.trim())}</div>
                </div>
            `;
        }
    }
    
    // Render markdown response
    const formattedMarkdown = marked.parse(agentResult.response || "");
    
    bubble.innerHTML = `
        ${thoughtsHtml}
        <div class="markdown-content">${formattedMarkdown}</div>
    `;
    
    row.appendChild(bubble);
    viewport.appendChild(row);
    
    // Trigger Prism highlight code blocks
    Prism.highlightAllUnder(bubble);
    
    // Scroll view
    scrollToBottom();
}

// Toggle intermediate thoughts accordion
window.toggleThoughts = function(headerElement) {
    const container = headerElement.parentElement;
    container.classList.toggle("open");
    const icon = headerElement.querySelector(".thoughts-icon");
    if (container.classList.contains("open")) {
        icon.className = "fa-solid fa-chevron-up thoughts-icon";
    } else {
        icon.className = "fa-solid fa-chevron-down thoughts-icon";
    }
};

// Render message array from server
function renderMessages(messages) {
    const viewport = document.getElementById("chat-bubbles");
    viewport.innerHTML = "";
    
    if (messages.length === 0) {
        showEmptyState();
        return;
    }
    
    hideEmptyState();
    
    // Helper to group turns
    let i = 0;
    while (i < messages.length) {
        const msg = messages[i];
        
        if (msg.role === "user") {
            appendMessage("user", msg.content);
            i++;
        } else {
            // Find intermediate thoughts for this assistant reply block
            let botResponse = msg.content;
            let thoughtsText = "";
            let nextIndex = i + 1;
            
            // Collect any concurrent assistant/tool logs until the next user message
            while (nextIndex < messages.length && messages[nextIndex].role !== "user") {
                const subMsg = messages[nextIndex];
                if (subMsg.role === "assistant") {
                    // Update final bot answer or accumulate logs
                    if (subMsg.content.includes("Thinking:")) {
                        thoughtsText += `[AGENT THOUGHTS]\n${subMsg.content}\n\n`;
                    } else {
                        botResponse = subMsg.content;
                    }
                } else if (subMsg.role === "tool") {
                    thoughtsText += `[TOOL CALL: ${subMsg.name}]\nOutput:\n${subMsg.content}\n\n`;
                }
                nextIndex++;
            }
            
            // Draw bot bubble
            const row = document.createElement("div");
            row.className = "message-row bot";
            const bubble = document.createElement("div");
            bubble.className = "message-bubble";
            
            let thoughtsHtml = "";
            if (thoughtsText.trim()) {
                thoughtsHtml = `
                    <div class="thoughts-container">
                        <div class="thoughts-header" onclick="toggleThoughts(this)">
                            <span><i class="fa-solid fa-microchip"></i> Agent Reasoning Chain</span>
                            <i class="fa-solid fa-chevron-down thoughts-icon"></i>
                        </div>
                        <div class="thoughts-content">${escapeHTML(thoughtsText.trim())}</div>
                    </div>
                `;
            }
            
            const formattedMarkdown = marked.parse(botResponse || "");
            bubble.innerHTML = `
                ${thoughtsHtml}
                <div class="markdown-content">${formattedMarkdown}</div>
            `;
            
            row.appendChild(bubble);
            viewport.appendChild(row);
            
            Prism.highlightAllUnder(bubble);
            i = nextIndex;
        }
    }
    
    scrollToBottom();
}

// Append generic single message bubble
function appendMessage(role, content, returnId = false) {
    const viewport = document.getElementById("chat-bubbles");
    
    const row = document.createElement("div");
    const id = "bubble-" + Math.random().toString(36).substring(2, 9);
    row.className = `message-row ${role}`;
    row.id = id;
    
    const bubble = document.createElement("div");
    bubble.className = "message-bubble";
    
    if (role === "user") {
        bubble.textContent = content;
    } else {
        bubble.innerHTML = content; // allows HTML for spinner
    }
    
    row.appendChild(bubble);
    viewport.appendChild(row);
    scrollToBottom();
    
    if (returnId) return id;
}

// Utilities
function scrollToBottom() {
    const viewport = document.getElementById("messages-viewport");
    viewport.scrollTop = viewport.scrollHeight;
}

function showEmptyState() {
    const el = document.getElementById("chat-empty-state");
    if (el) el.style.display = "flex";
}

function hideEmptyState() {
    const el = document.getElementById("chat-empty-state");
    if (el) el.style.display = "none";
}

// Client TTS Speech Output
function speakText(text) {
    if (!SpeechSynthesis || !clientTtsEnabled) return;
    
    // Cancel currently speaking voices
    window.speechSynthesis.cancel();
    
    const utterance = new SpeechSynthesisUtterance(text);
    // Find a good voice if available
    const voices = window.speechSynthesis.getVoices();
    const naturalVoice = voices.find(v => v.name.includes("Natural") || v.name.includes("Google"));
    if (naturalVoice) utterance.voice = naturalVoice;
    
    utterance.rate = 1.0;
    utterance.pitch = 1.0;
    window.speechSynthesis.speak(utterance);
}

// Clean markdown characters from synthesis texts
function cleanSpeechText(markdown) {
    return markdown
        .replace(/`{3}[\s\S]*?`{3}/g, '[code block omitted]') // strip code blocks
        .replace(/`.*?`/g, '') // strip inline code
        .replace(/[*#_\[\]\(\)]/g, '') // strip markdown symbols
        .replace(/<[^>]*>/g, ''); // strip HTML tags
}

// Browser STT Speech recognition dictation
function startSpeechRecognition() {
    if (!recognition) return;
    
    const overlay = document.getElementById("dictation-overlay");
    const status = document.getElementById("dictation-status");
    const micBtn = document.getElementById("mic-btn");
    
    overlay.classList.add("visible");
    micBtn.classList.add("listening");
    status.textContent = "Listening...";
    
    recognition.start();
    
    recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        status.textContent = `Recognized: "${transcript}"`;
        
        setTimeout(() => {
            const input = document.getElementById("chat-input");
            input.value = transcript;
            input.dispatchEvent(new Event('input')); // auto grow height
            overlay.classList.remove("visible");
            micBtn.classList.remove("listening");
            
            // Auto submit
            sendMessage();
        }, 1000);
    };
    
    recognition.onerror = (event) => {
        console.error("Speech Recognition Error:", event.error);
        status.textContent = `Error: ${event.error}`;
        setTimeout(() => {
            overlay.classList.remove("visible");
            micBtn.classList.remove("listening");
        }, 2000);
    };
    
    recognition.onspeechend = () => {
        status.textContent = "Analyzing speech...";
        recognition.stop();
    };
}

// Settings Saving
async function saveSettings(e) {
    e.preventDefault();
    
    const payload = {
        active_provider: document.querySelector('input[name="active_provider"]:checked').value,
        ollama_url: document.getElementById("ollama_url").value,
        ollama_chat_model: document.getElementById("ollama_chat_model").value,
        ollama_embedding_model: document.getElementById("ollama_embedding_model").value,
        groq_api_key: document.getElementById("groq_api_key").value,
        groq_chat_model: document.getElementById("groq_chat_model").value,
        sqlite_db_path: document.getElementById("sqlite_db_path").value,
        chroma_db_path: document.getElementById("chroma_db_path").value,
        use_chroma: document.getElementById("use_chroma").checked,
        use_neo4j: document.getElementById("use_neo4j").checked,
        neo4j_uri: document.getElementById("neo4j_uri").value,
        neo4j_user: document.getElementById("neo4j_user").value,
        neo4j_password: document.getElementById("neo4j_password").value,
        fast_mode: document.getElementById("fast_mode").checked
    };
    
    const saveBtn = document.getElementById("save-settings-btn");
    saveBtn.innerHTML = `<i class="fa-solid fa-circle-notch fa-spin"></i> Saving...`;
    
    try {
        const response = await fetch("/api/config", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        
        if (response.ok) {
            alert("Configurations saved and system settings updated successfully!");
            await fetchConfig();
        } else {
            const err = await response.json();
            alert(`Error: ${err.detail || "Could not save configurations"}`);
        }
    } catch (error) {
        alert(`Error saving configurations: ${error.message}`);
    } finally {
        saveBtn.innerHTML = `<i class="fa-solid fa-floppy-disk"></i> Save Configurations`;
    }
}

// --- Graph Visualization Tab ---
async function loadGraphMemory() {
    const statsBadge = document.getElementById("graph-stats-badge");
    const container = document.getElementById("graph-network-container");
    container.innerHTML = `<div class="loading-placeholder" style="height:100%"><i class="fa-solid fa-circle-notch fa-spin"></i> Mapping memory nodes...</div>`;
    
    try {
        const response = await fetch("/api/graph");
        const graphData = await response.json();
        
        const nodes = graphData.nodes || [];
        const edges = graphData.edges || [];
        
        statsBadge.textContent = `${nodes.length} Nodes | ${edges.length} Relationships`;
        
        if (nodes.length === 0) {
            container.innerHTML = `
                <div class="empty-inspector" style="height:100%">
                    <i class="fa-solid fa-diagram-project"></i>
                    <p>No nodes found in memory. Chat with E.C.o to automatically build knowledge graphs or add nodes manually!</p>
                </div>
            `;
            return;
        }
        
        // Define type styles
        const typeStyles = {
            User: { color: "#9d4edd", border: "#7b2cbf", shape: "dot", size: 25 },
            Project: { color: "#00f0ff", border: "#00b4d8", shape: "dot", size: 22 },
            Preference: { color: "#ff7f00", border: "#e07a5f", shape: "dot", size: 20 },
            Style: { color: "#39ff14", border: "#2ebd14", shape: "dot", size: 20 },
            Topic: { color: "#ff007f", border: "#cc0066", shape: "dot", size: 20 },
            Concept: { color: "#ffff00", border: "#cccc00", shape: "dot", size: 18 },
            Source: { color: "#00ffff", border: "#00cccc", shape: "dot", size: 18 }
        };
        
        // Map nodes for vis.js
        const visNodes = nodes.map(node => {
            const style = typeStyles[node.type] || { color: "#9ea2b0", border: "#5e6273", shape: "dot", size: 18 };
            return {
                id: node.id,
                label: node.name,
                title: `${node.name} (${node.type})`,
                color: {
                    background: style.color,
                    border: style.border,
                    highlight: { background: "#fff", border: style.border }
                },
                shape: style.shape,
                size: style.size,
                shadow: {
                    enabled: true,
                    color: style.color,
                    size: 8,
                    x: 0, y: 0
                },
                font: { color: "#ffffff", face: "Outfit", size: 14 },
                type: node.type,
                metadata: node.metadata
            };
        });
        
        // Map edges for vis.js
        const visEdges = edges.map(edge => {
            return {
                from: edge.source_id,
                to: edge.target_id,
                label: edge.type,
                arrows: "to",
                color: { color: "rgba(255, 255, 255, 0.15)", highlight: "#00f0ff" },
                font: { color: "#9ea2b0", face: "Outfit", size: 10, strokeWidth: 0, align: "horizontal" }
            };
        });
        
        // Construct vis Network
        container.innerHTML = "";
        const data = { nodes: new vis.DataSet(visNodes), edges: new vis.DataSet(visEdges) };
        const options = {
            physics: {
                solver: "forceAtlas2Based",
                forceAtlas2Based: {
                    gravitationalConstant: -50,
                    centralGravity: 0.01,
                    springLength: 100,
                    springConstant: 0.08
                }
            },
            interaction: { hover: true, tooltipDelay: 200 }
        };
        
        graphNetwork = new vis.Network(container, data, options);
        
        // Bind selection event
        graphNetwork.on("selectNode", (params) => {
            const nodeId = params.nodes[0];
            const clickedNode = visNodes.find(n => n.id === nodeId);
            if (clickedNode) {
                renderNodeInspection(clickedNode);
            }
        });
        
        graphNetwork.on("deselectNode", () => {
            resetNodeInspection();
        });
        
    } catch (error) {
        console.error("Error loading graph network:", error);
        container.innerHTML = `<div class="empty-inspector" style="height:100%; color: var(--accent-pink);"><i class="fa-solid fa-circle-exclamation"></i> Error loading graph: ${error.message}</div>`;
    }
}

// Node Inspection Right Sidebar View
function renderNodeInspection(node) {
    const body = document.getElementById("inspector-content");
    
    let metaHtml = "";
    const meta = node.metadata || {};
    if (Object.keys(meta).length > 0) {
        metaHtml = Object.entries(meta).map(([k, v]) => `
            <div class="meta-item">
                <span class="meta-key">${escapeHTML(k)}:</span>
                <span class="meta-value">${escapeHTML(typeof v === 'object' ? JSON.stringify(v) : String(v))}</span>
            </div>
        `).join("");
    } else {
        metaHtml = `<div class="text-muted" style="font-size:12px;">No properties configured.</div>`;
    }
    
    body.innerHTML = `
        <div class="node-card-detail">
            <span class="detail-type-badge badge-${node.type}">${node.type}</span>
            <div>
                <h2 class="detail-name">${escapeHTML(node.label)}</h2>
                <span class="detail-id">ID: ${escapeHTML(node.id)}</span>
            </div>
            
            <div class="detail-section">
                <span class="detail-section-title">Properties</span>
                ${metaHtml}
            </div>
            
            <div class="detail-section">
                <span class="detail-section-title">Actions</span>
                <div class="inspector-actions">
                    <button class="delete-node-btn" onclick="deleteNodeFromGraph('${node.id}')">
                        <i class="fa-solid fa-trash-can"></i> Delete Entity
                    </button>
                </div>
            </div>
        </div>
    `;
}

function resetNodeInspection() {
    const body = document.getElementById("inspector-content");
    body.innerHTML = `
        <div class="empty-inspector">
            <i class="fa-solid fa-hand-pointer"></i>
            <p>Select a node in the graph to inspect properties, update values, or delete connections.</p>
        </div>
    `;
}

// Delete Node API call
window.deleteNodeFromGraph = async function(nodeId) {
    if (!confirm(`Are you sure you want to delete entity "${nodeId}" and all its connected links from memory?`)) return;
    
    try {
        const response = await fetch(`/api/graph/nodes/${encodeURIComponent(nodeId)}`, {
            method: "DELETE"
        });
        
        if (response.ok) {
            resetNodeInspection();
            loadGraphMemory(); // Reload canvas
        } else {
            const err = await response.json();
            alert(`Error deleting node: ${err.detail || "Could not complete operation"}`);
        }
    } catch (error) {
        alert(`Error deleting node: ${error.message}`);
    }
};

// --- RAG Explorer ---
let allRagEntries = [];

async function loadRAGEntries() {
    const tbody = document.getElementById("rag-table-body");
    tbody.innerHTML = `<tr><td colspan="5" class="loading-placeholder"><i class="fa-solid fa-circle-notch fa-spin"></i> Loading index...</td></tr>`;
    
    try {
        const response = await fetch("/api/rag");
        allRagEntries = await response.json();
        renderRagTable(allRagEntries);
    } catch (error) {
        console.error("Error loading RAG index:", error);
        tbody.innerHTML = `<tr><td colspan="5" style="color: var(--accent-pink); text-align:center;"><i class="fa-solid fa-circle-exclamation"></i> Load error: ${error.message}</td></tr>`;
    }
}

function renderRagTable(entries) {
    const tbody = document.getElementById("rag-table-body");
    tbody.innerHTML = "";
    
    if (entries.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-muted" style="text-align:center; padding: 30px 0;">No document embeddings found in local database.</td></tr>`;
        return;
    }
    
    entries.forEach(entry => {
        const row = document.createElement("tr");
        row.innerHTML = `
            <td>${entry.id}</td>
            <td style="font-weight:600;">${escapeHTML(entry.title)}</td>
            <td class="text-secondary" style="max-width:320px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${escapeHTML(entry.content)}">
                ${escapeHTML(entry.content)}
            </td>
            <td><span class="badge ${entry.type === 'document' ? 'badge-Source' : 'badge-Project'}">${entry.type}</span></td>
            <td class="text-muted" style="font-size:12px;">${new Date(entry.created_at).toLocaleString()}</td>
        `;
        tbody.appendChild(row);
    });
}

function filterRagTable(query) {
    const term = query.toLowerCase().trim();
    if (!term) {
        renderRagTable(allRagEntries);
        return;
    }
    
    const filtered = allRagEntries.filter(entry => 
        (entry.title || "").toLowerCase().includes(term) || 
        (entry.content || "").toLowerCase().includes(term) ||
        (entry.type || "").toLowerCase().includes(term)
    );
    renderRagTable(filtered);
}

// --- Memory Manager Tab ---
async function loadGraphManager() {
    await loadDirectories();
}

async function loadDirectories() {
    const nodesBody = document.getElementById("directory-nodes-body");
    const edgesBody = document.getElementById("directory-edges-body");
    const datalist = document.getElementById("node-ids-datalist");
    
    nodesBody.innerHTML = `<tr><td colspan="5" class="loading-placeholder"><i class="fa-solid fa-circle-notch fa-spin"></i></td></tr>`;
    edgesBody.innerHTML = `<tr><td colspan="4" class="loading-placeholder"><i class="fa-solid fa-circle-notch fa-spin"></i></td></tr>`;
    
    try {
        const response = await fetch("/api/graph");
        const graph = await response.json();
        
        const nodes = graph.nodes || [];
        const edges = graph.edges || [];
        
        // Nodes Directory
        nodesBody.innerHTML = "";
        datalist.innerHTML = "";
        
        if (nodes.length === 0) {
            nodesBody.innerHTML = `<tr><td colspan="5" class="text-muted" style="text-align:center;">No entities stored.</td></tr>`;
        } else {
            nodes.forEach(node => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td style="font-family:var(--font-mono); font-size:12px;">${escapeHTML(node.id)}</td>
                    <td style="font-weight:600;">${escapeHTML(node.name)}</td>
                    <td><span class="badge badge-${node.type}">${node.type}</span></td>
                    <td style="font-size:12px; font-family:var(--font-mono); color:var(--accent-cyan);">${escapeHTML(JSON.stringify(node.metadata))}</td>
                    <td>
                        <button class="table-btn-delete" onclick="deleteNodeFromGraph('${node.id}'); loadDirectories();">
                            Delete
                        </button>
                    </td>
                `;
                nodesBody.appendChild(tr);
                
                // Populate Autocomplete
                const option = document.createElement("option");
                option.value = node.id;
                datalist.appendChild(option);
            });
        }
        
        // Relationships Directory
        edgesBody.innerHTML = "";
        if (edges.length === 0) {
            edgesBody.innerHTML = `<tr><td colspan="4" class="text-muted" style="text-align:center;">No links stored.</td></tr>`;
        } else {
            edges.forEach(edge => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td style="font-family:var(--font-mono); font-size:12px;">${escapeHTML(edge.source_id)}</td>
                    <td><span class="badge" style="background:rgba(255,255,255,0.04); border:1px solid var(--border-color);">${edge.type}</span></td>
                    <td style="font-family:var(--font-mono); font-size:12px;">${escapeHTML(edge.target_id)}</td>
                    <td>
                        <button class="table-btn-delete" onclick="deleteEdge('${edge.source_id}', '${edge.target_id}', '${edge.type}')">
                            Unlink
                        </button>
                    </td>
                `;
                edgesBody.appendChild(tr);
            });
        }
        
    } catch (error) {
        console.error("Error loading directories:", error);
    }
}

// Add Node submit handler
async function addGraphNode(e) {
    e.preventDefault();
    
    const id = document.getElementById("new-node-id").value.trim();
    const name = document.getElementById("new-node-name").value.trim();
    const type = document.getElementById("new-node-type").value;
    const metaStr = document.getElementById("new-node-metadata").value.trim();
    
    let metadata = {};
    if (metaStr) {
        try {
            metadata = json.loads(metaStr); // Wait: JS uses JSON.parse!
        } catch(err) {
            try {
                metadata = JSON.parse(metaStr);
            } catch(e2) {
                alert("Invalid JSON format in Metadata field.");
                return;
            }
        }
    }
    
    try {
        const response = await fetch("/api/graph/nodes", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id, name, type, metadata })
        });
        
        if (response.ok) {
            document.getElementById("new-node-id").value = "";
            document.getElementById("new-node-name").value = "";
            document.getElementById("new-node-metadata").value = "";
            loadDirectories();
        } else {
            const err = await response.json();
            alert(`Error: ${err.detail}`);
        }
    } catch (error) {
        alert(`Error adding node: ${error.message}`);
    }
}

// Add Relationship submit handler
async function addGraphEdge(e) {
    e.preventDefault();
    
    const source_id = document.getElementById("new-edge-source").value.trim();
    const target_id = document.getElementById("new-edge-target").value.trim();
    const type = document.getElementById("new-edge-type").value;
    
    try {
        const response = await fetch("/api/graph/edges", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ source_id, target_id, type })
        });
        
        if (response.ok) {
            document.getElementById("new-edge-source").value = "";
            document.getElementById("new-edge-target").value = "";
            loadDirectories();
        } else {
            const err = await response.json();
            alert(`Error: ${err.detail}`);
        }
    } catch (error) {
        alert(`Error: ${error.message}`);
    }
}

// Delete Relationship call
async function deleteEdge(sourceId, targetId, edgeType) {
    if (!confirm(`Are you sure you want to delete relationship: ${sourceId} -[${edgeType}]-> ${targetId}?`)) return;
    
    try {
        const response = await fetch(`/api/graph/edges?source_id=${encodeURIComponent(sourceId)}&target_id=${encodeURIComponent(targetId)}&edge_type=${encodeURIComponent(edgeType)}`, {
            method: "DELETE"
        });
        
        if (response.ok) {
            loadDirectories();
        } else {
            const err = await response.json();
            alert(`Error deleting link: ${err.detail}`);
        }
    } catch (error) {
        alert(`Error: ${error.message}`);
    }
}

// HTML Escaping Utility
function escapeHTML(str) {
    if (!str) return "";
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
