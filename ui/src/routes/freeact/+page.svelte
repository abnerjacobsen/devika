<script>
  import { onDestroy, onMount, tick } from "svelte";
  import { toast } from "svelte-sonner";

  import MessageContainer from "$lib/components/MessageContainer.svelte";
  import MessageInput from "$lib/components/MessageInput.svelte";
  import * as Resizable from "$lib/components/ui/resizable/index.js";

  /* FreeAct-specific widgets (copies of the originals) */
  import FreeActBrowserWidget from "$lib/components/FreeActBrowserWidget.svelte";
  import FreeActTerminalWidget from "$lib/components/FreeActTerminalWidget.svelte";
  import { serverStatus } from "$lib/store";
  import { socketListener, emitMessage } from "$lib/sockets";
  import { checkServerStatus, fetchInitialData } from "$lib/api";
  import { socket, API_BASE_URL } from "$lib/api";

  /* ------------------------------------------------------------------ */
  /* Markdown rendering helpers                                          */
  /* ------------------------------------------------------------------ */
  import DOMPurify from "dompurify";
  import { marked } from "marked";

  // Configure marked to render line breaks as <br>
  marked.setOptions({
    breaks: true, // Convert line breaks to <br>
  });

  /**
   * Render markdown to HTML using the 'marked' library.
   * Sanitizes with DOMPurify to prevent XSS.
   */
  function renderMarkdown(md = "") {
    if (!md) return "";
    try {
      const html = marked.parse(md);
      return DOMPurify.sanitize(html, { USE_PROFILES: { html: true } });
    } catch (err) {
      console.error("[FreeAct] Error rendering markdown:", err);
      return md; // Fallback to plain text if markdown parsing fails
    }
  }

  // FreeAct specific stores
  import { writable } from "svelte/store";
  // Remover afterUpdate que estava forçando scroll sempre
  const freeactMessages = writable([]);
  const freeactStatus = writable("idle"); // idle, active, error
  const isSending = writable(false);

  let selectedProject = "";
  let messageInput = "";
  let messagesContainer; // Referência ao container de mensagens para scroll

  /* ------------------------------------------------------------------ */
  /* Agent state initialization with safe defaults                       */
  /* ------------------------------------------------------------------ */
  import { agentState } from "$lib/store";
  let isComponentInitialized = false;

  // Get the selected project from localStorage
  onMount(() => {
    console.log("[FreeAct] Component mounting, initializing...");
    
    // Global error handler for uncaught JavaScript errors
    window.onerror = function (message, source, lineno, colno, error) {
      console.error("Global JavaScript Error:", { message, source, lineno, colno, error });
      toast.error(`An unexpected error occurred: ${message}`);
      return true; // Prevent default browser error handling
    };

    // Global handler for unhandled promise rejections
    window.onunhandledrejection = function (event) {
      console.error("Unhandled Promise Rejection:", event.reason);
      toast.error(`An unhandled promise rejection occurred: ${event.reason}`);
      return true; // Prevent default browser error handling
    };

    // Add listener for socket connection events
    socket.on('connect', () => {
      console.log(`[FreeAct] Socket connected with ID: ${socket.id}`);
    });

    socket.on('disconnect', () => {
      console.log('[FreeAct] Socket disconnected');
    });

    socket.on('connect_error', (error) => {
      console.error('[FreeAct] Socket connection error:', error);
    });

    const load = async () => {
      try {
        console.log("[FreeAct] Starting load() function...");
        
        if (!(await checkServerStatus())) {
          console.error("[FreeAct] Server status check failed");
          toast.error("Failed to connect to server");
          return;
        }
        
        console.log("[FreeAct] Server status check passed");
        serverStatus.set(true);
        await fetchInitialData();
        
        // Connect socket if not already connected
        console.log(`[FreeAct] Socket status before connect: connected=${socket.connected}, id=${socket.id}`);
        if (!socket.connected) {
          console.log("[FreeAct] Socket not connected, connecting now...");
          socket.connect();
        }
        console.log(`[FreeAct] Socket status after connect: connected=${socket.connected}, id=${socket.id}`);
        
        // Get selected project from localStorage
        selectedProject = localStorage.getItem("selectedProject") || "";
        console.log(`[FreeAct] Selected project: "${selectedProject}"`);
        if (!selectedProject) {
          console.warn("[FreeAct] No project selected");
          toast.error("Please select a project first");
        }

        /* ------------------------------------------------------------------ */
        /* Register socket listeners **before** touching agentState           */
        /* ------------------------------------------------------------------ */
        console.log("[FreeAct] Registering socket listeners...");

        socketListener("freeact_status", handleFreeActStatus);
        socketListener("freeact_error", handleFreeActError);
        socketListener("freeact_input_request", handleFreeActInputRequest);
        socketListener("freeact_usage", handleFreeActUsage);
        socketListener("freeact_model_response", handleFreeActModelResponse);
        socketListener("freeact_code_action", handleCodeAction);
        socketListener("freeact_execution_result", handleExecutionResult);
        console.log("[FreeAct] All socket listeners registered");

        /* --------- DEBUG: log every incoming event once listeners set ------ */
        const originalOnevent = socket.onevent;
        socket.onevent = function (packet) {
          console.log(`[FreeAct] Socket event received: ${packet.data?.[0]}`);
          originalOnevent.call(this, packet);
        };

        // Initialize agentState with a safe default structure AFTER server check
        // This prevents "Function called outside component initialization"
        await tick(); // Ensure DOM is ready
        isComponentInitialized = true;
        console.log("[FreeAct] Initializing agentState with safe defaults");
        try {
          agentState.update((current) => ({
            ...current,
            browser_session:
              current?.browser_session ?? { url: null, screenshot: null },
            terminal_session:
              current?.terminal_session ?? {
                command: null,
                output: null,
                title: "FreeAct Terminal",
              },
          }));
        } catch (err) {
          console.error("[FreeAct] agentState.update error:", err);
        }
        
        // Add direct socket listeners for debugging
        socket.on('freeact_model_response', (data) => {
          console.log('[FreeAct] DIRECT SOCKET: Received freeact_model_response event:', data);
        });
        
        socket.on('freeact_code_action', (data) => {
          console.log('[FreeAct] DIRECT SOCKET: Received freeact_code_action event:', data);
        });
        
        socket.on('freeact_execution_result', (data) => {
          console.log('[FreeAct] DIRECT SOCKET: Received freeact_execution_result event:', data);
        });
        
        // Log all incoming socket events for debugging
        const originalOnevent = socket.onevent;
        socket.onevent = function(packet) {
          const eventName = packet.data[0];
          console.log(`[FreeAct] Socket event received: ${eventName}`);
          originalOnevent.call(this, packet);
        };
        
      } catch (error) {
        console.error("Error during FreeAct page initialization:", error);
        toast.error(`Error initializing FreeAct page: ${error.message}`);
      }
    };

    load();
  });

  onDestroy(() => {
    console.log("[FreeAct] Component destroying, cleaning up listeners...");
    // Clean up socket listeners
    if (socket?.connected) {
      try {
        console.log("[FreeAct] Removing socket listeners...");
        socket.off("freeact_model_response");
        socket.off("freeact_code_action");
        socket.off("freeact_execution_result");
        socket.off("freeact_status");
        socket.off("freeact_error");
        socket.off("freeact_input_request");
        socket.off("freeact_usage");
        socket.off("connect");
        socket.off("disconnect");
        socket.off("connect_error");
        console.log("[FreeAct] Socket listeners removed");
      } catch (err) {
        console.error("[FreeAct] Error cleaning up socket listeners:", err);
      }
    } else {
      console.log("[FreeAct] Socket not connected, no listeners to remove");
    }
    isComponentInitialized = false;
  });

  /* ------------------------------------------------------------------ */
  /* Terminal output helper (uses agentState so widget auto-updates)     */
  /* ------------------------------------------------------------------ */
  async function appendToTerminal(text, type = "Output") {
    // DEBUG: track every update to terminal widget
    console.debug("[FreeAct] appendToTerminal", { type, preview: (text ?? "").slice(0, 120) });
    try {
      if (!isComponentInitialized) {
        console.warn("[FreeAct] Cannot update terminal - component not initialized");
        return;
      }
      
      await tick(); // Ensure DOM is ready before updating
      
      agentState.update((state) => {
        const term = state?.terminal_session ?? {
          command: "",
          output: "",
          title: "FreeAct Terminal",
        };

        const newOutput =
          (term.output ? term.output + "\n" : "") +
          (type === "Code"
            ? `\n🔧 Code action:\n${text}\n`
            : `\n✅ Execution result:\n${text}\n`);

        return {
          ...state,
          terminal_session: { ...term, command: type, output: newOutput },
        };
      });
    } catch (err) {
      console.error("[FreeAct] Error updating terminal:", err);
    }
  }

  // Add a visual separator between different FreeAct runs
  function addTerminalSeparator() {
    console.log("[FreeAct] Adding terminal separator");
    //  ─ looks nicer in most terminals; adjust length if needed
    appendToTerminal("─".repeat(60), "Output");
  }

  async function handleCodeAction(data) {
    try {
      console.log("[FreeAct] handleCodeAction called with data:", data);
      console.debug("[FreeAct] handleCodeAction event", data);
      if (data?.code) await appendToTerminal(data.code, "Code");
    } catch (err) {
      console.error("[FreeAct] Error handling code action:", err);
    }
  }

  async function handleExecutionResult(data) {
    try {
      console.log("[FreeAct] handleExecutionResult called with data:", data);
      console.debug("[FreeAct] handleExecutionResult event", data);
      if (data?.result) await appendToTerminal(data.result, "Output");
    } catch (err) {
      console.error("[FreeAct] Error handling execution result:", err);
    }
  }

  // Função para rolar para o final da conversa, quando necessário
  async function scrollMessages() {
    try {
      await tick(); // Ensure DOM is updated
      if (messagesContainer) {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
      }
    } catch (err) {
      console.error("[FreeAct] Error scrolling messages:", err);
    }
  }

  // Handle FreeAct messages from WebSocket
  async function handleFreeActModelResponse(data) {
    console.log("[FreeAct] handleFreeActModelResponse called with data:", data);
    console.debug("[FreeAct] handleFreeActModelResponse event", data);
    try {
      const text = data?.text;

      if (!text) {
        console.warn("[FreeAct] model_response missing text payload", data);
        return;
      }

      await tick(); // Ensure DOM is ready
      
      // Verificar se o usuário está próximo do final antes de atualizar
      const isAtBottom =
        messagesContainer &&
        messagesContainer.scrollHeight - messagesContainer.scrollTop <=
          messagesContainer.clientHeight + 50;

      console.log("[FreeAct] Updating freeactMessages store with new message");
      freeactMessages.update((msgs) => [
        ...msgs,
        {
          from_devika: true,
          message: text,
          timestamp: new Date().toISOString(),
        },
      ]);

      // Só fazer auto-scroll se o usuário já estiver próximo do final
      // ou se for uma mensagem do agente
      if (isAtBottom) {
        // Usar setTimeout para garantir que o DOM foi atualizado
        setTimeout(scrollMessages, 0);
      }
    } catch (err) {
      console.error("[FreeAct] Error handling model response", err, data);
    }
  }

  /**
   * Recebe estatísticas de uso (tokens e custo) vindas do backend
   * e adiciona como uma mensagem do agente, abaixo da resposta.
   */
  async function handleFreeActUsage(data) {
    console.log("[FreeAct] handleFreeActUsage called with data:", data);
    try {
      const usage = data?.usage || {};
      const text = `Tokens usados: ${usage.total_tokens ?? "?"} (input: ${usage.input_tokens ?? "?"}, output: ${usage.output_tokens ?? "?"})\nCusto: $${usage.cost ?? "?"}`;

      await tick(); // Ensure DOM is ready
      
      // Verificar se o usuário está próximo do final antes de atualizar
      const isAtBottom = messagesContainer && 
        (messagesContainer.scrollHeight - messagesContainer.scrollTop <= messagesContainer.clientHeight + 50);

      freeactMessages.update((msgs) => [
        ...msgs,
        {
          from_devika: true,
          // Exibe em itálico para diferenciar de uma resposta normal
          message: `_${text}_`,
          timestamp: new Date().toISOString(),
        },
      ]);

      // Só fazer auto-scroll se o usuário já estiver próximo do final
      if (isAtBottom) {
        setTimeout(scrollMessages, 0);
      }
    } catch (err) {
      console.error("[FreeAct] Error handling usage stats:", err);
    }
  }

  function handleFreeActStatus(data) {
    console.log("[FreeAct] handleFreeActStatus called with data:", data);
    try {
      const status = data?.status;
      if (!status) return;
      
      freeactStatus.set(status);
      
      if (status === "starting") {
        toast.info("FreeAct agent is starting...");
        isSending.set(true);
      } else if (status === "completed") {
        // Add a separator after each completed run for better readability
        addTerminalSeparator();

        toast.success("FreeAct agent completed");
        isSending.set(false);
      }
    } catch (err) {
      console.error("[FreeAct] Error handling status update:", err);
      isSending.set(false);
    }
  }

  function handleFreeActError(data) {
    console.log("[FreeAct] handleFreeActError called with data:", data);
    try {
      const error = data?.error || "Unknown error";
      toast.error(`FreeAct error: ${error}`);
      freeactStatus.set("error");
      isSending.set(false);
    } catch (err) {
      console.error("[FreeAct] Error handling error event:", err);
      isSending.set(false);
    }
  }

  function handleFreeActInputRequest(data) {
    console.log("[FreeAct] handleFreeActInputRequest called with data:", data);
    try {
      const prompt = data?.prompt || "Input requested";
      toast.info(`FreeAct is requesting input: ${prompt}`);
      // In a more advanced implementation, we could show a modal for user input
    } catch (err) {
      console.error("[FreeAct] Error handling input request:", err);
    }
  }

  // Send message to FreeAct agent
  async function sendMessage() {
    console.log("[FreeAct] sendMessage called with input:", messageInput);
    if (!messageInput?.trim() || !selectedProject) {
      console.warn("[FreeAct] Cannot send empty message or no project selected");
      return;
    }

    try {
      await tick(); // Ensure DOM is ready
      
      // Verificar se o usuário está próximo do final antes de atualizar
      const isAtBottom = messagesContainer && 
        (messagesContainer.scrollHeight - messagesContainer.scrollTop <= messagesContainer.clientHeight + 50);

      // Add user message to the conversation
      freeactMessages.update(msgs => [...msgs, {
        from_devika: false,
        message: messageInput,
        timestamp: new Date().toISOString()
      }]);

      // Só fazer auto-scroll se o usuário já estiver próximo do final
      if (isAtBottom) {
        setTimeout(scrollMessages, 0);
      }

      // Get the socket ID for tracking the specific connection
      const socketId = socket?.id;
      console.log(`[FreeAct] Current socket ID: ${socketId}`);
      if (!socketId) {
        console.error("[FreeAct] Socket ID not available");
        toast.error("Socket connection not available");
        return;
      }

      isSending.set(true);
      
      // Send the message to the backend
      console.log(`[FreeAct] Sending message to backend: ${messageInput}, project: ${selectedProject}, sid: ${socketId}`);
      const response = await fetch(`${API_BASE_URL}/api/freeact-message`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message: messageInput,
          project_name: selectedProject,
          sid: socketId
        }),
      });

      if (!response.ok) {
        throw new Error("Failed to send message to FreeAct agent");
      }
      
      const responseData = await response.json();
      console.log("[FreeAct] Backend response:", responseData);
      
      // Clear the input field
      messageInput = "";
    } catch (error) {
      console.error("[FreeAct] Error sending message:", error);
      toast.error(`Error: ${error.message}`);
      isSending.set(false);
    }
  }
