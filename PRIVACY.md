# Privacy Policy — Voice Mode Proxy

Last updated 2026-09-23

Voice Mode Proxy is an iOS app that lets you talk to a server you run yourself. This
policy describes what the app does with your data. The short version: your data goes to
your own server and nowhere else.

## What the app collects

**Nothing is sent to us.** The app has no accounts, no analytics, no advertising, no crash
reporting and no third-party services. We do not receive, store or see any data from the
app.

**Microphone.** When you turn the mic on, the app streams audio to the server address you
entered in the app, and to nothing else. Audio is not stored on the phone. The mic is off
until you tap it and stays off in demo mode.

**Text you type and replies you receive** travel between the phone and your server only.

**Stored on the phone.** The app keeps one setting: the address of your server. It keeps
no history; the conversation shown on screen is fetched from your server each time.

## Your server

The server component runs on a computer you control. What it does with audio and text,
including the transcripts it writes to disk and the requests it makes to Anthropic's
Claude on your behalf, happens under your own account and your own settings. See the
project README for how the server stores session logs and how to delete them.

## Network

The app connects only to the server address you enter. The project recommends reaching
it over your own private network (Tailscale), so no traffic crosses the public internet.
The app makes no other network connections.

## Demo mode

Demo mode runs entirely on the phone with a built-in fake server. Nothing leaves the
device. Replies are read aloud by the phone's own speech voice.


## Changes

If this policy changes, the date at the top changes and the new text is published at the
same address.

## Contact

Questions: open an issue on the project's GitHub repository, or email George Mazzeo at
mazzeogeorge@gmail.com.
