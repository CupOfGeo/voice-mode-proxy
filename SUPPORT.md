# Support — Voice Mode Proxy

Voice Mode Proxy is an open-source app and server. There is no company behind it; it is
maintained by George Mazzeo.

## Getting help

- **Setup and usage:** the project README covers installing the server on a Mac, putting
  Tailscale on your phone, and entering the server address in the app.
- **Bugs and questions:** open an issue on the project's GitHub repository. Include what
  you did, what you expected, and what happened. For app problems, the iOS version and
  the TestFlight build number help; for server problems, the last lines of the server log.
- **Email:** mazzeogeorge@gmail.com for anything that should not be public.

## Common problems

- **"Cannot reach" your server.** Check that the server is running on the Mac, the Mac is
  awake (it must not be asleep; see the README on energy settings), and the phone is on
  the same Tailscale network. Use Test connection on the Settings screen.
- **The mic button is greyed out.** Speech recognition is done by the server. It is off in
  demo mode, and off if the server was started without speech recognition.
- **Replies are cut off when you talk.** Barge-in is off by default; if you turned it on,
  the speaker can be heard by the mic and read as an interruption. Turn it off in
  Settings.
- **No sound with the screen locked.** Make sure the mic was on before locking; the
  active audio session is what keeps the app alive in the background.

## What the app does not do

It does not collect data, has no accounts, and talks only to the server you point it at.
See the privacy policy for details.
