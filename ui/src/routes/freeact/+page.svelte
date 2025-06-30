<script>
  import { onDestroy, onMount } from "svelte";
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

  // Get the selected project from localStorage
  onMount(() => {
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

    // Initialize agentState with a safe default structure
    agentState.update(current => {
      return {
        ...current,
        browser_session: current?.browser_session ?? { url: null, screenshot: null },
        terminal_session: current?.terminal_session ?? { command: null, output: null, title: "FreeAct Terminal" },
      };
    });

    const load = async () => {
      try {
        if (!(await checkServerStatus())) {
          toast.error("Failed to connect to server");
          return;
        }
        
        serverStatus.set(true);
        await fetchInitialData();
        
        // Connect socket if not already connected
        if (!socket.connected) {
          socket.connect();
        }
        
        // Get selected project from localStorage
        selectedProject = localStorage.getItem("selectedProject") || "";
        if (!selectedProject) {
          toast.error("Please select a project first");
        }

        // Set up socket listeners for FreeAct
        socketListener("freeact_status", handleFreeActStatus);
        socketListener("freeact_error", handleFreeActError);
        socketListener("freeact_input_request", handleFreeActInputRequest);
        socketListener("freeact_usage", handleFreeActUsage);   // 💬 estatística

        // novos eventos específicos
        socketListener("freeact_model_response", handleFreeActModelResponse);
        socketListener("freeact_code_action", handleCodeAction);
        socketListener("freeact_execution_result", handleExecutionResult);
      } catch (error) {
        console.error("Error during FreeAct page initialization:", error);
        toast.error(`Error initializing FreeAct page: ${error.message}`);
      }
    };

    load();
  });

  onDestroy(() => {
    // Clean up socket listeners
    if (socket?.connected) {
      try {
        socket.off("freeact_model_response");
        socket.off("freeact_code_action");
        socket.off("freeact_execution_result");
        socket.off("freeact_status");
        socket.off("freeact_error");
        socket.off("freeact_input_request");
        socket.off("freeact_usage");
      } catch (err) {
        console.error("[FreeAct] Error cleaning up socket listeners:", err);
      }
    }
  });

  /* ------------------------------------------------------------------ */
  /* Terminal output helper (uses agentState so widget auto-updates)     */
  /* ------------------------------------------------------------------ */
  function appendToTerminal(text, type = "Output") {
    // DEBUG: track every update to terminal widget
    console.debug("[FreeAct] appendToTerminal", { type, preview: (text ?? "").slice(0, 120) });
    try {
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

  function handleCodeAction(data) {
    try {
      console.debug("[FreeAct] handleCodeAction event", data);
      if (data?.code) appendToTerminal(data.code, "Code");
    } catch (err) {
      console.error("[FreeAct] Error handling code action:", err);
    }
  }

  function handleExecutionResult(data) {
    try {
      console.debug("[FreeAct] handleExecutionResult event", data);
      if (data?.result) appendToTerminal(data.result, "Output");
    } catch (err) {
      console.error("[FreeAct] Error handling execution result:", err);
    }
  }

  // Função para rolar para o final da conversa, quando necessário
  function scrollMessages() {
    try {
      if (messagesContainer) {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
      }
    } catch (err) {
      console.error("[FreeAct] Error scrolling messages:", err);
    }
  }

  // Handle FreeAct messages from WebSocket
  function handleFreeActModelResponse(data) {
    console.debug("[FreeAct] handleFreeActModelResponse event", data);
    try {
      const text = data?.text;

      if (!text) {
        console.warn("[FreeAct] model_response missing text payload", data);
        return;
      }

      // Verificar se o usuário está próximo do final antes de atualizar
      const isAtBottom =
        messagesContainer &&
        messagesContainer.scrollHeight - messagesContainer.scrollTop <=
          messagesContainer.clientHeight + 50;

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
  function handleFreeActUsage(data) {
    try {
      const usage = data?.usage || {};
      const text = `Tokens usados: ${usage.total_tokens ?? "?"} (input: ${usage.input_tokens ?? "?"}, output: ${usage.output_tokens ?? "?"})\nCusto: $${usage.cost ?? "?"}`;

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
    try {
      const status = data?.status;
      if (!status) return;
      
      freeactStatus.set(status);
      
      if (status === "starting") {
        toast.info("FreeAct agent is starting...");
        isSending.set(true);
      } else if (status === "completed") {
        toast.success("FreeAct agent completed");
        isSending.set(false);
      }
    } catch (err) {
      console.error("[FreeAct] Error handling status update:", err);
      isSending.set(false);
    }
  }

  function handleFreeActError(data) {
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
    if (!messageInput?.trim() || !selectedProject) {
      return;
    }

    try {
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
      if (!socketId) {
        toast.error("Socket connection not available");
        return;
      }

      isSending.set(true);
      
      // Send the message to the backend
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
      
      // Clear the input field
      messageInput = "";
    } catch (error) {
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
