# Optional OpenAI-compatible vision connector

**Gemma 4 with Möbius Custom C1 for OCR remains the recommended default.**
The optional connector lets you use another locally hosted or remote model at
your discretion. OpenAI-compatible describes an API shape, not equivalent model
behavior. It does not guarantee image input, structured responses, completion
of a book, or correction accuracy. The historical Gemma comparison does not
establish performance for other models or servers.

## Requirements

- A **vision-capable LLM** that accepts image data URLs in Chat Completions
  messages. A text-only LLM cannot check the original page image.
- A server implementing `POST /chat/completions` under the configured API base
  URL, non-streaming `choices[].message.content`, and JSON text responses.
- Sufficient model context, output budget, memory and server timeout for page
  images plus OCR. Passing a small connection test does not establish these
  limits for a full book.

This connector does not implement the Responses API, vendor-specific image
upload APIs, tool calls, streaming or server/model installation. The application
still runs OCR locally and needs its OCR dependencies.

## Setup

1. In **Review provider**, select **Advanced: OpenAI-compatible API**.
2. Enter the API base URL, such as `http://127.0.0.1:1234/v1`, and the exact vision
   model identifier exposed by that server. Do not append `/chat/completions`.
3. Enter an API key if required. Choose `json_schema` when supported; otherwise
   try `json_object` or `prompt`. Local correction validation remains enabled
   in all three modes. Select the output token parameter your server accepts:
   `max_tokens` or `max_completion_tokens`.
   **Reasoning effort** is optional and server-dependent. `server_default` sends
   no parameter; `none` can disable thinking when the server/model supports it,
   leaving the token budget for the JSON answer. Unsupported values may be
   rejected or interpreted differently by a provider. The connector does not
   silently change this setting. See the [Ollama compatibility reference](https://docs.ollama.com/api/openai-compatibility) for that server.
4. Read the destination notice and enable the consent checkbox. Click
   **Test vision connection and enable**. This sends only a generated image
   containing a random code and requests a JSON answer; it sends no book pages.
5. After the test passes, start a PDF, image or Kindle job normally. Changing
   any connection setting requires another test. Re-selecting local Gemma
   restores the default provider for new jobs.

Use HTTPS for remote servers. Plain HTTP is accepted only for loopback
addresses or `localhost`; a LAN IP without TLS is rejected. For a local-only
server on another machine, an explicitly configured SSH loopback tunnel is
one option. URLs containing credentials or query strings are rejected.
Redirects are not followed, and environment HTTP proxy settings are not used.
These restrictions do not certify the trustworthiness of the chosen endpoint.

## Privacy and credentials

The default Gemma workflow is local. With this optional connector enabled,
**page images, OCR text and review prompts are sent to the selected endpoint**.
Remote providers may retain data and charge for requests. Review, verification,
repair and split-page requests can produce multiple calls per page. Choose an
endpoint and content you are comfortable sending; the app does not automatically
switch to a cloud provider when local review fails.

Connection profiles, including API keys, are stored as **plaintext** JSON under
`.connector-profiles/`, with directory mode 0700 and file mode 0600. This is
filesystem access control, not encryption or a system keychain. Profiles are
excluded from job ZIP exports and the public source package. Do not publish or
share that directory. The profile identifier is saved in each job; the API key
is not. Profile files are immutable through the UI, so changing settings does
not silently redirect a saved job to another endpoint.

To revoke access, revoke the key at the provider and remove the corresponding
local profile when no job needs it. Saved jobs referencing a missing or invalid
profile fail explicitly; they do not fall back to another provider. Starting
a fresh job after testing a new connection creates a new profile. Avoid
credentials in model names or document names. Provider error bodies are not
copied into job errors.

## Execution and output

For this connector, OCR completes before model review starts. The app does not
control the external server's GPU placement, model loading, VRAM recovery or
request concurrency, even when that server runs on the same computer. The
local Gemma shared/dual GPU scheduler does not apply to that server.

The existing C1 OCR instructions, correction validation, image checks and
source-preservation path are retained. A different model may follow these
instructions differently. Requests that time out, refuse, return invalid JSON
or exceed output limits can leave partial results. Original OCR and completed
pages remain available. Unapproved model suggestions never silently replace
original OCR in the reading text. Review important names, numbers and passages
against the source images.

The connection test checks one small image/JSON exchange only. It is not a
supported-model list, an accuracy benchmark, or a full-book completion guarantee.

The app also accepts an entire valid JSON response wrapped in one Markdown code
fence. It does not extract JSON from a response containing surrounding commentary.
The connection probe still requires the exact image code; a timeout, token limit
or wrong reading leaves the connector disabled.
