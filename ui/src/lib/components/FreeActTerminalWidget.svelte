<script>
  // This is a FreeAct-specific copy of TerminalWidget.svelte
  // It is intended to be modified independently for FreeAct's specific needs.
  import { onMount } from "svelte";
  import { onDestroy, tick } from "svelte";
  import { Terminal } from "@xterm/xterm";
  import { FitAddon } from "@xterm/addon-fit";
  import { agentState } from "$lib/store"; // Assuming FreeAct will update agentState or a similar store
  import "@xterm/xterm/css/xterm.css";

  // Keep references so they are accessible in helper functions
  let terminal;
  let fitAddon;
  let resizeTimeout;

  /**
   * Clear the terminal output and reset agentState terminal_session.
   */
  function clearTerminal() {
    try {
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
    } catch (err) {
      console.error("[FreeActTerminalWidget] Error clearing terminal:", err);
    }
  }

  onMount(async () => {
    try {
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

      const contentEl = document.getElementById("freeact-terminal-content");
      if (contentEl) {
        try {
          terminal.loadAddon(fitAddon);
          terminal.open(contentEl);
        } catch (err) {
          console.error("[FreeActTerminalWidget] Error opening terminal:", err);
        }
      } else {
        console.error("[FreeActTerminalWidget] Terminal content element not found.");
      }

      try {
        if (fitAddon) {
          fitAddon.fit();
        }
      } catch (err) {
        console.error("[FreeActTerminalWidget] Error fitting terminal on mount:", err);
      }

      /* -------------------------- Auto-resize support -------------------------- */
      let resizeObserver;
      if (contentEl) {
        resizeObserver = new ResizeObserver(() => {
          // Debounce resize operations to avoid excessive calls
          if (resizeTimeout) {
            clearTimeout(resizeTimeout);
          }
          resizeTimeout = setTimeout(() => {
            try {
              if (fitAddon) {
                fitAddon.fit();
              }
            } catch (err) {
              console.error("[FreeActTerminalWidget] Error fitting terminal on resize:", err);
            }
          }, 100); // 100ms debounce
        });
        resizeObserver.observe(contentEl);
      }

      let previousState = {};

      // Clean-up observers on component destroy
      onDestroy(() => {
        if (resizeTimeout) {
          clearTimeout(resizeTimeout);
        }
        if (resizeObserver && contentEl) {
          resizeObserver.unobserve(contentEl);
        }
        if (terminal) {
          terminal.dispose(); // Dispose xterm.js instance
        }
      });
    } catch (err) {
      console.error("[FreeActTerminalWidget] Error during terminal initialization:", err);
    }
  });

  /* ------------------------------------------------------------------ */
  /* Reactive update when agentState.terminal_session changes            */
  /* ------------------------------------------------------------------ */

  // keep previous state for diffing
  let previousState = {};

  $: if (terminal && $agentState?.terminal_session) {
      const { command = 'echo "Waiting..."', output = "Waiting...", title = "FreeAct Terminal" } =
        $agentState.terminal_session ?? {};

      // detect changes
      if (
        command !== previousState.command ||
        output !== previousState.output ||
        title !== previousState.title
      ) {
        // update title
        const titleEl = document.getElementById("freeact-terminal-title");
        if (titleEl) {
          titleEl.innerText = title;
        }

        // write to terminal
        tick().then(() => {
          if (terminal) {
            terminal.reset();
            terminal.write(`$ ${command}\r\n\r\n${output}\r\n`);
            try {
              fitAddon?.fit();
            } catch {/* ignore */}
          }
        });

        previousState = { command, output, title };
      }
  } else if (terminal && !$agentState?.terminal_session) {
      // if session cleared, reset terminal once
      tick().then(() => terminal && terminal.reset());
  }
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