</script>

<div class="flex flex-col h-full w-full overflow-hidden">
  <!-- Header -->
  <div class="flex-none p-4 bg-secondary">
    <h1 class="text-2xl font-bold">FreeAct Agent</h1>
    <p class="text-sm text-muted-foreground">
      An AI agent that can run Python code to answer questions and analyze data. 
      FreeAct uses code execution to provide more accurate and interactive responses.
    </p>
  </div>

  <!-- Main content area -->
  <div class="flex-1 overflow-hidden">
    <!-- Horizontal splitter: conversation | browser + terminal -->
    <Resizable.PaneGroup class="h-full" direction="horizontal">
      <!-- Messages area -->
      <!-- flex-1 garante ocupar todo o espaço vertical disponível -->
      <Resizable.Pane class="flex-1 min-h-[200px] overflow-hidden p-4">
        <!-- div que realmente receberá o scroll -->
        <div
          bind:this={messagesContainer}
          class="flex flex-col gap-4 max-w-4xl mx-auto overflow-y-auto h-full"
        >
          {#if $freeactMessages.length === 0}
            <div class="text-center text-muted-foreground p-8">
              <p>No messages yet. Start a conversation with FreeAct!</p>
              <p class="text-sm mt-2">
                Try asking questions that might require code execution, data analysis, or accessing external APIs.
              </p>
              <p class="text-sm mt-2">
                Examples:
              </p>
              <ul class="text-sm mt-1 list-disc list-inside">
                <li>Search for recent research papers on machine learning</li>
                <li>Analyze this dataset and create a visualization</li>
                <li>Help me understand how this algorithm works</li>
              </ul>
            </div>
          {:else}
            {#each $freeactMessages as message}
              <div class={`p-4 rounded-lg ${message.from_devika ? 'bg-primary/10 ml-8' : 'bg-secondary mr-8'}`}>
                <div class="flex items-center mb-2">
                  <div class="font-semibold">
                    {message.from_devika ? 'FreeAct' : 'You'}
                  </div>
                  <div class="ml-auto text-xs text-muted-foreground">
                    {new Date(message.timestamp).toLocaleTimeString()}
                  </div>
                </div>
                <div class="whitespace-pre-wrap">
                  {#if message.from_devika}
                    {@html renderMarkdown(message.message)}
                  {:else}
                    {message.message}
                  {/if}
                </div>
              </div>
            {/each}
            <!-- Removida a âncora para auto-scroll, agora usamos scrollTop/scrollHeight -->
          {/if}
        </div>
      </Resizable.Pane>

      <!-- Browser + Terminal widgets (FreeAct specific copies) -->
      <Resizable.Pane class="flex flex-col gap-4 w-full max-w-[50%] p-2">
        <FreeActBrowserWidget />
        <FreeActTerminalWidget />
      </Resizable.Pane>
    </Resizable.PaneGroup>
  </div>

  <!-- Input area -->
  <div class="flex-none p-4 bg-secondary">
    <div class="max-w-4xl mx-auto">
      <div class="flex gap-2">
        <input
          type="text"
          class="flex-1 p-2 rounded border border-input bg-background"
          placeholder="Ask FreeAct a question..."
          bind:value={messageInput}
          on:keydown={(e) => e.key === 'Enter' && !$isSending && sendMessage()}
          disabled={$isSending || !selectedProject}
        />
        <button
          class="px-4 py-2 bg-primary text-primary-foreground rounded hover:bg-primary/90 disabled:opacity-50"
          on:click={sendMessage}
          disabled={$isSending || !messageInput?.trim() || !selectedProject}
        >
          {$isSending ? 'Processing...' : 'Send'}
        </button>
      </div>
      {#if !selectedProject}
        <p class="text-sm text-warning mt-2">Please select a project first from the home page.</p>
      {/if}
    </div>
  </div>
</div>
