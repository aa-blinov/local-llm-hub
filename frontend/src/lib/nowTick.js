// A shared ticking clock; the transient messages in step 3 of the Simple view
// expire by wall clock, so the view needs a value that invalidates.
import { writable } from 'svelte/store';

export const nowTick = writable(Date.now());

if (typeof window !== 'undefined') {
  setInterval(() => nowTick.set(Date.now()), 1000);
}
