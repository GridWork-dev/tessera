---
title: Install
description: Install Tessera on macOS, Windows, or Linux, including the macOS Gatekeeper "Open Anyway" path for unsigned builds.
group: Getting started
order: 20
---

Tessera ships as a desktop build for macOS, Windows, and Linux. Download the
asset for your platform from the [latest release](https://github.com/tessera-app/tessera/releases/latest),
open it, and point Tessera at one or more folders of images and video.

Every release publishes SHA-256 checksums. Verify your download against the
published checksum before running it.

The first launch downloads roughly 3.5 GB of local models from Hugging Face.
After that, Tessera runs fully offline — no further network calls are required to
index, search, or browse.

## macOS

Download the `.dmg`, open it, and drag Tessera to Applications.

Until the first stable release is code-signed and notarized, macOS Gatekeeper
will refuse to open the app on a double-click, reporting that it "cannot be
opened because the developer cannot be verified." This is expected for an
unsigned build. To open it anyway:

1. Open the **Applications** folder in Finder.
2. **Right-click** (or Control-click) Tessera and choose **Open**.
3. In the dialog, click **Open** again to confirm.

You only need to do this once. After the first launch, Tessera opens normally.

If the right-click path does not offer an Open button, go to **System Settings →
Privacy & Security**, scroll to the Security section, and click **Open Anyway**
next to the Tessera notice, then confirm.

Requirements: macOS 13 Ventura or newer, Apple silicon or Intel, 8 GB RAM
(16 GB recommended).

## Windows

Download the `.exe` and run it. Windows SmartScreen may warn that the publisher
is unrecognized for an unsigned build; choose **More info → Run anyway** to
proceed.

Requirements: Windows 10/11 64-bit, 8 GB RAM (16 GB recommended), a DirectX 12
GPU recommended for acceleration.

## Linux

Download the `.AppImage`, mark it executable, and run it:

```bash
chmod +x Tessera-*.AppImage
./Tessera-*.AppImage
```

The AppImage is portable and needs no installation.

Requirements: x86_64, glibc 2.31 or newer, 8 GB RAM (16 GB recommended).

## Disk space

Plan for roughly 10 GB of free disk for the app plus downloaded models. The
catalog and thumbnail cache grow with the size of your library.

## Build from source

The full source is on [GitHub](https://github.com/tessera-app/tessera) under
AGPLv3. If you prefer to build it yourself, or run the backend as a service, see
[Configuration](/docs/configuration) for the file and environment layout.
