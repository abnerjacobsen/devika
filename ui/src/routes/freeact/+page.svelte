<script>
  import { onDestroy, onMount } from "svelte";
  import { toast } from "svelte-sonner";

  import MessageContainer from "$lib/components/MessageContainer.svelte";
  import MessageInput from "$lib/components/MessageInput.svelte";
  import * as Resizable from "$lib/components/ui/resizable/index.js";

  import { serverStatus } from "$lib/store";
  import { socketListener, emitMessage } from "$lib/sockets";
  import { checkServerStatus, fetchInitialData } from "$lib/api";
  import { socket, API_BASE_URL } from "$lib/api";

  // FreeAct specific stores
  import { writable } from "svelte/store";
  // Remover afterUpdate que estava forçando scroll sempre
  const freeactMessages = writable([]);
  const freeactStatus = writable("idle"); // idle, active, error
  const isSending = writable(false);

  let selectedProject = "";
  let messageInput = "";
  let messagesContainer; // Referência ao container de mensagens para scroll

  // Get the selected project from localStorage
  onMount(() => {
    const load = async () => {
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
      socketListener("freeact_output", handleFreeActOutput);
      socketListener("freeact_status", handleFreeActStatus);
      socketListener("freeact_error", handleFreeActError);
      socketListener("freeact_input_request", handleFreeActInputRequest);
      socketListener("freeact_usage", handleFreeActUsage);   // 💬 nova estatística
    };

    load();
  });

  onDestroy(() => {
    // Clean up socket listeners
    if (socket.connected) {
      socket.off("freeact_output");
      socket.off("freeact_status");
      socket.off("freeact_error");
      socket.off("freeact_input_request");
      socket.off("freeact_usage");
    }
  });

  // Função para rolar para o final da conversa, quando necessário
  function scrollMessages() {
    if (messagesContainer) {
      messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
  }

  // Handle FreeAct messages from WebSocket
  function handleFreeActOutput(data) {
    const text = data.text;
    if (text) {
      // Verificar se o usuário está próximo do final antes de atualizar
      const isAtBottom = messagesContainer && 
        (messagesContainer.scrollHeight - messagesContainer.scrollTop <= messagesContainer.clientHeight + 50);
      
      freeactMessages.update(msgs => [...msgs, {
        from_devika: true,
        message: text,
        timestamp: new Date().toISOString()
      }]);

      // Só fazer auto-scroll se o usuário já estiver próximo do final
      // ou se for uma mensagem do agente
      if (isAtBottom) {
        // Usar setTimeout para garantir que o DOM foi atualizado
        setTimeout(scrollMessages, 0);
      }
    }
  }

  /**
   * Recebe estatísticas de uso (tokens e custo) vindas do backend
   * e adiciona como uma mensagem do agente, abaixo da resposta.
   */
  function handleFreeActUsage(data) {
    const usage = data.usage || {};
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
  }

  function handleFreeActStatus(data) {
    const status = data.status;
    freeactStatus.set(status);
    
    if (status === "starting") {
      toast.info("FreeAct agent is starting...");
      isSending.set(true);
    } else if (status === "completed") {
      toast.success("FreeAct agent completed");
      isSending.set(false);
    }
  }

  function handleFreeActError(data) {
    const error = data.error;
    toast.error(`FreeAct error: ${error}`);
    freeactStatus.set("error");
    isSending.set(false);
  }

  function handleFreeActInputRequest(data) {
    const prompt = data.prompt;
    toast.info(`FreeAct is requesting input: ${prompt}`);
    // In a more advanced implementation, we could show a modal for user input
  }

  // Send message to FreeAct agent
  async function sendMessage() {
    if (!messageInput.trim() || !selectedProject) {
      return;
    }

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
    const socketId = socket.id;

    try {
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
    <Resizable.PaneGroup class="h-full" direction="vertical">
      <!-- Messages area -->
      <!-- flex-1 garante ocupar todo o espaço vertical disponível -->
      <Resizable.Pane bind:this={messagesContainer} class="flex-1 min-h-[200px] overflow-y-auto p-4">
        <div class="flex flex-col gap-4 max-w-4xl mx-auto">
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
                  {message.message}
                </div>
              </div>
            {/each}
            <!-- Removida a âncora para auto-scroll, agora usamos scrollTop/scrollHeight -->
          {/if}
        </div>
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
          disabled={$isSending || !messageInput.trim() || !selectedProject}
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
