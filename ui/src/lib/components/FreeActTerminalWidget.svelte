<script>
  // This is a FreeAct-specific copy of TerminalWidget.svelte
  // It is intended to be modified independently for FreeAct's specific needs.
  import { onMount } from "svelte";
  import { onDestroy } from "svelte";
  import { Terminal } from "@xterm/xterm";
  import { FitAddon } from "@xterm/addon-fit";
  import { agentState } from "$lib/store"; // Assuming FreeAct will update agentState or a similar store
  import "@xterm/xterm/css/xterm.css";

  // Keep references so they are accessible in helper functions
  let terminal;
  let fitAddon;

  /**
   * Clear the terminal output and reset agentState terminal_session.
   */
  function clearTerminal() {
    if (terminal) {
      terminal.reset();
    }
    agentState.update((state) => {
      if (!state) return state;
      return {
        ...state,
        terminal_session: {
          ...(state.terminal_session ?? {}),
          output: "",
          command: "",
        },
      };
    });
  }

  onMount(async () => {
    const terminalBg = getComputedStyle(document.body).getPropertyValue(
      "--terminal-window-background"
    );
    const terminalFg = getComputedStyle(document.body).getPropertyValue(
      "--terminal-window-foreground"
    );

    terminal = new Terminal({
      disableStdin: true,
      cursorBlink: true,
      convertEol: true,
      rows: 1,
      theme: {
        background: terminalBg,
        foreground: terminalFg,
        innerText: terminalFg,
        cursor: terminalFg,
        selectionForeground: terminalBg,
        selectionBackground: terminalFg
      },
    });
    fitAddon = new FitAddon();

    terminal.loadAddon(fitAddon);
    terminal.open(document.getElementById("freeact-terminal-content")); // Changed ID

    fitAddon.fit();

    /* -------------------------- Auto-resize support -------------------------- */
    const contentEl = document.getElementById("freeact-terminal-content");
    let resizeObserver;
    if (contentEl) {
      resizeObserver = new ResizeObserver(() => {
        // Fit the terminal whenever the container size changes
        try {
          fitAddon.fit();
        } catch (_) {
          /* ignore */
        }
      });
      resizeObserver.observe(contentEl);
    }


    let previousState = {};

    agentState.subscribe((state) => {
      if (state && state.terminal_session) {
        let command = state.terminal_session.command || 'echo "Waiting..."';
        let output = state.terminal_session.output || "Waiting...";
        let title = state.terminal_session.title || "FreeAct Terminal"; // Changed default title

        // Check if the current state is different from the previous state
        if (
          command !== previousState.command ||
          output !== previousState.output ||
          title !== previousState.title
        ) {
          // Atualiza o título se o elemento existir
          if (title) {
            const titleEl = document.getElementById("freeact-terminal-title");
            if (titleEl) {
              titleEl.innerText = title;
            }
          }
          terminal.reset();
          terminal.write(`$ ${command}\r\n\r\n${output}\r\n`);
          // Update the previous state
          previousState = { command, output, title };
        }
      } else {
        // Reset the terminal
        terminal.reset();
      }

      fitAddon.fit();
    });

    // Clean-up observers on component destroy
    onDestroy(() => {
      if (resizeObserver && contentEl) {
        resizeObserver.unobserve(contentEl);
      }
    });
  });
</script>

<div
  class="w-full h-full flex flex-col border-[3px] overflow-hidden rounded-xl border-window-outline"
>
  <div class="flex items-center p-2 border-b bg-terminal-window-ribbon">
    <div class="flex ml-2 mr-4 space-x-2">
      <div class="w-3 h-3 rounded-full bg-terminal-window-dots"></div>
      <div class="w-3 h-3 rounded-full bg-terminal-window-dots"></div>
      <div class="w-3 h-3 rounded-full bg-terminal-window-dots"></div>
    </div>
    <span id="freeact-terminal-title" class="text-tertiary text-sm">FreeAct Terminal</span>
    <!-- Clear (trash) button -->
    <button
      class="ml-auto text-xs hover:text-red-500 focus:outline-none"
      title="Clear terminal"
      on:click={clearTerminal}
    >
      <i class="fas fa-trash"></i>
    </button>
  </div>
  <div
    id="freeact-terminal-content"
    class="w-full h-full rounded-bl-lg bg-terminal-window-background "
  ></div>
</div>

<style>
  #freeact-terminal-content :global(.xterm) {
    padding: 10px;
  }
  #freeact-terminal-content :global(.xterm-screen) {
    width: 100% !important;

  }
  #freeact-terminal-content :global(.xterm-rows) {
    width: 100% !important;
    height: 100% !important;
    overflow-x: scroll !important;
    /* hide the scrollbar */
    scrollbar-width: none;
  }
</style>
