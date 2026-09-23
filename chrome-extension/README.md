# Optional local Chrome connection

See [INSTALL.md](../INSTALL.md) for setup. Generate `config.js` locally using
`setup_chrome_bridge.py` before loading this directory in Chrome. No credential
is distributed. Enable the bridge explicitly in the app or through
`BOOK_OCR_ENABLE_BRIDGE=1`.

Permissions: debugger (screenshots/page interaction), tabs (reader discovery),
alarms (reconnection), loopback port 8508 (local transfer). Debugger is a broad
Chrome permission; the implementation restricts operations to supported Kindle
book URLs. Review the code and permission prompt before installing.

Multiple ambiguous reader tabs cause capture to stop. Do not attach another
debugger to the same book tab. Generated configuration, keys, profiles and
capture results must never be published. This is a beta; reader layouts and
browser-extension conflicts can require manual intervention.
