<script>
  // This is a FreeAct-specific copy of BrowserWidget.svelte
  // It is intended to be modified independently for FreeAct's specific needs.
  import { agentState } from "$lib/store";
  import { API_BASE_URL, socket } from "$lib/api";

  socket.on('screenshot', function(msg) {
    const data = msg['data'];
    const img = document.querySelector('.freeact-browser-img'); // Changed class name
    if (img) { // Added check to ensure img exists
      img.src = `data:image/png;base64,${data}`;
    }
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
      value={$agentState?.browser_session.url || ""}
    />
  </div>
  <div id="freeact-browser-content" class="flex-grow overflow-y-auto">
    {#if $agentState?.browser_session.screenshot}
      <img
        class="freeact-browser-img"
        src={API_BASE_URL + "/api/get-browser-snapshot?snapshot_path=" + $agentState?.browser_session.screenshot}
        alt="Browser snapshot"
      />
    {:else}
      <div class="text-gray-400 text-sm text-center mt-5"><strong>💡 TIP:</strong> FreeAct can browse the web!</div>
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
