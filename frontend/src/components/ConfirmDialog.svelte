<script>
  // Confirmation dialog in place of window.confirm. The question text is the
  // panel's own; the answers come back through the promise in confirm.js.
  import { Modal, Button } from '@monos/ui';
  import { confirmState, answerConfirm } from '../lib/confirm.js';
</script>

<Modal
  open={$confirmState !== null}
  on:close={() => answerConfirm(false)}
  showClose={false}
  closeOnBackdrop={false}
>
  {#if $confirmState}
    <p class="text-sm leading-relaxed">{$confirmState.message}</p>
  {/if}
  <svelte:fragment slot="footer">
    <Button variant="secondary" on:click={() => answerConfirm(false)}>Cancel</Button>
    <Button on:click={() => answerConfirm(true)}>OK</Button>
  </svelte:fragment>
</Modal>
