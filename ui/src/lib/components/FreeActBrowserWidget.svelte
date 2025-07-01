<script>
  /*
   * FreeAct-specific Browser widget.
   * Receives a **local** store (freeactBrowserState) so it is completely
   * independent from the global `agentState` used by the Home page.
   */
  export let freeactBrowserState; // writable store injected by the FreeAct page
  import { API_BASE_URL, socket } from "$lib/api";

  socket.on('screenshot', function(msg) {
    const data = msg['data'];
    // Update the local browser state with the new screenshot (base64 data URI)
    // so the widget reacts automatically.
    freeactBrowserState.update(state => ({
      ...state,
      screenshot: `data:image/png;base64,${data}`
    }));
  });

</script>

<div class="w-full h-full flex flex-col border-[3px] rounded-xl overflow-y-auto bg-browser-window-background border-window-outline">
  <div class="p-2 flex items-center border-b border-border bg-browser-window-ribbon h-12">
    <div class="flex space-x-2 ml-2 mr-4">
      <div class="w-3 h-3 bg-browser-window-dots rounded-full"></div>
      <div class="w-3 h-3 bg-browser-window-dots rounded-full"></div>
      <div class="w-3 h-3 bg-browser-window-dots rounded-full"></div>
    </div>
    <input
      type="text"
      id="freeact-browser-url"
      class="flex-grow h-7 text-xs rounded-lg p-2 overflow-x-auto bg-browser-window-search text-browser-window-foreground"
      placeholder="devika://newtab"
      value={$freeactBrowserState.url || ""}
    />
  </div>
  <div id="freeact-browser-content" class="flex-grow overflow-y-auto">
    {#if $freeactBrowserState.screenshot}
      <img
        class="freeact-browser-img"
        alt="Browser snapshot"
        src={
          $freeactBrowserState.screenshot.startsWith("data:image")
            ? $freeactBrowserState.screenshot
            : `${API_BASE_URL}/api/get-browser-snapshot?snapshot_path=${$freeactBrowserState.screenshot}`
        }
      />
    {:else}
      <div class="text-gray-400 text-sm text-center mt-5">
        <strong>💡 TIP:</strong> FreeAct can browse the web!
      </div>
    {/if}
  </div>
</div>

<style>
  #freeact-browser-url {
    pointer-events: none
  }

  .freeact-browser-img {
    display: block;
    object-fit: contain;
  }
</style>
