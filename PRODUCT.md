<!-- impeccable:product-schema 1 -->
# Local LLM Hub: product record

## Platform

A web panel opened in the browser at 127.0.0.1:8765. Backend in Python (FastAPI). Runs on macOS with Apple Silicon. External services are needed only to download models from Hugging Face and to install packages.

## Users

A Mac owner who wants to run a language model locally and cannot or does not want to set up the Terminal: a beginner who needs an assistant for questions. A developer who connects the local model to opencode or to their own scripts.

## Product Purpose

Bring up a local model on a Mac in a few steps that need no infrastructure knowledge: install the program, download a model, start it, ask a question. The panel also watches memory so that the model does not bring the system down.

## Positioning

Existing tools (LM Studio, Ollama) cover part of the job. Three things matter here: a memory check before start, plain-language errors instead of raw tracebacks, and open source that can be installed with one command and read in full.

## Operating Context

One Mac owned by one person. Models are 17–28 GB and long contexts reach 262 thousand tokens, so memory and swap are the main constraints. The panel runs in the background through launchd and must not get in the way of other work.

## Capabilities and Constraints

Can: run MLX and GGUF models, download models, check memory, restart an engine after a crash, integrate with opencode.

Cannot and should not: run on Linux or Windows, manage remote servers, store conversation history (answers are not saved, except for an event log without the text), send data anywhere except when downloading models.

## Brand Commitments

Everything stays local. No telemetry. Clear language in the interface without condescension. Errors say what to do. Tokens and settings never leave the project folder.

## Evidence on Hand

Verified on one Mac (Apple Silicon, 48 GB): running Ornith 1.5 35B-A3B in 4-bit and 6-bit, Inkling 2 Mini in MLX and GGUF, long context up to 100 thousand tokens, automatic restart, installing and removing engines and models, a beginner's scenario through the browser. Not verified: a clean installation on another Mac, a reboot with autostart, downloading a gated model with a working token (403 during testing, caused by the Hugging Face side).

## Product Principles

Protect the system first: warn about low memory rather than crash. One primary button on screen. No shadows or gradients. Settings are visible and explained. The code can be read without a build step.

## Accessibility & Inclusion

Text is at least 14 px, body text 16 px, contrast at least 4.5:1 in both themes. Buttons are at least 44 px. Animation is disabled when the system asks for reduced motion. The interface is in English; technical terms are explained in hints where they appear.
