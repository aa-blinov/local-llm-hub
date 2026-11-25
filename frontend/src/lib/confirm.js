// A confirmation dialog in place of window.confirm. The question text is the
// same one the old confirm() calls showed; the answer arrives as a promise.
import { writable } from 'svelte/store';

// { message, resolve } while a question is on screen, null otherwise.
export const confirmState = writable(null);

export function confirmBox(message) {
  return new Promise((resolve) => confirmState.set({ message, resolve }));
}

export function answerConfirm(yes) {
  confirmState.update((state) => {
    if (state) state.resolve(yes);
    return null;
  });
}
