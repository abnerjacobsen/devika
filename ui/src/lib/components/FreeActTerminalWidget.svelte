<script>
  import { onMount, onDestroy } from "svelte";
  import { Terminal } from "@xterm/xterm";
  import { FitAddon } from "@xterm/addon-fit";
  /* Independent store injected by FreeAct page (NOT the global agentState) */
  export let freeactTerminalState;
  import "@xterm/xterm/css/xterm.css";

  // DOM element references using Svelte's bind:this
  let containerEl;
  let titleEl;
  
  // Terminal components
  let terminal;
  let fitAddon;
  let resizeObserver;

  // Clear terminal function
  function clearTerminal() {
    if (terminal) terminal.reset();
    /* Reset the local terminal store – fully independent from home page */
    freeactTerminalState.set({
      command: null,
      output: "",
      title: "FreeAct Terminal",
    });
  }

  // Initialize terminal on mount
  onMount(() => {
    const bg = getComputedStyle(document.body).getPropertyValue("--terminal-window-background") || "#000";
    const fg = getComputedStyle(document.body).getPropertyValue("--terminal-window-foreground") || "#fff";

    // Create terminal instance
    terminal = new Terminal({
      disableStdin: true,
      cursorBlink: true,
      convertEol: true,
      rows: 1,
      theme: {
        background: bg,
        foreground: fg,
        innerText: fg,
        cursor: fg,
        selectionForeground: bg,
        selectionBackground: fg
      },
    });

    // Add fit addon
    fitAddon = new FitAddon();
    terminal.loadAddon(fitAddon);

    // Open terminal in container element (using bind:this reference)
    if (containerEl) {
      terminal.open(containerEl);
      fitAddon.fit();
      
      // Setup resize observer for auto-resizing
      resizeObserver = new ResizeObserver(() => {
        setTimeout(() => fitAddon?.fit(), 100);
      });
      resizeObserver.observe(containerEl);
    }
  });

  // Clean up on destroy - OUTSIDE onMount
  onDestroy(() => {
    if (resizeObserver) {
      resizeObserver.disconnect();
    }
    if (terminal) {
      terminal.dispose();
    }
  });

  // Reactive updates using Svelte's reactive syntax
  let prevState = {};
  
  /* ------------------------------------------------------------------ */
  /* Reactive update driven by local freeactTerminalState                */
  /* ------------------------------------------------------------------ */

  $: if (terminal && $freeactTerminalState) {
    const session = $freeactTerminalState;
    const cmd = session.command || 'echo "Waiting..."';
    const out = session.output || "Waiting...";
    const title = session.title || "FreeAct Terminal";

    // Only update if something changed
    if (cmd !== prevState.command || out !== prevState.output || title !== prevState.title) {
      // Update title safely using bind:this reference
      if (titleEl) {
        titleEl.textContent = title;
      }
      
      // Update terminal content
      terminal.reset();
      terminal.write(`$ ${cmd}\r\n\r\n${out}\r\n`);
      
      // Fit terminal after update
      setTimeout(() => fitAddon?.fit(), 0);
      
      // Store previous state
      prevState = { command: cmd, output: out, title };
    }
  }
</script>

<div class="w-full h-full flex flex-col border-[3px] overflow-hidden rounded-xl border-window-outline">
  <div class="flex items-center p-2 border-b bg-terminal-window-ribbon">
    <div class="flex ml-2 mr-4 space-x-2">
      <div class="w-3 h-3 rounded-full bg-terminal-window-dots"></div>
      <div class="w-3 h-3 rounded-full bg-terminal-window-dots"></div>
      <div class="w-3 h-3 rounded-full bg-terminal-window-dots"></div>
    </div>
    <!-- Use bind:this for direct element reference -->
    <span bind:this={titleEl} class="text-tertiary text-sm">FreeAct Terminal</span>
    <button
      class="ml-auto text-xs hover:text-red-500 focus:outline-none"
      title="Clear terminal"
      on:click={clearTerminal}
    >
      <i class="fas fa-trash"></i>
    </button>
  </div>
  <!-- Use bind:this for direct element reference -->
  <div
    bind:this={containerEl}
    class="w-full h-full rounded-bl-lg bg-terminal-window-background"
  ></div>
</div>

<style>
  div :global(.xterm) {
    padding: 10px;
  }
  div :global(.xterm-screen) {
    width: 100% !important;
  }
  div :global(.xterm-rows) {
    width: 100% !important;
    height: 100% !important;
    overflow-x: auto !important;
    scrollbar-width: none;
  }
</style>
